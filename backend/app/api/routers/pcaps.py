"""
PCAP 路由。
POST /pcaps/upload、GET /pcaps、GET /pcaps/{id}/status、POST /pcaps/{id}/process
"""

import asyncio
import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Request, UploadFile, File, Query
from sqlalchemy.orm import Session
from streaming_form_data import StreamingFormDataParser
from streaming_form_data.targets import FileTarget, ValueTarget

from app.api.deps import get_db, SessionLocal
from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError, UnsupportedMediaError
from app.core.logging import get_logger
from app.core.loop import get_main_loop
from app.models.flow import Flow
from app.models.pcap import PcapFile
from app.schemas.common import ApiResponse
from app.schemas.pcap import PcapFileSchema, PcapProcessRequest, PcapProcessResponse
from app.services.ingestion.service import IngestionService
from app.services.parsing.service import ParsingService
from app.services.features.service import FeaturesService
from app.services.detection.composite import CompositeDetectionService
from app.services.alerting.service import AlertingService
from app.models.alert import Alert, alert_flows
from app.services.pipeline import PipelineTracker, PipelineStage

logger = get_logger(__name__)

router = APIRouter(prefix="/pcaps", tags=["pcaps"])


# --------------- 后台处理任务 ---------------

def _process_pcap_sync(pcap_id: str, mode: str, window_sec: int) -> None:
    """
    同步 PCAP 处理任务。
    在 FastAPI BackgroundTasks（线程池）中运行。
    """
    db = SessionLocal()
    tracker = None
    try:
        pcap = db.query(PcapFile).filter(PcapFile.id == pcap_id).first()
        if not pcap:
            logger.error(f"PCAP {pcap_id} not found for processing")
            return

        # --- 通过 EventBus 发布事件（已消除旧旁路） ---
        from app.core.events import get_event_bus
        from app.core.events.models import (
            make_event,
            PCAP_PROCESS_PROGRESS,
            PCAP_PROCESS_DONE,
            PCAP_PROCESS_FAILED,
            ALERT_CREATED,
        )

        def _publish(event_type: str, data: dict):
            """在后台线程中通过 EventBus 发布事件（fire-and-forget）。"""
            try:
                loop = get_main_loop()
                if loop is None or not loop.is_running():
                    return
                asyncio.run_coroutine_threadsafe(
                    get_event_bus().publish(make_event(event_type, data)), loop
                )
            except Exception:
                pass  # 非关键路径，不因事件发布失败中断处理

        # --- pipeline 追踪器（可观测性） ---
        tracker = None
        if settings.PIPELINE_OBSERVABILITY_ENABLED:
            tracker = PipelineTracker(pcap_id, db)

        # 步骤 1：更新状态 → processing 10%
        pcap.status = "processing"
        pcap.progress = 10
        db.commit()
        _publish(PCAP_PROCESS_PROGRESS, {"pcap_id": pcap_id, "percent": 10})

        # 步骤 2：解析 PCAP → flows
        if tracker:
            with tracker.stage(PipelineStage.PARSE) as stg:
                parser = ParsingService()
                stg.record_input({"pcap_path": pcap.storage_path, "window_sec": window_sec})
                flow_dicts = parser.parse_to_flows(Path(pcap.storage_path), window_sec=window_sec)
                stg.record_metrics({"flow_count": len(flow_dicts)})
                stg.record_output({"flow_count": len(flow_dicts)})
        else:
            parser = ParsingService()
            flow_dicts = parser.parse_to_flows(Path(pcap.storage_path), window_sec=window_sec)
        pcap.progress = 40
        db.commit()
        _publish(PCAP_PROCESS_PROGRESS, {"pcap_id": pcap_id, "percent": 40})

        # 步骤 3：为每条 flow 提取特征
        if tracker:
            with tracker.stage(PipelineStage.FEATURE_EXTRACT) as stg:
                feat_svc = FeaturesService()
                stg.record_input({"flow_count": len(flow_dicts)})
                flow_dicts = feat_svc.extract_features_batch(flow_dicts)
                stg.record_metrics({"flow_count": len(flow_dicts)})
                stg.record_output({"flow_count": len(flow_dicts)})
        else:
            feat_svc = FeaturesService()
            flow_dicts = feat_svc.extract_features_batch(flow_dicts)
        pcap.progress = 55
        db.commit()
        _publish(PCAP_PROCESS_PROGRESS, {"pcap_id": pcap_id, "percent": 55})

        # 步骤 4：异常评分（仅当 mode == flows_and_detect）
        if mode == "flows_and_detect":
            if tracker:
                with tracker.stage(PipelineStage.DETECT) as stg:
                    det_svc = CompositeDetectionService()
                    stg.record_input({"flow_count": len(flow_dicts)})
                    flow_dicts = det_svc.score_flows(flow_dicts)
                    scored = [f for f in flow_dicts if f.get("anomaly_score") is not None]
                    stg.record_metrics({
                        "scored_count": len(scored),
                        "max_score": max((f["anomaly_score"] for f in scored), default=0),
                    })
                    stg.record_output({"scored_flow_count": len(scored)})
            else:
                det_svc = CompositeDetectionService()
                flow_dicts = det_svc.score_flows(flow_dicts)
            pcap.progress = 70
            db.commit()
            _publish(PCAP_PROCESS_PROGRESS, {"pcap_id": pcap_id, "percent": 70})
        elif tracker:
            with tracker.stage(PipelineStage.DETECT) as stg:
                stg.skip("mode != flows_and_detect")

        # 步骤 5：将 flows 入库（Core bulk insert，绕过 ORM 开销）
        _BULK = 50_000
        flow_rows = [
            {
                "id": fd["id"],
                "version": fd.get("version", "1.1"),
                "created_at": fd["created_at"],
                "pcap_id": pcap_id,
                "ts_start": fd["ts_start"],
                "ts_end": fd["ts_end"],
                "src_ip": fd["src_ip"],
                "src_port": fd["src_port"],
                "dst_ip": fd["dst_ip"],
                "dst_port": fd["dst_port"],
                "proto": fd["proto"],
                "packets_fwd": fd["packets_fwd"],
                "packets_bwd": fd["packets_bwd"],
                "bytes_fwd": fd["bytes_fwd"],
                "bytes_bwd": fd["bytes_bwd"],
                "features": json.dumps(fd.get("features", {})),
                "anomaly_score": fd.get("anomaly_score"),
                "label": fd.get("label"),
            }
            for fd in flow_dicts
        ]
        flow_table = Flow.__table__
        for i in range(0, len(flow_rows), _BULK):
            db.execute(flow_table.insert(), flow_rows[i:i + _BULK])
        db.flush()
        pcap.progress = 85
        db.commit()
        _publish(PCAP_PROCESS_PROGRESS, {"pcap_id": pcap_id, "percent": 85})

        # 步骤 6：生成 alerts（仅当 mode == flows_and_detect）
        alert_count = 0
        if mode == "flows_and_detect":
            if tracker:
                with tracker.stage(PipelineStage.AGGREGATE) as stg:
                    alert_svc = AlertingService(score_threshold=0.7, window_sec=window_sec)
                    stg.record_input({"flow_count": len(flow_dicts)})
                    alert_dicts = alert_svc.generate_alerts(flow_dicts, pcap_id)
                    stg.record_metrics({"alert_count": len(alert_dicts)})
                    stg.record_output({"alert_count": len(alert_dicts)})
            else:
                alert_svc = AlertingService(score_threshold=0.7, window_sec=window_sec)
                alert_dicts = alert_svc.generate_alerts(flow_dicts, pcap_id)
            alert_flow_links: list[dict] = []
            for ad in alert_dicts:
                flow_ids_for_alert = ad.pop("_flow_ids", [])
                db.execute(Alert.__table__.insert(), [{
                    "id": ad["id"],
                    "version": ad.get("version", "1.1"),
                    "created_at": ad["created_at"],
                    "severity": ad["severity"],
                    "status": ad["status"],
                    "type": ad["type"],
                    "time_window_start": ad["time_window_start"],
                    "time_window_end": ad["time_window_end"],
                    "primary_src_ip": ad["primary_src_ip"],
                    "primary_dst_ip": ad["primary_dst_ip"],
                    "primary_proto": ad["primary_proto"],
                    "primary_dst_port": ad["primary_dst_port"],
                    "evidence": ad["evidence"],
                    "aggregation": ad["aggregation"],
                    "agent": ad["agent"],
                    "twin": ad["twin"],
                    "tags": ad["tags"],
                    "notes": ad.get("notes", ""),
                }])
                for fid in flow_ids_for_alert:
                    alert_flow_links.append({"alert_id": ad["id"], "flow_id": fid, "role": "top"})
                _publish(ALERT_CREATED, {
                    "alert_id": ad["id"],
                    "severity": ad["severity"],
                })
            if alert_flow_links:
                for i in range(0, len(alert_flow_links), _BULK):
                    db.execute(alert_flows.insert(), alert_flow_links[i:i + _BULK])
            alert_count = len(alert_dicts)
            db.commit()
            pcap.progress = 95
            db.commit()
            _publish(PCAP_PROCESS_PROGRESS, {"pcap_id": pcap_id, "percent": 95})
        elif tracker:
            with tracker.stage(PipelineStage.AGGREGATE) as stg:
                stg.skip("mode != flows_and_detect")

        # 步骤 7：收尾
        flow_count = len(flow_dicts)
        pcap.status = "done"
        pcap.progress = 100
        pcap.flow_count = flow_count
        pcap.alert_count = alert_count
        db.commit()
        logger.info(f"PCAP {pcap_id} processed ({mode}): {flow_count} flows, {alert_count} alerts")
        _publish(PCAP_PROCESS_PROGRESS, {"pcap_id": pcap_id, "percent": 100})
        _publish(PCAP_PROCESS_DONE, {
            "pcap_id": pcap_id,
            "flow_count": flow_count,
            "alert_count": alert_count,
        })

        # 结束 pipeline 追踪
        if tracker:
            tracker.finish()
            db.commit()

    except Exception as exc:
        logger.exception(f"Processing failed for PCAP {pcap_id}")
        # 发布处理失败事件（前端已订阅 pcap.process.failed）
        _publish(PCAP_PROCESS_FAILED, {
            "pcap_id": pcap_id,
            "error": str(exc)[:500],
        })
        if tracker:
            try:
                tracker.fail(str(exc)[:500])
                db.commit()
            except Exception:
                pass
        try:
            pcap = db.query(PcapFile).filter(PcapFile.id == pcap_id).first()
            if pcap:
                pcap.status = "failed"
                pcap.error_message = str(exc)[:500]
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


# --------------- 接口 ---------------

class _HashingFileTarget(FileTarget):
    """FileTarget that computes SHA256 on the fly and captures the first 4 bytes."""

    def __init__(self, filepath: str, **kwargs):
        super().__init__(filepath, **kwargs)
        self._hasher = hashlib.sha256()
        self._size = 0
        self._magic = b""

    def on_data_received(self, chunk: bytes):
        if self._size == 0 and chunk:
            self._magic = chunk[:4]
        self._hasher.update(chunk)
        self._size += len(chunk)
        super().on_data_received(chunk)

    @property
    def sha256(self) -> str:
        return f"sha256:{self._hasher.hexdigest()}"

    @property
    def size(self) -> int:
        return self._size

    @property
    def magic(self) -> bytes:
        return self._magic


_VALID_PCAP_MAGICS = {
    b"\xa1\xb2\xc3\xd4", b"\xd4\xc3\xb2\xa1",
    b"\xa1\xb2\x3c\x4d", b"\x4d\x3c\xb2\xa1",
    b"\x0a\x0d\x0d\x0a",
}


@router.post(
    "/upload",
    response_model=ApiResponse[PcapFileSchema],
    summary="Upload PCAP File",
    description="Upload a PCAP file for analysis. Returns file metadata. (DOC C C6.2.1)",
)
async def upload_pcap(
    request: Request,
    db: Session = Depends(get_db),
) -> ApiResponse[PcapFileSchema]:
    """
    流式上传 PCAP 文件。

    使用 streaming-form-data 直接将上传数据写入磁盘，
    无需将整个文件加载到内存。内存占用固定 ~64KB。
    同步计算 SHA256 和文件大小。
    """
    from app.core.utils import generate_uuid, sanitize_filename, datetime_to_iso

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        raise UnsupportedMediaError(
            message="Content-Type must be multipart/form-data",
            details={"content_type": content_type},
        )

    pcap_id = generate_uuid()
    storage_path = settings.PCAP_DIR / f"{pcap_id}.pcap"
    settings.PCAP_DIR.mkdir(parents=True, exist_ok=True)

    # 设置流式解析器：文件数据直接写入磁盘
    file_target = _HashingFileTarget(str(storage_path))
    filename_target = ValueTarget()

    parser = StreamingFormDataParser(headers={"Content-Type": content_type})
    parser.register("file", file_target)
    parser.register("filename", filename_target)

    # 流式接收 — 每个 chunk 到达即写入磁盘，内存固定
    async for chunk in request.stream():
        parser.data_received(chunk)

    # 获取文件名（从 multipart Content-Disposition 中提取）
    raw_filename = file_target.multipart_filename or "unknown.pcap"
    safe_filename = sanitize_filename(raw_filename)

    # 魔数校验
    if file_target.size < 4 or file_target.magic not in _VALID_PCAP_MAGICS:
        storage_path.unlink(missing_ok=True)
        raise UnsupportedMediaError(
            message="File does not appear to be a valid PCAP file (invalid magic number)",
            details={"filename": raw_filename},
        )

    logger.info("流式上传完成: %s (%d bytes, %s)", pcap_id, file_target.size, safe_filename)

    # 创建数据库记录
    pcap_record = PcapFile(
        id=pcap_id,
        filename=safe_filename,
        storage_path=str(storage_path),
        sha256=file_target.sha256,
        size_bytes=file_target.size,
        status="uploaded",
        progress=0,
        flow_count=0,
        alert_count=0,
    )
    db.add(pcap_record)
    db.commit()
    db.refresh(pcap_record)

    service = IngestionService(db)
    return ApiResponse.success(service._to_schema(pcap_record))


@router.get(
    "",
    response_model=ApiResponse[list[PcapFileSchema]],
    summary="List PCAP Files",
    description="List all uploaded PCAP files with pagination. (DOC C C6.2.3)",
)
async def list_pcaps(
    limit: int = Query(default=50, ge=1, le=1000, description="Max results"),
    offset: int = Query(default=0, ge=0, description="Skip count"),
    db: Session = Depends(get_db),
) -> ApiResponse[list[PcapFileSchema]]:
    """按 created_at 倒序列出 PCAP 文件。"""
    service = IngestionService(db)
    pcaps = service.list_pcaps(limit=limit, offset=offset)
    return ApiResponse.success(pcaps)


@router.get(
    "/{pcap_id}/status",
    response_model=ApiResponse[PcapFileSchema],
    summary="Get PCAP Status",
    description="Get status and metadata of a specific PCAP file. (DOC C C6.2.4)",
)
async def get_pcap_status(
    pcap_id: str,
    db: Session = Depends(get_db),
) -> ApiResponse[PcapFileSchema]:
    """按 ID 获取 PCAP 文件状态。"""
    service = IngestionService(db)
    pcap = service.get_pcap(pcap_id)
    return ApiResponse.success(pcap)


@router.post(
    "/{pcap_id}/process",
    response_model=ApiResponse[PcapProcessResponse],
    summary="Start PCAP Processing",
    description="Start async processing of a PCAP file. (DOC C C6.2.2)",
)
async def process_pcap(
    pcap_id: str,
    request: PcapProcessRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ApiResponse[PcapProcessResponse]:
    """启动 PCAP 处理任务。"""
    pcap = db.query(PcapFile).filter(PcapFile.id == pcap_id).first()
    if not pcap:
        raise NotFoundError(
            message=f"PCAP file not found: {pcap_id}",
            details={"pcap_id": pcap_id},
        )
    if pcap.status == "processing":
        raise ConflictError(
            message=f"PCAP {pcap_id} is already processing",
            details={"pcap_id": pcap_id, "status": pcap.status},
        )

    background_tasks.add_task(_process_pcap_sync, pcap_id, request.mode, request.window_sec)
    return ApiResponse.success(PcapProcessResponse(accepted=True))


@router.delete(
    "/{pcap_id}",
    response_model=ApiResponse[dict],
    summary="Delete PCAP File",
    description="删除 PCAP 文件及其所有关联数据。",
)
async def delete_pcap(
    pcap_id: str,
    db: Session = Depends(get_db),
) -> ApiResponse[dict]:
    """删除 PCAP 文件、关联数据和磁盘文件。"""
    service = IngestionService(db)
    service.delete_pcap(pcap_id)
    return ApiResponse.success({"deleted": True})

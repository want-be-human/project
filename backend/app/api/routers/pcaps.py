"""
PCAP 路由。
POST /pcaps/upload、GET /pcaps、GET /pcaps/{id}/status、POST /pcaps/{id}/process
"""

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, File, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, SessionLocal
from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError
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

        # --- 广播辅助（在运行中的事件循环里 fire-and-forget） ---
        from app.api.routers.stream import manager

        def _broadcast(event: str, data: dict):
            try:
                # 使用保存的主事件循环引用，而非 asyncio.get_event_loop()
                # 后者在 BackgroundTasks 线程池中无法获取主循环
                loop = get_main_loop()
                if loop is None:
                    return  # 循环未初始化（如单元测试场景），静默跳过
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        manager.broadcast(event, data), loop
                    )
            except RuntimeError:
                pass  # 兜底：防止其他运行时异常

        # --- pipeline 追踪器（可观测性） ---
        tracker = None
        if settings.PIPELINE_OBSERVABILITY_ENABLED:
            tracker = PipelineTracker(pcap_id, db)

        # 步骤 1：更新状态 → processing 10%
        pcap.status = "processing"
        pcap.progress = 10
        db.commit()
        _broadcast("pcap.process.progress", {"pcap_id": pcap_id, "percent": 10})

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
        _broadcast("pcap.process.progress", {"pcap_id": pcap_id, "percent": 40})

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
        _broadcast("pcap.process.progress", {"pcap_id": pcap_id, "percent": 55})

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
            _broadcast("pcap.process.progress", {"pcap_id": pcap_id, "percent": 70})
        elif tracker:
            with tracker.stage(PipelineStage.DETECT) as stg:
                stg.skip("mode != flows_and_detect")

        # 步骤 5：将 flows 入库
        for fd in flow_dicts:
            features_json = json.dumps(fd.get("features", {}))
            flow = Flow(
                id=fd["id"],
                version=fd.get("version", "1.1"),
                created_at=fd["created_at"],
                pcap_id=pcap_id,
                ts_start=fd["ts_start"],
                ts_end=fd["ts_end"],
                src_ip=fd["src_ip"],
                src_port=fd["src_port"],
                dst_ip=fd["dst_ip"],
                dst_port=fd["dst_port"],
                proto=fd["proto"],
                packets_fwd=fd["packets_fwd"],
                packets_bwd=fd["packets_bwd"],
                bytes_fwd=fd["bytes_fwd"],
                bytes_bwd=fd["bytes_bwd"],
                features=features_json,
                anomaly_score=fd.get("anomaly_score"),
                label=fd.get("label"),
            )
            db.add(flow)

        db.flush()
        pcap.progress = 85
        db.commit()
        _broadcast("pcap.process.progress", {"pcap_id": pcap_id, "percent": 85})

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
            for ad in alert_dicts:
                flow_ids_for_alert = ad.pop("_flow_ids", [])
                alert_obj = Alert(
                    id=ad["id"],
                    version=ad.get("version", "1.1"),
                    created_at=ad["created_at"],
                    severity=ad["severity"],
                    status=ad["status"],
                    type=ad["type"],
                    time_window_start=ad["time_window_start"],
                    time_window_end=ad["time_window_end"],
                    primary_src_ip=ad["primary_src_ip"],
                    primary_dst_ip=ad["primary_dst_ip"],
                    primary_proto=ad["primary_proto"],
                    primary_dst_port=ad["primary_dst_port"],
                    evidence=ad["evidence"],
                    aggregation=ad["aggregation"],
                    agent=ad["agent"],
                    twin=ad["twin"],
                    tags=ad["tags"],
                    notes=ad.get("notes", ""),
                )
                db.add(alert_obj)
                db.flush()
                # 插入 alert_flows 关联
                for fid in flow_ids_for_alert:
                    db.execute(
                        alert_flows.insert().values(
                            alert_id=ad["id"],
                            flow_id=fid,
                            role="top",
                        )
                    )
                # WS: alert.created
                _broadcast("alert.created", {
                    "alert_id": ad["id"],
                    "severity": ad["severity"],
                })
            alert_count = len(alert_dicts)
            db.commit()
            pcap.progress = 95
            db.commit()
            _broadcast("pcap.process.progress", {"pcap_id": pcap_id, "percent": 95})
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
        _broadcast("pcap.process.progress", {"pcap_id": pcap_id, "percent": 100})
        _broadcast("pcap.process.done", {
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

@router.post(
    "/upload",
    response_model=ApiResponse[PcapFileSchema],
    summary="Upload PCAP File",
    description="Upload a PCAP file for analysis. Returns file metadata. (DOC C C6.2.1)",
)
async def upload_pcap(
    file: UploadFile = File(..., description="PCAP file to upload"),
    db: Session = Depends(get_db),
) -> ApiResponse[PcapFileSchema]:
    """上传 PCAP 文件。"""
    service = IngestionService(db)
    pcap = service.save_pcap(file.file, file.filename or "unknown.pcap")
    return ApiResponse.success(pcap)


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

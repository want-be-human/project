"""
PCAP router.
POST /pcaps/upload, GET /pcaps, GET /pcaps/{id}/status, POST /pcaps/{id}/process
"""

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, File, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, SessionLocal
from app.core.errors import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models.flow import Flow
from app.models.pcap import PcapFile
from app.schemas.common import ApiResponse
from app.schemas.pcap import PcapFileSchema, PcapProcessRequest, PcapProcessResponse
from app.services.ingestion.service import IngestionService
from app.services.parsing.service import ParsingService

logger = get_logger(__name__)

router = APIRouter(prefix="/pcaps", tags=["pcaps"])


# --------------- background processing task ---------------

def _process_pcap_sync(pcap_id: str, mode: str, window_sec: int) -> None:
    """
    Synchronous PCAP processing task.
    Runs inside FastAPI BackgroundTasks (thread-pool).
    """
    db = SessionLocal()
    try:
        pcap = db.query(PcapFile).filter(PcapFile.id == pcap_id).first()
        if not pcap:
            logger.error(f"PCAP {pcap_id} not found for processing")
            return

        # --- broadcast helpers (fire-and-forget in running event loop) ---
        from app.api.routers.stream import manager

        def _broadcast(event: str, data: dict):
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        manager.broadcast(event, data), loop
                    )
            except RuntimeError:
                pass  # no event loop available (e.g. unit test)

        # Step 1: update → processing 10 %
        pcap.status = "processing"
        pcap.progress = 10
        db.commit()
        _broadcast("pcap.process.progress", {"pcap_id": pcap_id, "percent": 10})

        # Step 2: parse PCAP → flows
        parser = ParsingService()
        flow_dicts = parser.parse_to_flows(Path(pcap.storage_path), window_sec=window_sec)
        pcap.progress = 50
        db.commit()
        _broadcast("pcap.process.progress", {"pcap_id": pcap_id, "percent": 50})

        # Step 3: insert flows into DB
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
        pcap.progress = 80
        db.commit()
        _broadcast("pcap.process.progress", {"pcap_id": pcap_id, "percent": 80})

        # Step 4: (flows_and_detect would run anomaly detection here – Week 3)

        # Step 5: finalize
        flow_count = len(flow_dicts)
        pcap.status = "done"
        pcap.progress = 100
        pcap.flow_count = flow_count
        pcap.alert_count = 0  # will be set by detection in Week 3+
        db.commit()
        logger.info(f"PCAP {pcap_id} processed: {flow_count} flows")
        _broadcast("pcap.process.progress", {"pcap_id": pcap_id, "percent": 100})
        _broadcast("pcap.process.done", {
            "pcap_id": pcap_id,
            "flow_count": flow_count,
            "alert_count": 0,
        })

    except Exception as exc:
        logger.exception(f"Processing failed for PCAP {pcap_id}")
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


# --------------- endpoints ---------------

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
    """Upload a PCAP file."""
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
    """List PCAP files ordered by created_at descending."""
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
    """Get PCAP file status by ID."""
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
    """Start processing a PCAP file."""
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

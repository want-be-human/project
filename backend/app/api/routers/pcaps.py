"""
PCAP router.
POST /pcaps/upload, GET /pcaps, GET /pcaps/{id}/status, POST /pcaps/{id}/process
"""

from fastapi import APIRouter, Depends, UploadFile, File, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.common import ApiResponse
from app.schemas.pcap import PcapFileSchema, PcapProcessRequest, PcapProcessResponse
from app.services.ingestion.service import IngestionService

router = APIRouter(prefix="/pcaps", tags=["pcaps"])


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
    """
    Upload a PCAP file.
    
    - Validates file extension (.pcap, .pcapng)
    - Validates PCAP magic number
    - Stores file and creates database record
    - Returns PcapFile metadata
    """
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
    """
    List PCAP files ordered by created_at descending.
    """
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
    """
    Get PCAP file status by ID.
    """
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
    db: Session = Depends(get_db),
) -> ApiResponse[PcapProcessResponse]:
    """
    Start processing a PCAP file.
    
    Processing modes:
    - flows_only: Extract flows without anomaly detection
    - flows_and_detect: Extract flows and run anomaly detection
    
    Processing is async; use GET /pcaps/{id}/status to check progress.
    """
    # Verify PCAP exists
    service = IngestionService(db)
    pcap = service.get_pcap_model(pcap_id)

    # Update status to processing
    service.update_status(pcap_id, status="processing", progress=0)

    # TODO: Week 2 - Trigger background processing task
    # For now, just accept the request
    # BackgroundTasks.add_task(process_pcap_task, pcap_id, request.mode, request.window_sec)

    return ApiResponse.success(PcapProcessResponse(accepted=True))

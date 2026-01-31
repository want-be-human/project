"""
Flows router.
GET /flows, GET /flows/{flow_id}
"""

from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.common import ApiResponse
from app.schemas.flow import FlowRecordSchema

router = APIRouter(prefix="/flows", tags=["flows"])


@router.get(
    "",
    response_model=ApiResponse[list[FlowRecordSchema]],
    summary="List Flows",
    description="List flows with filtering and pagination. (DOC C C6.3)",
)
async def list_flows(
    pcap_id: str | None = Query(default=None, description="Filter by PCAP ID"),
    src_ip: str | None = Query(default=None, description="Filter by source IP"),
    dst_ip: str | None = Query(default=None, description="Filter by destination IP"),
    proto: str | None = Query(default=None, description="Filter by protocol"),
    min_score: float | None = Query(default=None, ge=0.0, le=1.0, description="Minimum anomaly score"),
    start: str | None = Query(default=None, description="Start time filter ISO8601"),
    end: str | None = Query(default=None, description="End time filter ISO8601"),
    limit: int = Query(default=100, ge=1, le=1000, description="Max results"),
    offset: int = Query(default=0, ge=0, description="Skip count"),
    db: Session = Depends(get_db),
) -> ApiResponse[list[FlowRecordSchema]]:
    """
    List flow records with optional filters.
    """
    # TODO: Implement flow listing with filters
    # For now, return empty list
    return ApiResponse.success([])


@router.get(
    "/{flow_id}",
    response_model=ApiResponse[FlowRecordSchema],
    summary="Get Flow Details",
    description="Get a specific flow record by ID. (DOC C C6.3)",
)
async def get_flow(
    flow_id: str = Path(..., description="Flow ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[FlowRecordSchema]:
    """
    Get flow record by ID.
    """
    # TODO: Implement flow retrieval
    from app.core.errors import NotFoundError
    raise NotFoundError(resource="Flow", resource_id=flow_id)

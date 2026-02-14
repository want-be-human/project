"""
Flows router.
GET /flows, GET /flows/{flow_id}
"""

import json
from typing import cast

from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import NotFoundError
from app.core.utils import datetime_to_iso, iso_to_datetime
from app.models.flow import Flow
from app.schemas.common import ApiResponse
from app.schemas.flow import FlowRecordSchema

router = APIRouter(prefix="/flows", tags=["flows"])


def _flow_to_schema(flow: Flow) -> FlowRecordSchema:
    """Convert ORM Flow to Pydantic schema."""
    # features is stored as TEXT (JSON string) in SQLite
    features = flow.features
    if isinstance(features, str):
        try:
            features = json.loads(features)
        except (json.JSONDecodeError, TypeError):
            features = {}
    return FlowRecordSchema(
        version=flow.version,
        id=flow.id,
        created_at=datetime_to_iso(flow.created_at),
        pcap_id=flow.pcap_id,
        ts_start=datetime_to_iso(flow.ts_start),
        ts_end=datetime_to_iso(flow.ts_end),
        src_ip=flow.src_ip,
        src_port=flow.src_port,
        dst_ip=flow.dst_ip,
        dst_port=flow.dst_port,
        proto=cast(str, flow.proto),  # type: ignore[arg-type]
        packets_fwd=flow.packets_fwd,
        packets_bwd=flow.packets_bwd,
        bytes_fwd=flow.bytes_fwd,
        bytes_bwd=flow.bytes_bwd,
        features=features,
        anomaly_score=flow.anomaly_score,
        label=flow.label,
    )


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
    """List flow records with optional filters."""
    stmt = select(Flow)

    if pcap_id:
        stmt = stmt.where(Flow.pcap_id == pcap_id)
    if src_ip:
        stmt = stmt.where(Flow.src_ip == src_ip)
    if dst_ip:
        stmt = stmt.where(Flow.dst_ip == dst_ip)
    if proto:
        stmt = stmt.where(Flow.proto == proto.upper())
    if min_score is not None:
        stmt = stmt.where(Flow.anomaly_score >= min_score)
    if start:
        stmt = stmt.where(Flow.ts_start >= iso_to_datetime(start))
    if end:
        stmt = stmt.where(Flow.ts_end <= iso_to_datetime(end))

    stmt = stmt.order_by(Flow.ts_start.desc()).offset(offset).limit(limit)
    flows = db.execute(stmt).scalars().all()
    return ApiResponse.success([_flow_to_schema(f) for f in flows])


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
    """Get flow record by ID."""
    flow = db.get(Flow, flow_id)
    if not flow:
        raise NotFoundError(
            message=f"Flow not found: {flow_id}",
            details={"flow_id": flow_id},
        )
    return ApiResponse.success(_flow_to_schema(flow))

"""
流记录路由。
GET /flows、GET /flows/{flow_id}
"""

import json
from typing import cast

from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import NotFoundError
from app.core.utils import datetime_to_iso, iso_to_datetime
from app.models.flow import Flow
from app.schemas.common import ApiResponse, PaginatedData
from app.schemas.flow import FlowRecordSchema

router = APIRouter(prefix="/flows", tags=["flows"])


def _flow_to_schema(flow: Flow) -> FlowRecordSchema:
    """将 ORM Flow 转换为 Pydantic Schema。"""
    # features 在 SQLite 中以 TEXT（JSON 字符串）存储
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
    response_model=ApiResponse[PaginatedData[FlowRecordSchema]],
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
) -> ApiResponse[PaginatedData[FlowRecordSchema]]:
    """按可选筛选条件列出流记录。"""
    conditions = []
    if pcap_id:
        conditions.append(Flow.pcap_id == pcap_id)
    if src_ip:
        conditions.append(Flow.src_ip == src_ip)
    if dst_ip:
        conditions.append(Flow.dst_ip == dst_ip)
    if proto:
        conditions.append(Flow.proto == proto.upper())
    if min_score is not None:
        conditions.append(Flow.anomaly_score >= min_score)
    if start:
        conditions.append(Flow.ts_start >= iso_to_datetime(start))
    if end:
        conditions.append(Flow.ts_end <= iso_to_datetime(end))

    count_stmt = select(func.count()).select_from(Flow)
    data_stmt = select(Flow)
    for cond in conditions:
        count_stmt = count_stmt.where(cond)
        data_stmt = data_stmt.where(cond)

    total = db.execute(count_stmt).scalar() or 0
    data_stmt = data_stmt.order_by(Flow.ts_start.desc()).offset(offset).limit(limit)
    flows = db.execute(data_stmt).scalars().all()
    return ApiResponse.success(PaginatedData(
        items=[_flow_to_schema(f) for f in flows],
        total=total,
        limit=limit,
        offset=offset,
    ))


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
    """按 ID 获取流记录。"""
    flow = db.get(Flow, flow_id)
    if not flow:
        raise NotFoundError(
            message=f"Flow not found: {flow_id}",
            details={"flow_id": flow_id},
        )
    return ApiResponse.success(_flow_to_schema(flow))

"""
拓扑路由。
GET /topology/graph — DOC C C6.7
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.utils import iso_to_datetime
from app.models.flow import Flow
from app.schemas.common import ApiResponse
from app.schemas.topology import GraphResponseSchema

router = APIRouter(prefix="/topology", tags=["topology"])


@router.get(
    "/graph",
    response_model=ApiResponse[GraphResponseSchema],
    summary="Get Topology Graph",
    description="Get topology graph for time range. (DOC C C6.7)",
)
async def get_topology_graph(
    start: str | None = Query(default=None, description="Start time ISO8601"),
    end: str | None = Query(default=None, description="End time ISO8601"),
    mode: str = Query(default="ip", description="Graph mode: ip or subnet"),
    db: Session = Depends(get_db),
) -> ApiResponse[GraphResponseSchema]:
    """
    按指定时间窗口构建并返回拓扑图。

    参数：
    - start: 查询开始时间（ISO8601，不传则使用最早 flow）
    - end: 查询结束时间（ISO8601，不传则使用最晚 flow）
    - mode: 'ip' 表示主机级，'subnet' 表示子网级聚合

    返回包含 nodes、edges 和 meta 的 GraphResponse。
    """
    from app.services.topology import TopologyService

    if start:
        dt_start = iso_to_datetime(start)
    else:
        dt_start = db.query(func.min(Flow.ts_start)).scalar()

    if end:
        dt_end = iso_to_datetime(end)
    else:
        dt_end = db.query(func.max(Flow.ts_end)).scalar()

    if dt_start is None or dt_end is None:
        # 数据库无 flow 时返回空图
        from app.schemas.topology import GraphMeta
        empty = GraphResponseSchema(
            version="1.1", nodes=[], edges=[],
            meta=GraphMeta(start="", end="", mode=mode),  # type: ignore[arg-type]
        )
        return ApiResponse.success(empty)

    svc = TopologyService(db)
    graph = svc.build_graph(start=dt_start, end=dt_end, mode=mode)  # type: ignore[arg-type]
    return ApiResponse.success(graph)

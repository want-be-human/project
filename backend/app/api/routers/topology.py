"""拓扑路由。GET /topology/graph — DOC C C6.7。"""

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
    description="按时间范围获取拓扑图。(DOC C C6.7)",
)
async def get_topology_graph(
    start: str | None = Query(default=None, description="起始时间（ISO8601）"),
    end: str | None = Query(default=None, description="结束时间（ISO8601）"),
    mode: str = Query(default="ip", description="拓扑聚合模式：ip / subnet"),
    db: Session = Depends(get_db),
) -> ApiResponse[GraphResponseSchema]:
    from app.services.topology import TopologyService

    dt_start = iso_to_datetime(start) if start else db.query(func.min(Flow.ts_start)).scalar()
    dt_end = iso_to_datetime(end) if end else db.query(func.max(Flow.ts_end)).scalar()

    if dt_start is None or dt_end is None:
        # 数据库无 flow 时返回空图
        from app.schemas.topology import GraphMeta
        empty = GraphResponseSchema(
            version="1.1", nodes=[], edges=[],
            meta=GraphMeta(start="", end="", mode=mode),  # type: ignore[arg-type]
        )
        return ApiResponse.success(empty)

    graph = TopologyService(db).build_graph(start=dt_start, end=dt_end, mode=mode)  # type: ignore[arg-type]
    return ApiResponse.success(graph)

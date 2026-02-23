"""
Topology router.
GET /topology/graph — DOC C C6.7
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.utils import iso_to_datetime
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
    start: str = Query(..., description="Start time ISO8601"),
    end: str = Query(..., description="End time ISO8601"),
    mode: str = Query(default="ip", description="Graph mode: ip or subnet"),
    db: Session = Depends(get_db),
) -> ApiResponse[GraphResponseSchema]:
    """
    Build and return topology graph for the specified time window.
    
    Parameters:
    - start: ISO8601 timestamp for query start
    - end: ISO8601 timestamp for query end
    - mode: 'ip' for host-level, 'subnet' for subnet-level grouping
    
    Returns GraphResponse with nodes, edges, and metadata.
    """
    from app.services.topology import TopologyService

    svc = TopologyService(db)
    graph = svc.build_graph(
        start=iso_to_datetime(start),
        end=iso_to_datetime(end),
        mode=mode,
    )
    return ApiResponse.success(graph)

"""
Topology schemas: GraphResponse.
Strictly follows DOC C C5.1 GraphResponse schema.
"""

from typing import Literal
from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    """Node in topology graph - DOC C C5.1."""
    id: str = Field(..., description="Node ID (e.g., ip:192.0.2.10)")
    label: str = Field(..., description="Display label")
    type: Literal["host", "subnet", "service"] = Field(..., description="Node type")
    risk: float = Field(default=0.0, ge=0.0, le=1.0, description="Risk score")


class GraphEdge(BaseModel):
    """Edge in topology graph - DOC C C5.1."""
    id: str = Field(..., description="Edge ID")
    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")
    proto: str = Field(..., description="Protocol")
    dst_port: int = Field(..., description="Destination port")
    weight: int = Field(default=1, description="Edge weight (flow count)")
    risk: float = Field(default=0.0, ge=0.0, le=1.0, description="Risk score")
    activeIntervals: list[list[str]] = Field(
        default_factory=list,
        description="Active time intervals [[start, end], ...]"
    )
    alert_ids: list[str] = Field(default_factory=list, description="Related alert IDs")


class GraphMeta(BaseModel):
    """Metadata for graph response - DOC C C5.1."""
    start: str = Field(..., description="Query start time ISO8601")
    end: str = Field(..., description="Query end time ISO8601")
    mode: Literal["ip", "subnet"] = Field(..., description="Graph mode")


class GraphResponseSchema(BaseModel):
    """
    GraphResponse output schema - DOC C C5.1.
    """

    version: str = Field(default="1.1", description="Schema version")
    nodes: list[GraphNode] = Field(default_factory=list, description="Graph nodes")
    edges: list[GraphEdge] = Field(default_factory=list, description="Graph edges")
    meta: GraphMeta = Field(..., description="Graph metadata")


# topology 查询参数 - DOC C C6.7
class TopologyQueryParams(BaseModel):
    """Query parameters for GET /topology/graph - DOC C C6.7."""
    start: str = Field(..., description="Start time ISO8601")
    end: str = Field(..., description="End time ISO8601")
    mode: Literal["ip", "subnet"] = Field(default="ip", description="Graph mode")

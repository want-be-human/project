"""
Topology 相关 Schema：GraphResponse。
严格遵循 DOC C C5.1 的 GraphResponse 规范。
"""

from typing import Literal
from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    """拓扑图节点 - DOC C C5.1。"""
    id: str = Field(..., description="节点 ID（例如 ip:192.0.2.10）")
    label: str = Field(..., description="显示标签")
    type: Literal["host", "subnet", "service"] = Field(..., description="节点类型")
    risk: float = Field(default=0.0, ge=0.0, le=1.0, description="风险分值")


class GraphEdge(BaseModel):
    """拓扑图边 - DOC C C5.1。"""
    id: str = Field(..., description="边 ID")
    source: str = Field(..., description="源节点 ID")
    target: str = Field(..., description="目标节点 ID")
    proto: str = Field(..., description="协议")
    dst_port: int = Field(..., description="目标端口")
    weight: int = Field(default=1, description="边权重（流数量）")
    risk: float = Field(default=0.0, ge=0.0, le=1.0, description="风险分值")
    activeIntervals: list[list[str]] = Field(
        default_factory=list,
        description="活跃时间区间 [[start, end], ...]"
    )
    alert_ids: list[str] = Field(default_factory=list, description="关联告警 ID 列表")


class GraphMeta(BaseModel):
    """图响应元数据 - DOC C C5.1。"""
    start: str = Field(..., description="查询开始时间（ISO8601）")
    end: str = Field(..., description="查询结束时间（ISO8601）")
    mode: Literal["ip", "subnet"] = Field(..., description="图模式")


class GraphResponseSchema(BaseModel):
    """
    GraphResponse 输出模式 - DOC C C5.1。
    """

    version: str = Field(default="1.1", description="模式版本")
    nodes: list[GraphNode] = Field(default_factory=list, description="图节点列表")
    edges: list[GraphEdge] = Field(default_factory=list, description="图边列表")
    meta: GraphMeta = Field(..., description="图元数据")


# topology 查询参数 - DOC C C6.7
class TopologyQueryParams(BaseModel):
    """拓扑图接口查询参数 - DOC C C6.7。"""
    start: str = Field(..., description="开始时间（ISO8601）")
    end: str = Field(..., description="结束时间（ISO8601）")
    mode: Literal["ip", "subnet"] = Field(default="ip", description="图模式")

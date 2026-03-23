"""
EvidenceChain Schema。
严格遵循 DOC C C3.1 EvidenceChain 规范。
"""

from typing import Literal
from pydantic import BaseModel, Field


class EvidenceNode(BaseModel):
    """证据链中的节点 - DOC C C3.1。"""
    id: str = Field(..., description="节点 ID（例如 alert:uuid, flow:uuid）")
    type: Literal["alert", "flow", "feature", "hypothesis", "action", "dryrun"] = Field(
        ..., description="节点类型"
    )
    label: str = Field(..., description="显示标签")


class EvidenceEdge(BaseModel):
    """证据链中的边 - DOC C C3.1。"""
    source: str = Field(..., description="源节点 ID")
    target: str = Field(..., description="目标节点 ID")
    type: Literal["supports", "explains", "inferred_as", "leads_to", "simulated_by"] = Field(
        ..., description="边类型"
    )


class EvidenceChainSchema(BaseModel):
    """
    EvidenceChain 输出 Schema - DOC C C3.1。
    """

    version: str = Field(default="1.1", description="Schema 版本")
    id: str = Field(..., description="证据链 UUID")
    created_at: str = Field(..., description="ISO8601 UTC 时间戳")
    alert_id: str = Field(..., description="关联告警 ID")
    nodes: list[EvidenceNode] = Field(default_factory=list, description="证据节点")
    edges: list[EvidenceEdge] = Field(default_factory=list, description="证据边")

    class Config:
        from_attributes = True

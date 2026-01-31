"""
EvidenceChain schemas.
Strictly follows DOC C C3.1 EvidenceChain schema.
"""

from typing import Literal
from pydantic import BaseModel, Field


class EvidenceNode(BaseModel):
    """Node in evidence chain - DOC C C3.1."""
    id: str = Field(..., description="Node ID (e.g., alert:uuid, flow:uuid)")
    type: Literal["alert", "flow", "feature", "hypothesis", "action", "dryrun"] = Field(
        ..., description="Node type"
    )
    label: str = Field(..., description="Display label")


class EvidenceEdge(BaseModel):
    """Edge in evidence chain - DOC C C3.1."""
    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")
    type: Literal["supports", "explains", "inferred_as", "leads_to", "simulated_by"] = Field(
        ..., description="Edge type"
    )


class EvidenceChainSchema(BaseModel):
    """
    EvidenceChain output schema - DOC C C3.1.
    """

    version: str = Field(default="1.1", description="Schema version")
    id: str = Field(..., description="UUID of the evidence chain")
    created_at: str = Field(..., description="ISO8601 UTC timestamp")
    alert_id: str = Field(..., description="Related alert ID")
    nodes: list[EvidenceNode] = Field(default_factory=list, description="Evidence nodes")
    edges: list[EvidenceEdge] = Field(default_factory=list, description="Evidence edges")

    class Config:
        from_attributes = True

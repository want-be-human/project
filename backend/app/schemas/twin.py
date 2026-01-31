"""
Twin schemas: ActionPlan and DryRunResult.
Strictly follows DOC C C2.1 and C2.2 schemas.
"""

from typing import Any, Literal
from pydantic import BaseModel, Field


# Action target - DOC C C2.1
class ActionTarget(BaseModel):
    """Target specification for an action."""
    type: Literal["ip", "subnet", "service"] = Field(..., description="Target type")
    value: str = Field(..., description="Target value")


# Rollback action - DOC C C2.1
class RollbackAction(BaseModel):
    """Rollback specification for an action."""
    action_type: str = Field(..., description="Rollback action type")
    params: dict[str, Any] = Field(default_factory=dict, description="Rollback parameters")


# Single action in plan - DOC C C2.1
class PlanAction(BaseModel):
    """Single action in ActionPlan - DOC C C2.1."""
    action_type: Literal["block_ip", "isolate_host", "segment_subnet", "rate_limit_service"] = Field(
        ..., description="Action type"
    )
    target: ActionTarget = Field(..., description="Action target")
    params: dict[str, Any] = Field(default_factory=dict, description="Action parameters")
    rollback: RollbackAction | None = Field(default=None, description="Rollback action")


# ActionPlan schema - DOC C C2.1
class ActionPlanSchema(BaseModel):
    """
    ActionPlan output schema - DOC C C2.1.
    """

    version: str = Field(default="1.1", description="Schema version")
    id: str = Field(..., description="UUID of the plan")
    created_at: str = Field(..., description="ISO8601 UTC timestamp")
    alert_id: str = Field(..., description="Related alert ID")
    source: Literal["agent", "manual"] = Field(..., description="Plan source")
    actions: list[PlanAction] = Field(default_factory=list, description="Actions in plan")
    notes: str = Field(default="", description="Notes")

    class Config:
        from_attributes = True


# DryRunResult schemas - DOC C C2.2
class GraphHash(BaseModel):
    """Graph hash for before/after comparison."""
    graph_hash: str = Field(..., description="SHA256 hash of graph state")


class DryRunImpact(BaseModel):
    """Impact assessment from dry run - DOC C C2.2."""
    impacted_nodes_count: int = Field(..., description="Number of affected nodes")
    impacted_edges_count: int = Field(..., description="Number of affected edges")
    reachability_drop: float = Field(..., ge=0.0, le=1.0, description="Reachability reduction")
    service_disruption_risk: float = Field(..., ge=0.0, le=1.0, description="Service disruption risk")
    affected_services: list[str] = Field(default_factory=list, description="Affected services")
    warnings: list[str] = Field(default_factory=list, description="Warning messages")


class AlternativePath(BaseModel):
    """Alternative path found during dry run - DOC C C2.2."""
    source: str = Field(alias="from", description="Source node")  # 'from' is reserved
    to: str = Field(..., description="Destination node")
    path: list[str] = Field(default_factory=list, description="Path nodes")

    class Config:
        populate_by_name = True


class DryRunResultSchema(BaseModel):
    """
    DryRunResult output schema - DOC C C2.2.
    """

    version: str = Field(default="1.1", description="Schema version")
    id: str = Field(..., description="UUID of the dry run")
    created_at: str = Field(..., description="ISO8601 UTC timestamp")
    alert_id: str = Field(..., description="Related alert ID")
    plan_id: str = Field(..., description="Related plan ID")
    before: GraphHash = Field(..., description="Graph state before")
    after: GraphHash = Field(..., description="Graph state after")
    impact: DryRunImpact = Field(..., description="Impact assessment")
    alternative_paths: list[AlternativePath] = Field(default_factory=list, description="Alternative paths")
    explain: list[str] = Field(default_factory=list, description="Explanation text")

    class Config:
        from_attributes = True


# Create plan request - DOC C C6.8
class CreatePlanRequest(BaseModel):
    """Request for POST /twin/plans - DOC C C6.8."""
    alert_id: str = Field(..., description="Alert ID")
    source: Literal["agent", "manual"] = Field(..., description="Plan source")
    actions: list[PlanAction] = Field(..., description="Actions")
    notes: str = Field(default="", description="Notes")


# Dry run request - DOC C C6.8
class DryRunRequest(BaseModel):
    """Request for POST /twin/plans/{id}/dry-run - DOC C C6.8."""
    start: str | None = Field(default=None, description="Start time ISO8601")
    end: str | None = Field(default=None, description="End time ISO8601")
    mode: Literal["ip", "subnet"] = Field(default="ip", description="Graph mode")


# Query dry runs - DOC C C6.8
class DryRunQueryParams(BaseModel):
    """Query parameters for GET /twin/dry-runs."""
    alert_id: str | None = Field(default=None, description="Filter by alert ID")
    limit: int = Field(default=20, ge=1, le=100, description="Max results")

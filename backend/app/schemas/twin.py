"""
Twin schemas: ActionPlan and DryRunResult.
Strictly follows DOC C C2.1 and C2.2 schemas.
"""

from typing import Any, Literal
from pydantic import BaseModel, Field, AliasChoices, model_validator


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
        ...,
        description="Action type",
        validation_alias=AliasChoices("action_type", "type"),
    )
    target: ActionTarget = Field(..., description="Action target")
    params: dict[str, Any] = Field(default_factory=dict, description="Action parameters")
    rollback: RollbackAction | None = Field(default=None, description="Rollback action")

    # Optional fields populated by PlanCompiler (ignored during dry-run simulation)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="Compiler confidence score")
    derived_from_evidence: list[str] | None = Field(default=None, description="Evidence node IDs this action traces to")
    reasoning_summary: str | None = Field(default=None, description="Human-readable compilation reasoning")

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_payload(cls, data: Any) -> Any:
        """Normalize legacy frontend payloads to current schema."""
        if not isinstance(data, dict):
            return data

        action_type = data.get("action_type") or data.get("type")
        if action_type == "disable_user":
            # Legacy UI option; closest supported behavior in twin context.
            data["action_type"] = "isolate_host"
        elif action_type in {"block_ip", "isolate_host", "segment_subnet", "rate_limit_service"}:
            data["action_type"] = action_type
        elif not action_type:
            # Recommendation-style actions have no type; infer from title/steps.
            title = str(data.get("title", "")).lower()
            if "isolat" in title or "隔离" in title:
                data["action_type"] = "isolate_host"
            elif "segment" in title or "分段" in title:
                data["action_type"] = "segment_subnet"
            elif "rate" in title or "限流" in title or "限速" in title:
                data["action_type"] = "rate_limit_service"
            else:
                data["action_type"] = "block_ip"

        target = data.get("target")
        if isinstance(target, str):
            data["target"] = {"type": "ip", "value": target}
        elif isinstance(target, BaseModel):
            pass  # Already a validated Pydantic model, keep as-is
        elif not isinstance(target, dict):
            data["target"] = {"type": "ip", "value": "0.0.0.0"}
        else:
            target_type = target.get("type")
            target_value = target.get("value")
            if target_type not in {"ip", "subnet", "service"}:
                target["type"] = "ip"
            if not isinstance(target_value, str) or not target_value:
                target["value"] = "0.0.0.0"

        # Legacy recommendation rollback can be list[str]; ignore in plan schema.
        if isinstance(data.get("rollback"), list):
            data["rollback"] = None

        return data


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


# PlanCompiler request/response schemas
class CompilePlanRequest(BaseModel):
    """Request for POST /alerts/{id}/compile-plan."""
    recommendation_id: str | None = Field(default=None, description="Specific recommendation ID (uses latest if omitted)")
    language: Literal["zh", "en"] = Field(default="en", description="Output language")


class CompilationMetadata(BaseModel):
    """Metadata about the compilation process."""
    recommendation_id: str = Field(..., description="Source recommendation ID")
    rules_matched: int = Field(default=0, description="Number of rules matched")
    actions_skipped: int = Field(default=0, description="Number of non-compilable actions skipped")
    compiler_version: str = Field(default="1.0", description="Compiler version")


class CompilePlanResponse(BaseModel):
    """Response for POST /alerts/{id}/compile-plan."""
    plan: ActionPlanSchema = Field(..., description="Created action plan")
    compilation: CompilationMetadata = Field(..., description="Compilation metadata")

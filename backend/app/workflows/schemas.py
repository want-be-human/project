"""
Pydantic schemas for workflow execution traces.
Used for stage-level logging embedded in WorkflowExecution.stages_log JSON.
"""

from typing import Any, Literal
from pydantic import BaseModel, Field


class StageExecutionLog(BaseModel):
    """Single stage execution record, serialised into stages_log JSON."""

    stage_name: str = Field(..., description="Stage identifier")
    status: Literal["pending", "running", "completed", "failed", "skipped"] = Field(
        ..., description="Stage execution status"
    )
    started_at: str | None = Field(None, description="ISO8601 start time")
    completed_at: str | None = Field(None, description="ISO8601 end time")
    latency_ms: float | None = Field(None, description="Execution duration in ms")
    input_snapshot: dict[str, Any] = Field(default_factory=dict, description="Compact input summary")
    output_snapshot: dict[str, Any] = Field(default_factory=dict, description="Compact output summary")
    error: str | None = Field(None, description="Error message if failed")


class WorkflowExecutionSchema(BaseModel):
    """API-facing schema for workflow execution records."""

    version: str = Field(default="1.1")
    id: str
    alert_id: str
    workflow_type: str
    status: str
    created_at: str
    completed_at: str | None = None
    stages_log: list[StageExecutionLog] = Field(default_factory=list)

    class Config:
        from_attributes = True

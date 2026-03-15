"""
Pydantic schemas for pipeline observability API responses.
"""

from typing import Any

from pydantic import BaseModel, Field


class StageRecordSchema(BaseModel):
    """API-facing schema for a single pipeline stage record."""

    stage_name: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    latency_ms: float | None = None
    key_metrics: dict[str, Any] = Field(default_factory=dict)
    error_summary: str | None = None
    input_summary: dict[str, Any] = Field(default_factory=dict)
    output_summary: dict[str, Any] = Field(default_factory=dict)


class PipelineRunSchema(BaseModel):
    """API-facing schema for a complete pipeline run."""

    version: str = "1.1"
    id: str
    pcap_id: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    total_latency_ms: float | None = None
    stages: list[StageRecordSchema] = Field(default_factory=list)
    created_at: str | None = None

    class Config:
        from_attributes = True

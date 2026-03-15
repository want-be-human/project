"""
Pipeline stage definitions and data models.

Defines the 9-stage pipeline used by PipelineTracker to record
structured observability data for each PCAP processing run.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.utils import generate_uuid


class PipelineStage(str, Enum):
    """
    Named stages of the PCAP analysis pipeline.

    Stages 1-4 execute during background PCAP processing.
    Stages 5-8 execute on-demand when the user triggers agent analysis.
    Stage 9 executes when the topology/evidence API is called.
    """

    PARSE = "parse"
    FEATURE_EXTRACT = "feature_extract"
    DETECT = "detect"
    AGGREGATE = "aggregate"
    INVESTIGATE = "investigate"
    RECOMMEND = "recommend"
    COMPILE_PLAN = "compile_plan"
    DRY_RUN = "dry_run"
    VISUALIZE = "visualize"


# Ordered list for display / iteration purposes
PIPELINE_STAGE_ORDER: list[PipelineStage] = list(PipelineStage)

StageStatus = Literal["pending", "running", "completed", "failed", "skipped"]
RunStatus = Literal["pending", "running", "completed", "failed"]


class StageRecord(BaseModel):
    """Record for a single pipeline stage execution."""

    stage_name: str = Field(..., description="Stage identifier (PipelineStage value)")
    status: StageStatus = Field("pending", description="Execution status")
    started_at: str | None = Field(default=None, description="ISO8601 start time")
    completed_at: str | None = Field(default=None, description="ISO8601 end time")
    latency_ms: float | None = Field(default=None, description="Execution duration in ms")
    key_metrics: dict[str, Any] = Field(default_factory=dict, description="Stage-specific metrics")
    error_summary: str | None = Field(default=None, description="Error message if failed")
    input_summary: dict[str, Any] = Field(default_factory=dict, description="Compact input description")
    output_summary: dict[str, Any] = Field(default_factory=dict, description="Compact output description")


class PipelineRun(BaseModel):
    """Complete pipeline run covering all stages for a single PCAP."""

    version: str = Field(default="1.1")
    id: str = Field(default_factory=generate_uuid)
    pcap_id: str
    status: RunStatus = "pending"
    started_at: str | None = None
    completed_at: str | None = None
    total_latency_ms: float | None = None
    stages: list[StageRecord] = Field(default_factory=list)

    created_at: str | None = None

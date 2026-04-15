from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.utils import generate_uuid


class PipelineStage(str, Enum):
    # 1-4 在后台 PCAP 处理时执行；5-8 在智能体分析时按需执行；9 在调用拓扑/证据 API 时执行。
    PARSE = "parse"
    FEATURE_EXTRACT = "feature_extract"
    DETECT = "detect"
    AGGREGATE = "aggregate"
    INVESTIGATE = "investigate"
    RECOMMEND = "recommend"
    COMPILE_PLAN = "compile_plan"
    DRY_RUN = "dry_run"
    VISUALIZE = "visualize"


PIPELINE_STAGE_ORDER: list[PipelineStage] = list(PipelineStage)

StageStatus = Literal["pending", "running", "completed", "failed", "skipped"]
RunStatus = Literal["pending", "running", "completed", "failed"]


class StageRecord(BaseModel):
    stage_name: str
    status: StageStatus = "pending"
    started_at: str | None = None
    completed_at: str | None = None
    latency_ms: float | None = None
    key_metrics: dict[str, Any] = Field(default_factory=dict)
    error_summary: str | None = None
    input_summary: dict[str, Any] = Field(default_factory=dict)
    output_summary: dict[str, Any] = Field(default_factory=dict)


class PipelineRun(BaseModel):
    version: str = "1.1"
    id: str = Field(default_factory=generate_uuid)
    pcap_id: str
    status: RunStatus = "pending"
    started_at: str | None = None
    completed_at: str | None = None
    total_latency_ms: float | None = None
    stages: list[StageRecord] = Field(default_factory=list)
    created_at: str | None = None

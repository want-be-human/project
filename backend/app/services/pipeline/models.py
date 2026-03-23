"""
流水线阶段定义与数据模型。

定义 PipelineTracker 使用的 9 个阶段，
用于记录每次 PCAP 处理运行的结构化可观测数据。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.utils import generate_uuid


class PipelineStage(str, Enum):
    """
    PCAP 分析流水线的命名阶段。

    阶段 1-4 在后台 PCAP 处理时执行。
    阶段 5-8 在用户触发智能体分析时按需执行。
    阶段 9 在调用拓扑/证据 API 时执行。
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


# 供展示/遍历使用的有序阶段列表
PIPELINE_STAGE_ORDER: list[PipelineStage] = list(PipelineStage)

StageStatus = Literal["pending", "running", "completed", "failed", "skipped"]
RunStatus = Literal["pending", "running", "completed", "failed"]


class StageRecord(BaseModel):
    """单个流水线阶段执行记录。"""

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
    """覆盖单个 PCAP 全部阶段的完整流水线运行记录。"""

    version: str = Field(default="1.1")
    id: str = Field(default_factory=generate_uuid)
    pcap_id: str
    status: RunStatus = "pending"
    started_at: str | None = None
    completed_at: str | None = None
    total_latency_ms: float | None = None
    stages: list[StageRecord] = Field(default_factory=list)

    created_at: str | None = None

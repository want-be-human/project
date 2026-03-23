"""
流水线可观测性 API 响应的 Pydantic Schema。
"""

from typing import Any

from pydantic import BaseModel, Field


class StageRecordSchema(BaseModel):
    """面向 API 的单阶段流水线记录 Schema。"""

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
    """面向 API 的完整流水线运行 Schema。"""

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

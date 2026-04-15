from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ScenarioStage(str, Enum):
    LOAD_SCENARIO = "load_scenario"
    LOAD_ALERTS = "load_alerts"
    CHECK_ALERT_VOLUME = "check_alert_volume"
    CHECK_REQUIRED_PATTERNS = "check_required_patterns"
    CHECK_EVIDENCE_CHAIN = "check_evidence_chain"
    CHECK_DRY_RUN = "check_dry_run"
    CHECK_ENTITIES_AND_FEATURES = "check_entities_and_features"
    CHECK_PIPELINE_CONSTRAINTS = "check_pipeline_constraints"
    SUMMARIZE_RESULT = "summarize_result"


SCENARIO_STAGE_ORDER: list[ScenarioStage] = list(ScenarioStage)
TOTAL_STAGES = len(SCENARIO_STAGE_ORDER)


class FailureAttribution(BaseModel):
    check_name: str
    expected: Any
    actual: Any
    category: Literal["data_missing", "assertion_failed", "service_error", "timeout"]


class ScenarioStageRecord(BaseModel):
    stage_name: str
    status: Literal["pending", "running", "completed", "failed", "skipped"] = "pending"
    started_at: str | None = None
    completed_at: str | None = None
    latency_ms: float | None = None
    key_metrics: dict[str, Any] = Field(default_factory=dict)
    error_summary: str | None = None
    failure_attribution: FailureAttribution | None = None
    input_summary: dict[str, Any] = Field(default_factory=dict)
    output_summary: dict[str, Any] = Field(default_factory=dict)


class ScenarioRunTimeline(BaseModel):
    id: str
    scenario_id: str
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    started_at: str | None = None
    completed_at: str | None = None
    total_latency_ms: float | None = None
    validation_latency_ms: float | None = Field(
        default=None, description="阶段 1-8 耗时之和"
    )
    pipeline_latency_ms: float | None = Field(
        default=None, description="来自 PipelineRunModel"
    )
    stages: list[ScenarioStageRecord] = Field(default_factory=list)
    failed_stage: str | None = None

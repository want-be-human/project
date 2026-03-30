"""
场景运行服务层数据模型。

定义 ScenarioStage 枚举、ScenarioStageRecord、FailureAttribution 和 ScenarioRunTimeline，
供 ScenarioRunTracker 和 ScenariosService 使用。
"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ScenarioStage(str, Enum):
    """场景运行的 9 个执行阶段，顺序固定。"""

    LOAD_SCENARIO            = "load_scenario"
    LOAD_ALERTS              = "load_alerts"
    CHECK_ALERT_VOLUME       = "check_alert_volume"
    CHECK_REQUIRED_PATTERNS  = "check_required_patterns"
    CHECK_EVIDENCE_CHAIN     = "check_evidence_chain"
    CHECK_DRY_RUN            = "check_dry_run"
    CHECK_ENTITIES_AND_FEATURES = "check_entities_and_features"
    CHECK_PIPELINE_CONSTRAINTS  = "check_pipeline_constraints"
    SUMMARIZE_RESULT         = "summarize_result"


# 阶段执行顺序（用于排序和进度计算）
SCENARIO_STAGE_ORDER: list[ScenarioStage] = list(ScenarioStage)

# 总阶段数（常量，避免硬编码）
TOTAL_STAGES = len(SCENARIO_STAGE_ORDER)


class FailureAttribution(BaseModel):
    """结构化失败归因，精确描述哪个检查项失败及原因。"""

    check_name: str = Field(..., description="失败的检查项名称")
    expected: Any = Field(..., description="期望值")
    actual: Any = Field(..., description="实际值")
    category: Literal["data_missing", "assertion_failed", "service_error", "timeout"] = Field(
        ..., description="失败类别"
    )


class ScenarioStageRecord(BaseModel):
    """单个阶段的执行记录，与 pipeline StageRecord 结构对齐。"""

    stage_name: str = Field(..., description="阶段名称")
    status: Literal["pending", "running", "completed", "failed", "skipped"] = Field(
        default="pending", description="阶段状态"
    )
    started_at: str | None = Field(default=None, description="ISO8601 开始时间")
    completed_at: str | None = Field(default=None, description="ISO8601 完成时间")
    latency_ms: float | None = Field(default=None, description="阶段耗时（毫秒）")
    key_metrics: dict[str, Any] = Field(default_factory=dict, description="关键指标")
    error_summary: str | None = Field(default=None, description="错误摘要")
    failure_attribution: FailureAttribution | None = Field(
        default=None, description="结构化失败归因"
    )
    input_summary: dict[str, Any] = Field(default_factory=dict, description="输入摘要")
    output_summary: dict[str, Any] = Field(default_factory=dict, description="输出摘要")


class ScenarioRunTimeline(BaseModel):
    """场景运行完整时间线，汇总所有阶段结果和延迟指标。"""

    id: str = Field(..., description="运行 ID（与 ScenarioRun.id 一致）")
    scenario_id: str = Field(..., description="关联场景 ID")
    status: Literal["pending", "running", "completed", "failed"] = Field(
        default="pending", description="整体运行状态"
    )
    started_at: str | None = Field(default=None, description="ISO8601 运行开始时间")
    completed_at: str | None = Field(default=None, description="ISO8601 运行完成时间")
    total_latency_ms: float | None = Field(default=None, description="总耗时（毫秒）")
    validation_latency_ms: float | None = Field(
        default=None, description="校验耗时：阶段 1-8 耗时之和（毫秒）"
    )
    pipeline_latency_ms: float | None = Field(
        default=None, description="Pipeline 耗时：来自 PipelineRunModel（毫秒）"
    )
    stages: list[ScenarioStageRecord] = Field(default_factory=list, description="各阶段记录")
    failed_stage: str | None = Field(default=None, description="第一个失败阶段名称")

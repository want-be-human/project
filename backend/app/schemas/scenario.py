"""
Scenario 相关 Schema：Scenario 与 ScenarioRunResult。
严格遵循 DOC C C4.1 与 C4.2。
"""

from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from app.schemas.decision import DecisionValidation


# Scenario Schema（DOC C C4.1）
class ScenarioPcapRef(BaseModel):
    """场景中的 PCAP 引用。"""
    pcap_id: str = Field(..., description="PCAP 文件 ID")


class MustHaveExpectation(BaseModel):
    """场景中的必选期望项 - DOC C C4.1。"""
    type: str = Field(..., description="告警类型")
    severity_at_least: Literal["low", "medium", "high", "critical"] = Field(
        ..., description="最低严重等级"
    )


class ScenarioExpectations(BaseModel):
    """场景期望配置 - 完整 benchmark 规范。"""

    # 第一层：基础结果类
    min_alerts: int = Field(default=0, ge=0, description="最少告警数")
    max_alerts: int | None = Field(default=None, ge=0, description="最多告警数")
    exact_alerts: int | None = Field(default=None, ge=0, description="精确告警数（优先级高于 min/max）")
    min_high_severity_count: int = Field(default=0, ge=0, description="最少高危告警数")
    dry_run_required: bool = Field(default=False, description="是否要求 dry run")

    # 第二层：模式匹配类
    must_have: list[MustHaveExpectation] = Field(
        default_factory=list, description="必需告警模式"
    )
    forbidden_types: list[str] = Field(default_factory=list, description="禁止出现的告警类型")

    # 第三层：解释链与证据类
    evidence_chain_contains: list[str] = Field(
        default_factory=list, description="必需证据链节点"
    )
    required_entities: list[str] = Field(default_factory=list, description="必需实体（IP/service）")
    required_feature_names: list[str] = Field(default_factory=list, description="必需特征名")

    # 第四层：性能与稳定性类
    max_pipeline_latency_ms: float | None = Field(default=None, ge=0, description="最大 pipeline 耗时")
    max_validation_latency_ms: float | None = Field(default=None, ge=0, description="最大校验耗时")
    required_pipeline_stages: list[str] = Field(default_factory=list, description="必需 pipeline 阶段")
    no_failed_stages: bool = Field(default=False, description="不允许任何阶段失败")

    @model_validator(mode='after')
    def validate_alert_count_rules(self) -> 'ScenarioExpectations':
        """校验告警数规则冲突。"""
        if self.exact_alerts is not None:
            if self.min_alerts > 0 or self.max_alerts is not None:
                raise ValueError("exact_alerts 与 min_alerts/max_alerts 冲突，只能使用其一")
        if self.max_alerts is not None and self.min_alerts > self.max_alerts:
            raise ValueError("min_alerts 不能大于 max_alerts")
        return self

    @field_validator('forbidden_types', 'required_entities', 'required_feature_names', 'required_pipeline_stages')
    @classmethod
    def validate_no_empty_strings(cls, v: list[str]) -> list[str]:
        """禁止空字符串和重复项。"""
        if any(not s.strip() for s in v):
            raise ValueError("列表中不允许空字符串")
        if len(v) != len(set(v)):
            raise ValueError("列表中不允许重复项")
        return v


class ScenarioSchema(BaseModel):
    """
    场景输出 Schema - DOC C C4.1。
    """

    version: str = Field(default="1.1", description="Schema 版本")
    id: str = Field(..., description="场景 UUID")
    created_at: str = Field(..., description="ISO8601 UTC 时间戳")
    name: str = Field(..., description="场景名称")
    description: str = Field(default="", description="场景描述")
    status: Literal["active", "archived"] = Field(default="active", description="生命周期状态")
    pcap_ref: ScenarioPcapRef = Field(..., description="PCAP 引用")
    expectations: ScenarioExpectations = Field(..., description="场景期望")
    tags: list[str] = Field(default_factory=list, description="标签")

    class Config:
        from_attributes = True


# ScenarioRunResult Schema（DOC C C4.2）

# 结构化失败归因（新增）
class FailureAttribution(BaseModel):
    """结构化失败归因，精确描述哪个检查项失败及原因。"""
    check_name: str = Field(..., description="失败的检查项名称")
    expected: Any = Field(..., description="期望值")
    actual: Any = Field(..., description="实际值")
    category: Literal["data_missing", "assertion_failed", "service_error", "timeout"] = Field(
        ..., description="失败类别"
    )


# 阶段记录（新增）
class ScenarioStageRecordSchema(BaseModel):
    """单个阶段的执行记录，与 pipeline StageRecord 结构对齐。"""
    stage_name: str = Field(..., description="阶段名称")
    status: Literal["pending", "running", "completed", "failed", "skipped"] = Field(
        ..., description="阶段状态"
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


# 场景运行时间线（新增）
class ScenarioRunTimeline(BaseModel):
    """场景运行完整时间线，汇总所有阶段结果和延迟指标。"""
    id: str = Field(..., description="运行 ID（与 ScenarioRun.id 一致）")
    scenario_id: str = Field(..., description="关联场景 ID")
    status: Literal["pending", "running", "completed", "failed"] = Field(
        ..., description="整体运行状态"
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
    stages: list[ScenarioStageRecordSchema] = Field(default_factory=list, description="各阶段记录")
    failed_stage: str | None = Field(default=None, description="第一个失败阶段名称")


class ScenarioCheck(BaseModel):
    """场景运行中的单项检查结果 - DOC C C4.2。"""
    name: str = Field(..., description="检查项名称")
    pass_: bool = Field(alias="pass", description="是否通过")
    details: dict = Field(default_factory=dict, description="检查详情")

    class Config:
        populate_by_name = True


class ScenarioMetrics(BaseModel):
    """场景运行指标 - DOC C C4.2。"""
    alert_count: int = Field(default=0, description="告警总数")
    high_severity_count: int = Field(default=0, description="高严重等级告警数")
    avg_dry_run_risk: float = Field(default=0.0, description="平均 dry run 风险")
    # 延迟指标（拆分，不合并）
    validation_latency_ms: float | None = Field(default=None, description="校验耗时（毫秒）")
    pipeline_latency_ms: float | None = Field(default=None, description="Pipeline 耗时（毫秒）")


class ScenarioRunResultSchema(BaseModel):
    """
    场景运行结果输出 Schema - DOC C C4.2。
    """

    version: str = Field(default="1.1", description="Schema 版本")
    id: str = Field(..., description="运行结果 UUID")
    created_at: str = Field(..., description="ISO8601 UTC 时间戳")
    scenario_id: str = Field(..., description="关联场景 ID")
    status: Literal["pass", "fail"] = Field(..., description="整体状态")
    checks: list[ScenarioCheck] = Field(default_factory=list, description="检查结果")
    metrics: ScenarioMetrics = Field(default_factory=ScenarioMetrics, description="运行指标")
    timeline: ScenarioRunTimeline | None = Field(default=None, description="阶段时间线（新增）")
    # v1.2 决策校验结果（可选，向后兼容）
    decision_validation: DecisionValidation | None = Field(
        default=None, description="决策校验结果"
    )

    class Config:
        from_attributes = True


# 创建 scenario 请求 - DOC C C6.9
class CreateScenarioRequest(BaseModel):
    """POST /scenarios 请求体 - DOC C C6.9。"""
    name: str = Field(..., description="场景名称")
    description: str = Field(default="", description="描述")
    pcap_ref: ScenarioPcapRef = Field(..., description="PCAP 引用")
    expectations: ScenarioExpectations = Field(..., description="期望配置")
    tags: list[str] = Field(default_factory=list, description="标签")


# Scenario 查询参数
class ScenarioQueryParams(BaseModel):
    """GET /scenarios 查询参数。"""
    limit: int = Field(default=50, ge=1, le=1000, description="最大结果数")
    offset: int = Field(default=0, ge=0, description="分页偏移量")

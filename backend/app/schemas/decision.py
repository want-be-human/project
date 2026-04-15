"""
决策结果相关 Schema：动作原语、三段式决策结果。
为 dry-run/scenario 提供"会建议、会比较、会回退"的决策能力。
"""

from typing import Any, Literal
from pydantic import BaseModel, Field

class RiskProfile(BaseModel):
    """动作的风险画像。"""
    disruption_level: Literal["none", "low", "medium", "high", "critical"] = Field(
        ..., description="中断等级"
    )
    scope: Literal["single_host", "subnet", "service", "network_wide"] = Field(
        ..., description="影响范围"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="置信度")
    affected_services_count: int = Field(default=0, ge=0, description="受影响服务数量")
    affected_nodes_count: int = Field(default=0, ge=0, description="受影响节点数量")


class RollbackTemplate(BaseModel):
    """回滚模板，描述如何撤销某个动作。"""
    action_type: str = Field(..., description="回滚动作类型")
    params: dict[str, Any] = Field(default_factory=dict, description="回滚参数")
    description: str = Field(..., description="回滚操作描述")


class DecisionAction(BaseModel):
    """
    统一的动作原语模型。
    不与特定厂商设备耦合，便于后续扩展。
    """
    action_type: str = Field(
        ...,
        description="动作类型：block_ip / rate_limit / isolate_host / block_port / apply_acl_rule / monitor_only",
    )
    params: dict[str, Any] = Field(default_factory=dict, description="动作参数")
    expected_effect: str = Field(..., description="预期效果描述")
    risk_profile: RiskProfile = Field(..., description="风险画像")
    reversible: bool = Field(..., description="是否可逆")
    rollback_template: RollbackTemplate | None = Field(
        default=None, description="回滚模板（不可逆动作为 None）"
    )
    estimated_recovery_cost: Literal["none", "low", "medium", "high"] = Field(
        default="low", description="估算恢复成本"
    )


class RollbackPlan(BaseModel):
    """
    回退计划，描述如何撤销推荐动作。
    无论是否可逆都会返回，不可逆时给出原因。
    """
    rollback_supported: bool = Field(..., description="是否支持回退")
    rollback_steps: list[str] = Field(default_factory=list, description="回退步骤")
    rollback_risk: Literal["none", "low", "medium", "high"] = Field(
        default="low", description="回退操作自身的风险"
    )
    rollback_complexity: Literal["trivial", "simple", "moderate", "complex"] = Field(
        default="simple", description="回退操作复杂度"
    )
    estimated_duration: str | None = Field(
        default=None, description="预计回退耗时（如 '< 5min'）"
    )
    simulate_rollback_result: dict[str, Any] | None = Field(
        default=None, description="回退模拟结果（可选）"
    )
    not_supported_reason: str | None = Field(
        default=None, description="不支持回退的原因（当 rollback_supported=False 时必填）"
    )

class RecommendedDecision(BaseModel):
    """首选推荐动作及推理依据。"""
    action: DecisionAction = Field(..., description="推荐的动作")
    reasoning: str = Field(..., description="推荐理由")
    based_on: list[str] = Field(
        default_factory=list,
        description="决策依据（如 alert 类型、拓扑影响、dry-run 结果等）",
    )


class SaferAlternative(BaseModel):
    """更安全的替代方案，当首选动作风险较高时提供。"""
    action: DecisionAction = Field(..., description="替代动作")
    safer_because: str = Field(..., description="比主方案安全在哪里")
    tradeoff: str = Field(..., description="代价是什么")
    trigger_reason: str = Field(..., description="什么条件触发了该替代方案")


class ActionComparison(BaseModel):
    """首选方案与替代方案的结构化对比。"""
    disruption_diff: str = Field(..., description="影响差异描述")
    coverage_diff: str = Field(..., description="覆盖范围差异")
    reversibility_diff: str = Field(..., description="可逆性差异")
    recommendation: str = Field(..., description="最终建议选哪个")


class DecisionResult(BaseModel):
    """
    三段式决策结果：推荐动作 + 更安全替代 + 回退计划。
    嵌入到 DryRunResultSchema 中，为 dry-run 评估增加决策能力。
    """
    recommended_action: RecommendedDecision = Field(..., description="首选推荐动作")
    safer_alternative: SaferAlternative | None = Field(
        default=None, description="更安全的替代方案（当首选方案风险较高时）"
    )
    rollback_plan: RollbackPlan = Field(..., description="首选动作的回退计划")
    safer_alternative_rollback: RollbackPlan | None = Field(
        default=None, description="替代方案的回退计划"
    )
    decision_summary: str = Field(..., description="一句话概括决策逻辑")
    comparison: ActionComparison | None = Field(
        default=None, description="首选方案与替代方案的对比"
    )

class DecisionValidation(BaseModel):
    """场景执行时对决策结果的校验。"""
    has_decision: bool = Field(..., description="dry-run 是否包含决策结果")
    rollback_validated: bool = Field(
        default=False, description="回退计划是否经过校验"
    )
    rollback_simulation_passed: bool | None = Field(
        default=None, description="回退模拟是否通过（未模拟时为 None）"
    )
    validation_notes: list[str] = Field(
        default_factory=list, description="校验备注"
    )

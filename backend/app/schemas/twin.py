"""
Twin 相关 Schema：ActionPlan 与 DryRunResult。
严格遵循 DOC C C2.1 与 C2.2。
"""

from typing import Any, Literal
from pydantic import BaseModel, Field, AliasChoices, model_validator


# Action 目标 - DOC C C2.1
class ActionTarget(BaseModel):
    """动作目标定义。"""
    type: Literal["ip", "subnet", "service"] = Field(..., description="目标类型")
    value: str = Field(..., description="目标值")


# 回滚动作 - DOC C C2.1
class RollbackAction(BaseModel):
    """动作回滚定义。"""
    action_type: str = Field(..., description="回滚动作类型")
    params: dict[str, Any] = Field(default_factory=dict, description="回滚参数")


# 方案中的单个 action - DOC C C2.1
class PlanAction(BaseModel):
    """动作方案中的单个动作 - DOC C C2.1。"""
    action_type: Literal["block_ip", "isolate_host", "segment_subnet", "rate_limit_service"] = Field(
        ...,
        description="动作类型",
        validation_alias=AliasChoices("action_type", "type"),
    )
    target: ActionTarget = Field(..., description="动作目标")
    params: dict[str, Any] = Field(default_factory=dict, description="动作参数")
    rollback: RollbackAction | None = Field(default=None, description="回滚动作")

    # PlanCompiler 填充的可选字段（dry-run 仿真时忽略）
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="编译器置信度")
    derived_from_evidence: list[str] | None = Field(default=None, description="该动作可追溯的证据节点 ID")
    reasoning_summary: str | None = Field(default=None, description="可读的编译推理说明")

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_payload(cls, data: Any) -> Any:
        """将旧版前端载荷规范化到当前 Schema。"""
        if not isinstance(data, dict):
            return data

        action_type = data.get("action_type") or data.get("type")
        if action_type == "disable_user":
            # 旧版 UI 选项；在 twin 语境下映射到最接近的受支持行为。
            data["action_type"] = "isolate_host"
        elif action_type in {"block_ip", "isolate_host", "segment_subnet", "rate_limit_service"}:
            data["action_type"] = action_type
        elif not action_type:
            # Recommendation 风格 action 无 type；从 title/steps 推断。
            title = str(data.get("title", "")).lower()
            if "isolat" in title or "隔离" in title:
                data["action_type"] = "isolate_host"
            elif "segment" in title or "分段" in title:
                data["action_type"] = "segment_subnet"
            elif "rate" in title or "限流" in title or "限速" in title:
                data["action_type"] = "rate_limit_service"
            else:
                data["action_type"] = "block_ip"

        target = data.get("target")
        if isinstance(target, str):
            data["target"] = {"type": "ip", "value": target}
        elif isinstance(target, BaseModel):
            pass  # 已是通过校验的 Pydantic 模型，保持不变
        elif not isinstance(target, dict):
            data["target"] = {"type": "ip", "value": "0.0.0.0"}
        else:
            target_type = target.get("type")
            target_value = target.get("value")
            if target_type not in {"ip", "subnet", "service"}:
                target["type"] = "ip"
            if not isinstance(target_value, str) or not target_value:
                target["value"] = "0.0.0.0"

        # 旧版 recommendation 的 rollback 可能是 list[str]；在 plan schema 中忽略。
        if isinstance(data.get("rollback"), list):
            data["rollback"] = None

        return data


# ActionPlan Schema（DOC C C2.1）
class ActionPlanSchema(BaseModel):
    """
    ActionPlan 输出模式 - DOC C C2.1。
    """

    version: str = Field(default="1.1", description="模式版本")
    id: str = Field(..., description="方案 UUID")
    created_at: str = Field(..., description="ISO8601 UTC 时间戳")
    alert_id: str = Field(..., description="关联告警 ID")
    source: Literal["agent", "manual"] = Field(..., description="方案来源")
    actions: list[PlanAction] = Field(default_factory=list, description="方案动作列表")
    notes: str = Field(default="", description="备注")

    class Config:
        from_attributes = True


# DryRunResult Schema（DOC C C2.2）
class GraphHash(BaseModel):
    """用于前后对比的图状态哈希。"""
    graph_hash: str = Field(..., description="图状态的 SHA256 哈希")


class DryRunImpact(BaseModel):
    """演练影响评估 - DOC C C2.2。"""
    impacted_nodes_count: int = Field(..., description="受影响节点数量")
    impacted_edges_count: int = Field(..., description="受影响边数量")
    reachability_drop: float = Field(..., ge=0.0, le=1.0, description="可达性下降幅度")
    service_disruption_risk: float = Field(..., ge=0.0, le=1.0, description="服务中断风险")
    affected_services: list[str] = Field(default_factory=list, description="受影响服务")
    warnings: list[str] = Field(default_factory=list, description="告警提示")


class AlternativePath(BaseModel):
    """演练过程中发现的替代路径 - DOC C C2.2。"""
    source: str = Field(alias="from", description="源节点")  # 'from' 为保留字
    to: str = Field(..., description="目标节点")
    path: list[str] = Field(default_factory=list, description="路径节点列表")

    class Config:
        populate_by_name = True


class DryRunResultSchema(BaseModel):
    """
    DryRunResult 输出模式 - DOC C C2.2。
    """

    version: str = Field(default="1.1", description="模式版本")
    id: str = Field(..., description="dry-run UUID")
    created_at: str = Field(..., description="ISO8601 UTC 时间戳")
    alert_id: str = Field(..., description="关联告警 ID")
    plan_id: str = Field(..., description="关联方案 ID")
    before: GraphHash = Field(..., description="变更前图状态")
    after: GraphHash = Field(..., description="变更后图状态")
    impact: DryRunImpact = Field(..., description="影响评估")
    alternative_paths: list[AlternativePath] = Field(default_factory=list, description="替代路径列表")
    explain: list[str] = Field(default_factory=list, description="解释文本")

    class Config:
        from_attributes = True


# 创建 plan 请求 - DOC C C6.8
class CreatePlanRequest(BaseModel):
    """创建计划接口请求体 - DOC C C6.8。"""
    alert_id: str = Field(..., description="告警 ID")
    source: Literal["agent", "manual"] = Field(..., description="方案来源")
    actions: list[PlanAction] = Field(..., description="动作列表")
    notes: str = Field(default="", description="备注")


# dry run 请求 - DOC C C6.8
class DryRunRequest(BaseModel):
    """执行演练接口请求体 - DOC C C6.8。"""
    start: str | None = Field(default=None, description="开始时间（ISO8601）")
    end: str | None = Field(default=None, description="结束时间（ISO8601）")
    mode: Literal["ip", "subnet"] = Field(default="ip", description="图模式")


# 查询 dry runs - DOC C C6.8
class DryRunQueryParams(BaseModel):
    """查询演练结果的参数。"""
    alert_id: str | None = Field(default=None, description="按告警 ID 过滤")
    limit: int = Field(default=20, ge=1, le=100, description="最大返回数量")


# 计划编译请求/响应 Schema
class CompilePlanRequest(BaseModel):
    """编译计划接口请求体。"""
    recommendation_id: str | None = Field(default=None, description="指定 recommendation ID（为空时使用最新）")
    language: Literal["zh", "en"] = Field(default="en", description="输出语言")


class CompilationMetadata(BaseModel):
    """编译过程元数据。"""
    recommendation_id: str = Field(..., description="来源 recommendation ID")
    rules_matched: int = Field(default=0, description="命中规则数量")
    actions_skipped: int = Field(default=0, description="被跳过的不可编译动作数量")
    compiler_version: str = Field(default="1.0", description="编译器版本")


class CompilePlanResponse(BaseModel):
    """编译计划接口响应体。"""
    plan: ActionPlanSchema = Field(..., description="已创建的动作方案")
    compilation: CompilationMetadata = Field(..., description="编译元数据")

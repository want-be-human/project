"""
Twin 相关 Schema：ActionPlan 与 DryRunResult。
严格遵循 DOC C C2.1 与 C2.2。
v1.2: 数据驱动影响评估扩展 — 多维可达性、风险分解、结构化解释。
"""

from typing import Any, Literal
from pydantic import BaseModel, Field, AliasChoices, model_validator
from app.schemas.topology import GraphResponseSchema
from app.schemas.decision import DecisionResult


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


# ══════════════════════════════════════════════════════════════
# DryRunResult Schema（DOC C C2.2，v1.2 数据驱动扩展）
# ══════════════════════════════════════════════════════════════

class GraphHash(BaseModel):
    """用于前后对比的图状态哈希。"""
    graph_hash: str = Field(..., description="图状态的 SHA256 哈希")


# ── 多维可达性指标 ──────────────────────────────────────────

class PairReachabilityMetric(BaseModel):
    """源-目标对可达性指标。"""
    source: str = Field(..., description="源节点 ID")
    target: str = Field(..., description="目标节点 ID")
    reachable_before: bool = Field(..., description="变更前是否可达")
    reachable_after: bool = Field(..., description="变更后是否可达")
    protocols: list[str] = Field(default_factory=list, description="该对涉及的协议/端口")


class ReachabilityDetail(BaseModel):
    """多维可达性分解。"""
    pair_reachability_drop: float = Field(..., ge=0.0, le=1.0, description="源-目标对可达性损失率")
    service_reachability_drop: float = Field(..., ge=0.0, le=1.0, description="按服务维度可达性损失率")
    subnet_reachability_drop: float = Field(..., ge=0.0, le=1.0, description="按子网对可达性损失率")
    pair_metrics: list[PairReachabilityMetric] = Field(default_factory=list, description="逐对可达性明细")


# ── 逐服务影响明细 ──────────────────────────────────────────

class ImpactedServiceDetail(BaseModel):
    """单个受影响服务的详细分解。"""
    service: str = Field(..., description="协议/端口，如 tcp/22")
    importance_weight: float = Field(..., ge=0.0, le=1.0, description="服务重要性权重")
    affected_edge_count: int = Field(default=0, description="受影响边数量")
    affected_node_count: int = Field(default=0, description="受影响节点数量")
    traffic_proportion: float = Field(default=0.0, ge=0.0, le=1.0, description="该服务在当前时间窗口的流量占比")
    alert_severity_stats: dict[str, int] = Field(default_factory=dict, description="关联告警严重等级统计")
    risk_contribution: float = Field(default=0.0, description="对总风险的贡献值")


# ── 服务风险分解 ────────────────────────────────────────────

class ServiceRiskBreakdown(BaseModel):
    """服务中断风险的数据驱动分解。"""
    weighted_service_score: float = Field(..., ge=0.0, le=1.0, description="加权服务重要性得分")
    node_impact_score: float = Field(..., ge=0.0, le=1.0, description="节点影响得分")
    edge_impact_score: float = Field(..., ge=0.0, le=1.0, description="边影响得分")
    alert_severity_score: float = Field(..., ge=0.0, le=1.0, description="告警严重等级得分")
    traffic_proportion_score: float = Field(..., ge=0.0, le=1.0, description="流量占比得分")
    historical_score: float = Field(default=0.0, ge=0.0, le=1.0, description="历史演练/场景得分")
    composite_risk: float = Field(..., ge=0.0, le=1.0, description="综合风险值")


# ── 结构化解释（面向研究报告）──────────────────────────────

class ExplainSection(BaseModel):
    """结构化解释段落，适用于研究报告引用。"""
    section: str = Field(..., description="段落类型：affected_objects / impact_reason / metric_changes / risk_judgment / recommended_actions")
    title: str = Field(..., description="段落标题")
    content: list[str] = Field(default_factory=list, description="段落内容条目")


# ── 影响评估主模型 ──────────────────────────────────────────

class DryRunImpact(BaseModel):
    """演练影响评估 - DOC C C2.2（v1.2 数据驱动扩展）。"""

    # ── 保留原有字段（向后兼容）──
    impacted_nodes_count: int = Field(..., description="受影响节点数量")
    impacted_edges_count: int = Field(..., description="受影响边数量")
    reachability_drop: float = Field(..., ge=0.0, le=1.0, description="可达性下降幅度（兼容旧版，取 pair_reachability_drop）")
    service_disruption_risk: float = Field(..., ge=0.0, le=1.0, description="服务中断风险（兼容旧版，取 composite_risk）")
    affected_services: list[str] = Field(default_factory=list, description="受影响服务列表")
    warnings: list[str] = Field(default_factory=list, description="告警提示")

    # ── 新增：对象 ID 集合 ──
    removed_node_ids: list[str] = Field(default_factory=list, description="被移除的节点 ID")
    removed_edge_ids: list[str] = Field(default_factory=list, description="被移除的边 ID")
    affected_node_ids: list[str] = Field(default_factory=list, description="受波及的邻居节点 ID")
    affected_edge_ids: list[str] = Field(default_factory=list, description="受波及的邻居边 ID")

    # ── 新增：多维可达性 ──
    reachability_detail: ReachabilityDetail | None = Field(default=None, description="多维可达性分解")

    # ── 新增：逐服务影响明细 ──
    impacted_services: list[ImpactedServiceDetail] = Field(default_factory=list, description="逐服务影响明细")

    # ── 新增：风险分解 ──
    service_risk_breakdown: ServiceRiskBreakdown | None = Field(default=None, description="服务风险数据驱动分解")

    # ── 新增：置信度 ──
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="评估置信度")

    # ── 新增：节点/边级增量（供前端 diff 视图使用）──
    node_risk_deltas: dict[str, float] = Field(
        default_factory=dict,
        description="节点级风险变化：nodeId → 动作后新风险值",
    )
    edge_weight_deltas: dict[str, int] = Field(
        default_factory=dict,
        description="边级权重变化：edgeId → 动作后新权重",
    )


class AlternativePath(BaseModel):
    """演练过程中发现的可能绕行路径 - DOC C C2.2。"""
    source: str = Field(alias="from", description="源节点")  # 'from' 为保留字
    to: str = Field(..., description="目标节点")
    path: list[str] = Field(default_factory=list, description="路径节点列表")

    class Config:
        populate_by_name = True


class DryRunResultSchema(BaseModel):
    """
    DryRunResult 输出模式 - DOC C C2.2（v1.2 数据驱动扩展）。
    """

    version: str = Field(default="1.2", description="模式版本")
    id: str = Field(..., description="dry-run UUID")
    created_at: str = Field(..., description="ISO8601 UTC 时间戳")
    alert_id: str = Field(..., description="关联告警 ID")
    plan_id: str = Field(..., description="关联方案 ID")
    before: GraphHash = Field(..., description="变更前图状态")
    after: GraphHash = Field(..., description="变更后图状态")
    graph_before: GraphResponseSchema | None = Field(
        default=None,
        description="变更前的完整图结构（用于前端 before/diff 视图渲染）",
    )
    graph_after: GraphResponseSchema | None = Field(
        default=None,
        description="变更后的完整图结构（用于前端 after 视图渲染）",
    )
    # dry-run 执行时的时间窗口参数（前端跳转和快照回放用）
    dry_run_start: str | None = Field(default=None, description="dry-run 时间窗口起始（ISO8601 UTC）")
    dry_run_end: str | None = Field(default=None, description="dry-run 时间窗口结束（ISO8601 UTC）")
    dry_run_mode: str | None = Field(default=None, description="dry-run 图模式（ip/subnet）")
    impact: DryRunImpact = Field(..., description="影响评估")
    alternative_paths: list[AlternativePath] = Field(default_factory=list, description="可能绕行路径列表")
    explain: list[str] = Field(default_factory=list, description="解释文本（兼容旧版）")
    explain_sections: list[ExplainSection] = Field(default_factory=list, description="结构化解释段落")
    # v1.3 三段式决策结果（可选，向后兼容）
    decision: DecisionResult | None = Field(default=None, description="三段式决策结果")

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


class SkippedAction(BaseModel):
    """描述编译过程中被跳过的推荐动作。"""
    title: str = Field(..., description="原始动作标题")
    reason: str = Field(..., description="跳过原因")
    action_intent: str = Field(default="unknown", description="动作声明的意图分类")
    suggestion: str = Field(default="", description="用户可采取的下一步建议")


class CompilationMetadata(BaseModel):
    """编译过程元数据。"""
    recommendation_id: str = Field(..., description="来源 recommendation ID")
    rules_matched: int = Field(default=0, description="命中规则数量")
    actions_skipped: int = Field(default=0, description="被跳过的不可编译动作数量")
    compiler_version: str = Field(default="1.0", description="编译器版本")
    skipped_actions: list[SkippedAction] = Field(default_factory=list, description="被跳过动作的详细信息")
    all_skipped: bool = Field(default=False, description="是否所有推荐动作均被跳过")
    empty_reason: str | None = Field(default=None, description="当 all_skipped=True 时的解释说明")


class CompilePlanResponse(BaseModel):
    """编译计划接口响应体。"""
    plan: ActionPlanSchema = Field(..., description="已创建的动作方案")
    compilation: CompilationMetadata = Field(..., description="编译元数据")

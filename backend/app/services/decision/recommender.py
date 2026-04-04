"""
决策推荐引擎。
基于 alert 信息、dry-run 影响评估和 plan 动作，
生成三段式决策结果：推荐动作 + 更安全替代 + 回退计划。
"""

from app.core.logging import get_logger
from app.schemas.decision import (
    DecisionResult,
    RecommendedDecision,
    SaferAlternative,
    ActionComparison,
    RollbackPlan,
    DecisionAction,
)
from app.schemas.twin import DryRunResultSchema
from app.services.decision.action_registry import (
    PLAN_ACTION_MAPPING,
    build_decision_action,
    get_safer_action_type,
)

logger = get_logger(__name__)

# 触发 safer_alternative 的阈值
_DISRUPTION_RISK_THRESHOLD = 0.5   # composite_risk 超过此值时生成替代方案
_CONFIDENCE_THRESHOLD = 0.6        # 置信度低于此值时生成替代方案


class DecisionRecommender:
    """
    三段式决策推荐引擎。

    输入：alert 信息、dry-run 结果、plan 动作列表
    输出：DecisionResult（推荐动作 + 更安全替代 + 回退计划）
    """

    def recommend(
        self,
        alert_severity: str,
        alert_type: str,
        dry_run_result: DryRunResultSchema,
        plan_actions: list[dict],
    ) -> DecisionResult:
        """
        生成三段式决策结果。

        Args:
            alert_severity: 告警严重等级
            alert_type: 告警类型
            dry_run_result: dry-run 影响评估结果
            plan_actions: plan 中的动作列表（dict 格式）

        Returns:
            DecisionResult
        """
        impact = dry_run_result.impact
        composite_risk = impact.service_disruption_risk
        confidence = impact.confidence
        affected_services = impact.affected_services or []
        affected_nodes_count = impact.impacted_nodes_count

        # 1. 选择首选动作
        primary_action, primary_params = self._select_primary_action(
            plan_actions, alert_severity, alert_type,
        )

        # 2. 构建首选 DecisionAction
        recommended_da = build_decision_action(
            action_type=primary_action,
            params=primary_params,
            confidence=confidence,
            affected_services_count=len(affected_services),
            affected_nodes_count=affected_nodes_count,
        )

        # 3. 构建推荐理由
        reasoning, based_on = self._build_reasoning(
            primary_action, alert_severity, alert_type,
            composite_risk, confidence, affected_services,
        )

        recommended = RecommendedDecision(
            action=recommended_da,
            reasoning=reasoning,
            based_on=based_on,
        )

        # 4. 判断是否需要 safer_alternative
        needs_alternative = self._needs_safer_alternative(
            recommended_da, composite_risk, confidence,
        )

        safer_alt = None
        safer_alt_rollback = None
        comparison = None

        if needs_alternative:
            safer_alt, safer_alt_rollback, comparison = self._build_safer_alternative(
                recommended_da, composite_risk, confidence,
                primary_params, affected_services, affected_nodes_count,
            )

        # 5. 构建首选动作的回退计划
        rollback_plan = self._build_rollback_plan(recommended_da)

        # 6. 构建决策摘要
        summary = self._build_summary(
            recommended_da, safer_alt, composite_risk, confidence,
        )

        return DecisionResult(
            recommended_action=recommended,
            safer_alternative=safer_alt,
            rollback_plan=rollback_plan,
            safer_alternative_rollback=safer_alt_rollback,
            decision_summary=summary,
            comparison=comparison,
        )

    # ══════════════════════════════════════════════════════════
    # 内部方法
    # ══════════════════════════════════════════════════════════

    def _select_primary_action(
        self,
        plan_actions: list[dict],
        alert_severity: str,
        alert_type: str,
    ) -> tuple[str, dict]:
        """
        从 plan_actions 中选择首选动作。

        优先选择 plan_actions 中的第一个动作（已按优先级排序），
        并映射到决策引擎的动作类型。
        如果 plan_actions 为空，根据 alert 信息降级。
        """
        if not plan_actions:
            # 无动作可选，降级到 monitor_only
            return "monitor_only", {}

        first = plan_actions[0]
        raw_type = first.get("action_type", "")
        target = first.get("target", {})
        params = first.get("params", {})

        # 将 target 信息合入 params
        if isinstance(target, dict):
            params["target_type"] = target.get("type", "ip")
            params["target_value"] = target.get("value", "")

        # 映射动作类型
        mapped_type = PLAN_ACTION_MAPPING.get(raw_type, "monitor_only")

        return mapped_type, params

    def _build_reasoning(
        self,
        action_type: str,
        alert_severity: str,
        alert_type: str,
        composite_risk: float,
        confidence: float,
        affected_services: list[str],
    ) -> tuple[str, list[str]]:
        """构建推荐理由和决策依据。"""
        based_on = []
        reasons = []

        # 基于告警类型
        based_on.append(f"告警类型: {alert_type}")
        reasons.append(f"检测到 {alert_type} 类型告警")

        # 基于告警严重度
        based_on.append(f"告警严重度: {alert_severity}")
        severity_desc = {"critical": "极高", "high": "高", "medium": "中", "low": "低"}
        reasons.append(f"严重等级为{severity_desc.get(alert_severity, '中')}")

        # 基于影响评估
        based_on.append(f"综合风险: {composite_risk:.2f}")
        risk_level = "低" if composite_risk < 0.3 else "中" if composite_risk < 0.7 else "高"
        reasons.append(f"dry-run 评估综合风险为{risk_level}（{composite_risk:.2f}）")

        # 基于受影响服务
        if affected_services:
            based_on.append(f"受影响服务: {', '.join(affected_services[:3])}")

        # 基于置信度
        based_on.append(f"评估置信度: {confidence:.2f}")

        # 组装推荐理由
        action_desc = {
            "block_ip": "封锁源 IP",
            "rate_limit": "对目标流量限速",
            "isolate_host": "隔离可疑主机",
            "block_port": "封锁风险端口",
            "apply_acl_rule": "应用 ACL 规则",
            "monitor_only": "仅加强监控",
        }
        desc = action_desc.get(action_type, action_type)
        reasoning = (
            f"推荐执行「{desc}」。{'; '.join(reasons)}。"
            f"该动作在当前场景下可有效遏制威胁"
            f"{'且回退成本可控' if action_type != 'isolate_host' else '，但影响范围较大，请确认后执行'}。"
        )

        return reasoning, based_on

    def _needs_safer_alternative(
        self,
        action: DecisionAction,
        composite_risk: float,
        confidence: float,
    ) -> bool:
        """判断是否需要生成更安全的替代方案。"""
        # 条件 1：disruption risk 较高
        if composite_risk > _DISRUPTION_RISK_THRESHOLD:
            return True

        # 条件 2：置信度不足
        if confidence < _CONFIDENCE_THRESHOLD:
            return True

        # 条件 3：动作不可逆（虽然当前所有动作都可逆，但预留扩展）
        if not action.reversible:
            return True

        # 条件 4：动作侵入性高（isolate_host）
        if action.risk_profile.disruption_level in ("high", "critical"):
            return True

        return False

    def _build_safer_alternative(
        self,
        primary_action: DecisionAction,
        composite_risk: float,
        confidence: float,
        params: dict,
        affected_services: list[str],
        affected_nodes_count: int,
    ) -> tuple[SaferAlternative, RollbackPlan, ActionComparison]:
        """构建更安全的替代方案。"""
        # 确定替代动作类型
        safer_type = get_safer_action_type(primary_action.action_type)

        # 构建替代 DecisionAction
        safer_da = build_decision_action(
            action_type=safer_type,
            params=params,
            confidence=confidence,
            affected_services_count=len(affected_services),
            affected_nodes_count=affected_nodes_count,
        )

        # 构建 trigger_reason
        trigger_reasons = []
        if composite_risk > _DISRUPTION_RISK_THRESHOLD:
            trigger_reasons.append(f"综合风险 {composite_risk:.2f} 超过阈值 {_DISRUPTION_RISK_THRESHOLD}")
        if confidence < _CONFIDENCE_THRESHOLD:
            trigger_reasons.append(f"评估置信度 {confidence:.2f} 低于阈值 {_CONFIDENCE_THRESHOLD}")
        if primary_action.risk_profile.disruption_level in ("high", "critical"):
            trigger_reasons.append(f"首选动作中断等级为 {primary_action.risk_profile.disruption_level}")
        if not primary_action.reversible:
            trigger_reasons.append("首选动作不可逆")

        # 构建 safer_because
        safer_desc = {
            "monitor_only": "仅增加监控，不产生任何业务中断",
            "rate_limit": "通过限速降低威胁流量，同时保留基本连通性",
            "block_port": "仅封锁特定端口，影响范围小于全面封锁",
            "block_ip": "仅封锁单个 IP，不影响其他主机",
            "apply_acl_rule": "通过细粒度规则控制流量，比全面隔离更精细",
        }
        safer_because = safer_desc.get(
            safer_type,
            f"{safer_type} 的中断等级低于 {primary_action.action_type}",
        )

        # 构建 tradeoff
        tradeoff_desc = {
            "monitor_only": "不能主动阻止攻击，仅依赖后续人工响应",
            "rate_limit": "无法完全阻止恶意流量，攻击者仍有部分带宽可用",
            "block_port": "可能影响使用同一端口的合法服务",
            "block_ip": "可能存在 IP 欺骗或共享 IP 的情况",
            "apply_acl_rule": "ACL 规则可能需要人工调优，维护成本较高",
        }
        tradeoff = tradeoff_desc.get(
            safer_type,
            f"保护力度低于 {primary_action.action_type}",
        )

        safer_alt = SaferAlternative(
            action=safer_da,
            safer_because=safer_because,
            tradeoff=tradeoff,
            trigger_reason="; ".join(trigger_reasons),
        )

        # 替代方案的回退计划
        safer_rollback = self._build_rollback_plan(safer_da)

        # 构建对比
        comparison = ActionComparison(
            disruption_diff=(
                f"首选方案中断等级: {primary_action.risk_profile.disruption_level}; "
                f"替代方案中断等级: {safer_da.risk_profile.disruption_level}"
            ),
            coverage_diff=(
                f"首选方案影响范围: {primary_action.risk_profile.scope}; "
                f"替代方案影响范围: {safer_da.risk_profile.scope}"
            ),
            reversibility_diff=(
                f"首选方案可逆: {'是' if primary_action.reversible else '否'}; "
                f"替代方案可逆: {'是' if safer_da.reversible else '否'}"
            ),
            recommendation=(
                f"当综合风险 > {_DISRUPTION_RISK_THRESHOLD} 或置信度 < {_CONFIDENCE_THRESHOLD} 时，"
                f"建议优先执行替代方案（{safer_type}），待更多信息确认后再升级为首选方案"
            ),
        )

        return safer_alt, safer_rollback, comparison

    def _build_rollback_plan(self, action: DecisionAction) -> RollbackPlan:
        """为指定动作构建回退计划。"""
        if not action.reversible:
            return RollbackPlan(
                rollback_supported=False,
                rollback_steps=[],
                rollback_risk="high",
                rollback_complexity="complex",
                not_supported_reason=f"动作类型 {action.action_type} 不可逆，无法自动回退",
            )

        tpl = action.rollback_template
        if not tpl:
            return RollbackPlan(
                rollback_supported=False,
                rollback_steps=[],
                rollback_risk="medium",
                rollback_complexity="moderate",
                not_supported_reason=f"动作类型 {action.action_type} 缺少回滚模板",
            )

        # 根据动作类型生成详细回退步骤
        steps = self._generate_rollback_steps(action)

        # 根据动作类型确定回退复杂度
        complexity_map = {
            "monitor_only": "trivial",
            "rate_limit": "simple",
            "block_ip": "simple",
            "block_port": "simple",
            "apply_acl_rule": "moderate",
            "isolate_host": "moderate",
        }
        complexity = complexity_map.get(action.action_type, "moderate")

        # 根据动作类型确定回退风险
        risk_map = {
            "monitor_only": "none",
            "rate_limit": "low",
            "block_ip": "low",
            "block_port": "low",
            "apply_acl_rule": "medium",
            "isolate_host": "medium",
        }
        risk = risk_map.get(action.action_type, "medium")

        # 估算回退耗时
        duration_map = {
            "monitor_only": "< 1min",
            "rate_limit": "< 2min",
            "block_ip": "< 2min",
            "block_port": "< 2min",
            "apply_acl_rule": "< 5min",
            "isolate_host": "< 5min",
        }
        duration = duration_map.get(action.action_type, "< 10min")

        return RollbackPlan(
            rollback_supported=True,
            rollback_steps=steps,
            rollback_risk=risk,
            rollback_complexity=complexity,
            estimated_duration=duration,
        )

    def _generate_rollback_steps(self, action: DecisionAction) -> list[str]:
        """根据动作类型生成具体的回退步骤。"""
        tpl = action.rollback_template
        target_value = action.params.get("target_value", "目标")

        step_templates = {
            "block_ip": [
                f"确认 {target_value} 的封锁规则仍处于活动状态",
                f"执行 {tpl.action_type}：移除针对 {target_value} 的封锁规则",
                f"验证 {target_value} 的网络连通性已恢复",
                "检查是否有残留的相关联动规则需要一并清理",
            ],
            "rate_limit": [
                f"确认 {target_value} 的限速规则仍处于活动状态",
                f"执行 {tpl.action_type}：移除 {target_value} 的速率限制",
                "验证带宽已恢复正常水平",
            ],
            "isolate_host": [
                f"确认 {target_value} 仍处于隔离状态",
                f"在恢复前对 {target_value} 进行安全扫描",
                f"执行 {tpl.action_type}：将 {target_value} 重新接入网络",
                f"验证 {target_value} 的所有网络连接已恢复",
                "监控恢复后 15 分钟内是否出现异常流量",
            ],
            "block_port": [
                f"确认 {target_value} 端口封锁规则仍处于活动状态",
                f"执行 {tpl.action_type}：重新开放 {target_value} 端口",
                "验证依赖该端口的服务已恢复正常",
            ],
            "apply_acl_rule": [
                "记录当前 ACL 规则变更内容",
                f"执行 {tpl.action_type}：移除新增的 ACL 规则",
                "验证原始访问策略已恢复",
                "检查是否有依赖该规则的其他策略受到影响",
            ],
            "monitor_only": [
                f"执行 {tpl.action_type}：取消对 {target_value} 的额外监控",
                "恢复正常监控配置",
            ],
        }

        return step_templates.get(action.action_type, [
            f"执行 {tpl.action_type} 操作",
            "验证系统已恢复到原始状态",
        ])

    def _build_summary(
        self,
        primary_action: DecisionAction,
        safer_alt: SaferAlternative | None,
        composite_risk: float,
        confidence: float,
    ) -> str:
        """构建一句话决策摘要。"""
        action_desc = {
            "block_ip": "封锁 IP",
            "rate_limit": "流量限速",
            "isolate_host": "隔离主机",
            "block_port": "封锁端口",
            "apply_acl_rule": "应用 ACL",
            "monitor_only": "加强监控",
        }
        primary_desc = action_desc.get(primary_action.action_type, primary_action.action_type)

        if safer_alt:
            safer_desc = action_desc.get(safer_alt.action.action_type, safer_alt.action.action_type)
            return (
                f"首选方案「{primary_desc}」（风险 {composite_risk:.2f}，置信度 {confidence:.2f}），"
                f"同时提供更保守方案「{safer_desc}」供选择。"
                f"{'建议优先执行保守方案。' if composite_risk > 0.7 else '可根据实际情况选择。'}"
            )

        return (
            f"推荐执行「{primary_desc}」（风险 {composite_risk:.2f}，置信度 {confidence:.2f}），"
            f"回退方案已就绪。"
        )

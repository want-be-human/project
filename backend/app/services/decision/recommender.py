from typing import Literal

from app.core.logging import get_logger
from app.schemas.decision import (
    ActionComparison,
    DecisionAction,
    DecisionResult,
    RecommendedDecision,
    RollbackPlan,
    SaferAlternative,
)
from app.schemas.twin import DryRunResultSchema
from app.services.decision.action_registry import (
    PLAN_ACTION_MAPPING,
    build_decision_action,
    get_safer_action_type,
)

logger = get_logger(__name__)

_RISK_THRESHOLD = 0.5
_CONFIDENCE_THRESHOLD = 0.6

_SEVERITY_LABEL = {"critical": "极高", "high": "高", "medium": "中", "low": "低"}

_ACTION_LABEL = {
    "block_ip": "封锁 IP",
    "rate_limit": "流量限速",
    "isolate_host": "隔离主机",
    "block_port": "封锁端口",
    "apply_acl_rule": "应用 ACL",
    "monitor_only": "加强监控",
}

_ACTION_REASON_DESC = {
    "block_ip": "封锁源 IP",
    "rate_limit": "对目标流量限速",
    "isolate_host": "隔离可疑主机",
    "block_port": "封锁风险端口",
    "apply_acl_rule": "应用 ACL 规则",
    "monitor_only": "仅加强监控",
}

_SAFER_BECAUSE = {
    "monitor_only": "仅增加监控，不产生任何业务中断",
    "rate_limit": "通过限速降低威胁流量，同时保留基本连通性",
    "block_port": "仅封锁特定端口，影响范围小于全面封锁",
    "block_ip": "仅封锁单个 IP，不影响其他主机",
    "apply_acl_rule": "通过细粒度规则控制流量，比全面隔离更精细",
}

_SAFER_TRADEOFF = {
    "monitor_only": "不能主动阻止攻击，仅依赖后续人工响应",
    "rate_limit": "无法完全阻止恶意流量，攻击者仍有部分带宽可用",
    "block_port": "可能影响使用同一端口的合法服务",
    "block_ip": "可能存在 IP 欺骗或共享 IP 的情况",
    "apply_acl_rule": "ACL 规则可能需要人工调优，维护成本较高",
}

_COMPLEXITY: dict[str, Literal["trivial", "simple", "moderate", "complex"]] = {
    "monitor_only": "trivial",
    "rate_limit": "simple",
    "block_ip": "simple",
    "block_port": "simple",
    "apply_acl_rule": "moderate",
    "isolate_host": "moderate",
}

_ROLLBACK_RISK: dict[str, Literal["none", "low", "medium", "high"]] = {
    "monitor_only": "none",
    "rate_limit": "low",
    "block_ip": "low",
    "block_port": "low",
    "apply_acl_rule": "medium",
    "isolate_host": "medium",
}

_ROLLBACK_DURATION = {
    "monitor_only": "< 1min",
    "rate_limit": "< 2min",
    "block_ip": "< 2min",
    "block_port": "< 2min",
    "apply_acl_rule": "< 5min",
    "isolate_host": "< 5min",
}


class DecisionRecommender:
    def recommend(
        self,
        alert_severity: str,
        alert_type: str,
        dry_run_result: DryRunResultSchema,
        plan_actions: list[dict],
    ) -> DecisionResult:
        impact = dry_run_result.impact
        risk = impact.service_disruption_risk
        confidence = impact.confidence
        services = impact.affected_services or []
        nodes = impact.impacted_nodes_count

        action_type, params = self._select_primary_action(plan_actions)
        primary = build_decision_action(
            action_type=action_type,
            params=params,
            confidence=confidence,
            affected_services_count=len(services),
            affected_nodes_count=nodes,
        )

        reasoning, based_on = self._build_reasoning(
            action_type, alert_severity, alert_type, risk, confidence, services,
        )
        recommended = RecommendedDecision(
            action=primary, reasoning=reasoning, based_on=based_on,
        )

        safer = None
        safer_rollback = None
        comparison = None
        if self._needs_safer(primary, risk, confidence):
            safer, safer_rollback, comparison = self._build_safer(
                primary, risk, confidence, params, services, nodes,
            )

        return DecisionResult(
            recommended_action=recommended,
            safer_alternative=safer,
            rollback_plan=self._build_rollback_plan(primary),
            safer_alternative_rollback=safer_rollback,
            decision_summary=self._build_summary(primary, safer, risk, confidence),
            comparison=comparison,
        )

    def _select_primary_action(self, plan_actions: list[dict]) -> tuple[str, dict]:
        if not plan_actions:
            return "monitor_only", {}

        first = plan_actions[0]
        raw_type = first.get("action_type", "")
        target = first.get("target", {})
        params = first.get("params", {})

        if isinstance(target, dict):
            params["target_type"] = target.get("type", "ip")
            params["target_value"] = target.get("value", "")

        return PLAN_ACTION_MAPPING.get(raw_type, "monitor_only"), params

    def _build_reasoning(
        self,
        action_type: str,
        severity: str,
        alert_type: str,
        risk: float,
        confidence: float,
        services: list[str],
    ) -> tuple[str, list[str]]:
        based_on = [
            f"告警类型: {alert_type}",
            f"告警严重度: {severity}",
            f"综合风险: {risk:.2f}",
        ]
        if services:
            based_on.append(f"受影响服务: {', '.join(services[:3])}")
        based_on.append(f"评估置信度: {confidence:.2f}")

        risk_level = "低" if risk < 0.3 else "中" if risk < 0.7 else "高"
        reasons = [
            f"检测到 {alert_type} 类型告警",
            f"严重等级为{_SEVERITY_LABEL.get(severity, '中')}",
            f"dry-run 评估综合风险为{risk_level}（{risk:.2f}）",
        ]

        desc = _ACTION_REASON_DESC.get(action_type, action_type)
        tail = "，但影响范围较大，请确认后执行" if action_type == "isolate_host" else "且回退成本可控"
        reasoning = (
            f"推荐执行「{desc}」。{'; '.join(reasons)}。"
            f"该动作在当前场景下可有效遏制威胁{tail}。"
        )
        return reasoning, based_on

    def _needs_safer(self, action: DecisionAction, risk: float, confidence: float) -> bool:
        if risk > _RISK_THRESHOLD:
            return True
        if confidence < _CONFIDENCE_THRESHOLD:
            return True
        if not action.reversible:
            return True
        return action.risk_profile.disruption_level in ("high", "critical")

    def _build_safer(
        self,
        primary: DecisionAction,
        risk: float,
        confidence: float,
        params: dict,
        services: list[str],
        nodes: int,
    ) -> tuple[SaferAlternative, RollbackPlan, ActionComparison]:
        safer_type = get_safer_action_type(primary.action_type)
        safer_action = build_decision_action(
            action_type=safer_type,
            params=params,
            confidence=confidence,
            affected_services_count=len(services),
            affected_nodes_count=nodes,
        )

        triggers = []
        if risk > _RISK_THRESHOLD:
            triggers.append(f"综合风险 {risk:.2f} 超过阈值 {_RISK_THRESHOLD}")
        if confidence < _CONFIDENCE_THRESHOLD:
            triggers.append(f"评估置信度 {confidence:.2f} 低于阈值 {_CONFIDENCE_THRESHOLD}")
        if primary.risk_profile.disruption_level in ("high", "critical"):
            triggers.append(f"首选动作中断等级为 {primary.risk_profile.disruption_level}")
        if not primary.reversible:
            triggers.append("首选动作不可逆")

        safer_alt = SaferAlternative(
            action=safer_action,
            safer_because=_SAFER_BECAUSE.get(
                safer_type, f"{safer_type} 的中断等级低于 {primary.action_type}",
            ),
            tradeoff=_SAFER_TRADEOFF.get(safer_type, f"保护力度低于 {primary.action_type}"),
            trigger_reason="; ".join(triggers),
        )

        comparison = ActionComparison(
            disruption_diff=(
                f"首选方案中断等级: {primary.risk_profile.disruption_level}; "
                f"替代方案中断等级: {safer_action.risk_profile.disruption_level}"
            ),
            coverage_diff=(
                f"首选方案影响范围: {primary.risk_profile.scope}; "
                f"替代方案影响范围: {safer_action.risk_profile.scope}"
            ),
            reversibility_diff=(
                f"首选方案可逆: {'是' if primary.reversible else '否'}; "
                f"替代方案可逆: {'是' if safer_action.reversible else '否'}"
            ),
            recommendation=(
                f"当综合风险 > {_RISK_THRESHOLD} 或置信度 < {_CONFIDENCE_THRESHOLD} 时，"
                f"建议优先执行替代方案（{safer_type}），待更多信息确认后再升级为首选方案"
            ),
        )

        return safer_alt, self._build_rollback_plan(safer_action), comparison

    def _build_rollback_plan(self, action: DecisionAction) -> RollbackPlan:
        if not action.reversible:
            return RollbackPlan(
                rollback_supported=False,
                rollback_steps=[],
                rollback_risk="high",
                rollback_complexity="complex",
                not_supported_reason=f"动作类型 {action.action_type} 不可逆，无法自动回退",
            )

        if not action.rollback_template:
            return RollbackPlan(
                rollback_supported=False,
                rollback_steps=[],
                rollback_risk="medium",
                rollback_complexity="moderate",
                not_supported_reason=f"动作类型 {action.action_type} 缺少回滚模板",
            )

        return RollbackPlan(
            rollback_supported=True,
            rollback_steps=self._rollback_steps(action),
            rollback_risk=_ROLLBACK_RISK.get(action.action_type, "medium"),
            rollback_complexity=_COMPLEXITY.get(action.action_type, "moderate"),
            estimated_duration=_ROLLBACK_DURATION.get(action.action_type, "< 10min"),
        )

    def _rollback_steps(self, action: DecisionAction) -> list[str]:
        tpl = action.rollback_template
        target = action.params.get("target_value", "目标")

        templates = {
            "block_ip": [
                f"确认 {target} 的封锁规则仍处于活动状态",
                f"执行 {tpl.action_type}：移除针对 {target} 的封锁规则",
                f"验证 {target} 的网络连通性已恢复",
                "检查是否有残留的相关联动规则需要一并清理",
            ],
            "rate_limit": [
                f"确认 {target} 的限速规则仍处于活动状态",
                f"执行 {tpl.action_type}：移除 {target} 的速率限制",
                "验证带宽已恢复正常水平",
            ],
            "isolate_host": [
                f"确认 {target} 仍处于隔离状态",
                f"在恢复前对 {target} 进行安全扫描",
                f"执行 {tpl.action_type}：将 {target} 重新接入网络",
                f"验证 {target} 的所有网络连接已恢复",
                "监控恢复后 15 分钟内是否出现异常流量",
            ],
            "block_port": [
                f"确认 {target} 端口封锁规则仍处于活动状态",
                f"执行 {tpl.action_type}：重新开放 {target} 端口",
                "验证依赖该端口的服务已恢复正常",
            ],
            "apply_acl_rule": [
                "记录当前 ACL 规则变更内容",
                f"执行 {tpl.action_type}：移除新增的 ACL 规则",
                "验证原始访问策略已恢复",
                "检查是否有依赖该规则的其他策略受到影响",
            ],
            "monitor_only": [
                f"执行 {tpl.action_type}：取消对 {target} 的额外监控",
                "恢复正常监控配置",
            ],
        }
        return templates.get(action.action_type, [
            f"执行 {tpl.action_type} 操作",
            "验证系统已恢复到原始状态",
        ])

    def _build_summary(
        self,
        primary: DecisionAction,
        safer: SaferAlternative | None,
        risk: float,
        confidence: float,
    ) -> str:
        primary_label = _ACTION_LABEL.get(primary.action_type, primary.action_type)

        if safer is None:
            return (
                f"推荐执行「{primary_label}」（风险 {risk:.2f}，置信度 {confidence:.2f}），"
                f"回退方案已就绪。"
            )

        safer_label = _ACTION_LABEL.get(safer.action.action_type, safer.action.action_type)
        tail = "建议优先执行保守方案。" if risk > 0.7 else "可根据实际情况选择。"
        return (
            f"首选方案「{primary_label}」（风险 {risk:.2f}，置信度 {confidence:.2f}），"
            f"同时提供更保守方案「{safer_label}」供选择。{tail}"
        )

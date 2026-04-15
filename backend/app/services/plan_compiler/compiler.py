from app.core.logging import get_logger
from app.models.alert import Alert
from app.schemas.agent import RecommendedAction, RecommendationSchema, InvestigationSchema
from app.schemas.evidence import EvidenceChainSchema
from app.schemas.twin import PlanAction, ActionTarget, RollbackAction, SkippedAction
from app.services.plan_compiler.rules import (
    match_action_type_with_hint,
    compute_confidence,
    PARAMS_DEFAULTS,
    ROLLBACK_MAPPING,
    SKIP_REASON_TEMPLATES,
    SKIP_SUGGESTION_TEMPLATES,
)

logger = get_logger(__name__)


class PlanCompiler:
    """将 Agent recommendation 动作编译为 Twin 可消费的 PlanAction。纯函数，无 DB 副作用。"""

    def compile(
        self,
        alert: Alert,
        recommendation: RecommendationSchema,
        investigation: InvestigationSchema | None = None,
        evidence_chain: EvidenceChainSchema | None = None,
        language: str = "en",
    ) -> tuple[list[PlanAction], list[SkippedAction]]:
        compiled: list[PlanAction] = []
        skipped: list[SkippedAction] = []

        inv_confidence = investigation.impact.confidence if investigation else None
        ev_count = len(evidence_chain.nodes) if evidence_chain else 0

        for action in recommendation.actions:
            result = self._compile_action(
                action=action,
                alert=alert,
                inv_confidence=inv_confidence,
                evidence_node_count=ev_count,
                evidence_chain=evidence_chain,
                language=language,
            )
            if result is None:
                skipped.append(self._build_skip_info(action, language))
            else:
                compiled.append(result)

        logger.info(
            "从推荐 %s 编译了 %d 个动作（跳过 %d 个）",
            recommendation.id,
            len(compiled),
            len(skipped),
        )
        return compiled, skipped

    def _compile_action(
        self,
        action: RecommendedAction,
        alert: Alert,
        inv_confidence: float | None,
        evidence_node_count: int,
        evidence_chain: EvidenceChainSchema | None,
        language: str,
    ) -> PlanAction | None:
        hint = action.compile_hint.model_dump() if action.compile_hint else None
        action_type, method = match_action_type_with_hint(action.title, hint)
        if action_type is None:
            logger.debug("跳过不可编译动作: %s (方法=%s)", action.title, method)
            return None

        target = self._resolve_target(action_type, alert)
        params = self._build_params(action_type, alert)
        rollback = self._build_rollback(action_type, alert, target)

        confidence = compute_confidence(
            severity=alert.severity,
            priority=action.priority,
            evidence_node_count=evidence_node_count,
            investigation_confidence=inv_confidence,
        )

        derived_from = self._trace_evidence(evidence_chain)
        reasoning = self._build_reasoning(action_type, action, alert, confidence, language)

        return PlanAction(
            action_type=action_type,  # type: ignore[arg-type]
            target=target,
            params=params,
            rollback=rollback,
            confidence=confidence,
            derived_from_evidence=derived_from,
            reasoning_summary=reasoning,
        )

    def _resolve_target(self, action_type: str, alert: Alert) -> ActionTarget:
        if action_type in ("block_ip", "isolate_host"):
            return ActionTarget(type="ip", value=alert.primary_src_ip or "0.0.0.0")

        if action_type == "segment_subnet":
            ip = alert.primary_src_ip or "0.0.0.0"
            parts = ip.split(".")
            # 从源 IP 推导 /24 子网
            if len(parts) == 4:
                subnet = f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
            else:
                subnet = f"{ip}/24"
            return ActionTarget(type="subnet", value=subnet)

        if action_type == "rate_limit_service":
            proto = alert.primary_proto or "TCP"
            port = alert.primary_dst_port or 0
            return ActionTarget(type="service", value=f"{proto}/{port}")

        return ActionTarget(type="ip", value=alert.primary_src_ip or "0.0.0.0")

    def _build_params(self, action_type: str, alert: Alert) -> dict:
        params = dict(PARAMS_DEFAULTS.get(action_type, {}))

        if action_type in ("block_ip", "isolate_host"):
            params["ip"] = alert.primary_src_ip or "0.0.0.0"
        elif action_type == "rate_limit_service":
            params["proto"] = alert.primary_proto or "TCP"
            params["port"] = alert.primary_dst_port or 0

        return params

    def _build_rollback(
        self, action_type: str, alert: Alert, target: ActionTarget
    ) -> RollbackAction | None:
        mapping = ROLLBACK_MAPPING.get(action_type)
        if not mapping:
            return None

        rollback_type, base_params = mapping
        params = dict(base_params)

        if action_type in ("block_ip", "isolate_host"):
            params["ip"] = target.value
        elif action_type == "rate_limit_service":
            params["proto"] = alert.primary_proto or "TCP"
            params["port"] = alert.primary_dst_port or 0

        return RollbackAction(action_type=rollback_type, params=params)

    def _trace_evidence(self, evidence_chain: EvidenceChainSchema | None) -> list[str]:
        if not evidence_chain:
            return []
        # 溯源节点：alert 节点、相关 flow/feature 节点，以及触发 recommendation 的 hypothesis
        relevant = {"alert", "flow", "feature", "hypothesis"}
        return [node.id for node in evidence_chain.nodes if node.type in relevant]

    def _build_reasoning(
        self,
        action_type: str,
        action: RecommendedAction,
        alert: Alert,
        confidence: float,
        language: str,
    ) -> str:
        if language == "zh":
            return (
                f"基于推荐动作 \"{action.title}\"（优先级: {action.priority}），"
                f"针对 {alert.severity} 级 {alert.type} 告警，"
                f"编译为 {action_type} 操作。"
                f"置信度: {confidence}。"
            )
        return (
            f"Compiled from recommendation \"{action.title}\" "
            f"(priority: {action.priority}) for {alert.severity} {alert.type} alert. "
            f"Action: {action_type}. Confidence: {confidence}."
        )

    def _build_skip_info(self, action: RecommendedAction, language: str) -> SkippedAction:
        intent = action.action_intent
        lang = "zh" if language == "zh" else "en"
        key = intent if intent in ("monitoring", "advisory") else "no_match"

        return SkippedAction(
            title=action.title,
            reason=SKIP_REASON_TEMPLATES[key][lang],
            action_intent=intent,
            suggestion=SKIP_SUGGESTION_TEMPLATES[key][lang],
        )

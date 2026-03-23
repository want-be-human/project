"""
PlanCompiler – core compilation logic.
Transforms RecommendedAction[] into PlanAction[] with traceability.

Design inspired by agentic-soc-platform's modular approach:
  each analysis capability produces structured, actionable output
  that downstream modules (playbooks / simulations) can consume directly.

This compiler is a pure function with no DB side effects.
"""

from app.core.logging import get_logger
from app.models.alert import Alert
from app.schemas.agent import RecommendedAction, RecommendationSchema, InvestigationSchema
from app.schemas.evidence import EvidenceChainSchema
from app.schemas.twin import PlanAction, ActionTarget, RollbackAction
from app.services.plan_compiler.rules import (
    match_action_type,
    compute_confidence,
    PARAMS_DEFAULTS,
    ROLLBACK_MAPPING,
)

logger = get_logger(__name__)


class PlanCompiler:
    """
    Compiles Agent recommendation actions into Twin-consumable PlanActions.

    All compilation rules are deterministic, keyword-based, and traceable
    back to evidence nodes. Non-compilable actions (e.g. monitoring
    suggestions) are silently skipped with a count returned.
    """

    def compile(
        self,
        alert: Alert,
        recommendation: RecommendationSchema,
        investigation: InvestigationSchema | None = None,
        evidence_chain: EvidenceChainSchema | None = None,
        language: str = "en",
    ) -> tuple[list[PlanAction], int]:
        """
        Compile recommendation actions into PlanActions.

        Args:
            alert: Source alert
            recommendation: Recommendation with actions to compile
            investigation: Optional investigation for confidence blending
            evidence_chain: Optional evidence chain for traceability

        Returns:
            Tuple of (compiled PlanAction list, number of skipped actions)
        """
        compiled: list[PlanAction] = []
        skipped = 0

        inv_confidence = (
            investigation.impact.confidence if investigation else None
        )
        evidence_node_count = (
            len(evidence_chain.nodes) if evidence_chain else 0
        )

        for action in recommendation.actions:
            result = self._compile_action(
                action=action,
                alert=alert,
                inv_confidence=inv_confidence,
                evidence_node_count=evidence_node_count,
                evidence_chain=evidence_chain,
                language=language,
            )
            if result is not None:
                compiled.append(result)
            else:
                skipped += 1

        logger.info(
            "Compiled %d actions from recommendation %s (%d skipped)",
            len(compiled),
            recommendation.id,
            skipped,
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
        """Compile a single RecommendedAction or return None if not compilable."""
        action_type = match_action_type(action.title)
        if action_type is None:
            logger.debug("Skipping non-compilable action: %s", action.title)
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

        derived_from = self._trace_evidence(action_type, evidence_chain)
        reasoning = self._build_reasoning(
            action_type, action, alert, confidence, language
        )

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
        """Determine target from alert entities based on action type."""
        if action_type in ("block_ip", "isolate_host"):
            return ActionTarget(type="ip", value=alert.primary_src_ip or "0.0.0.0")

        if action_type == "segment_subnet":
            ip = alert.primary_src_ip or "0.0.0.0"
            # 从源 IP 推导 /24 子网
            parts = ip.split(".")
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
        """Build action parameters using defaults and alert context."""
        params = dict(PARAMS_DEFAULTS.get(action_type, {}))

        if action_type == "block_ip":
            params["ip"] = alert.primary_src_ip or "0.0.0.0"
        elif action_type == "isolate_host":
            params["ip"] = alert.primary_src_ip or "0.0.0.0"
        elif action_type == "rate_limit_service":
            params["proto"] = alert.primary_proto or "TCP"
            params["port"] = alert.primary_dst_port or 0

        return params

    def _build_rollback(
        self, action_type: str, alert: Alert, target: ActionTarget
    ) -> RollbackAction | None:
        """Build rollback action for the given action type."""
        mapping = ROLLBACK_MAPPING.get(action_type)
        if not mapping:
            return None

        rollback_type, base_params = mapping
        params = dict(base_params)

        if action_type == "block_ip":
            params["ip"] = target.value
        elif action_type == "isolate_host":
            params["ip"] = target.value
        elif action_type == "rate_limit_service":
            params["proto"] = alert.primary_proto or "TCP"
            params["port"] = alert.primary_dst_port or 0

        return RollbackAction(action_type=rollback_type, params=params)

    def _trace_evidence(
        self, action_type: str, evidence_chain: EvidenceChainSchema | None
    ) -> list[str]:
        """Return evidence node IDs this action traces to."""
        if not evidence_chain:
            return []

        # action 的溯源节点包括：alert 节点、相关 flow/feature 节点，
        # 以及触发 recommendation 的 hypothesis 节点
        relevant_types = {"alert", "flow", "feature", "hypothesis"}
        return [
            node.id
            for node in evidence_chain.nodes
            if node.type in relevant_types
        ]

    def _build_reasoning(
        self,
        action_type: str,
        action: RecommendedAction,
        alert: Alert,
        confidence: float,
        language: str,
    ) -> str:
        """Build a human-readable explanation of why this action was compiled."""
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

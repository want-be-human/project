"""
PlanCompiler 核心编译逻辑。
将 RecommendedAction[] 转换为可追溯的 PlanAction[]。

设计借鉴 agentic-soc-platform 的模块化思路：
    每个分析能力产出结构化、可执行的结果，
    供下游模块（剧本/仿真）直接消费。

该编译器为纯函数，不产生数据库副作用。
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
    将 Agent recommendation 动作编译为 Twin 可消费的 PlanAction。

    所有编译规则均为确定性、基于关键词且可追溯到证据节点。
    不可编译动作（如纯监控建议）会被静默跳过，并返回跳过数量。
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
        将 recommendation 动作编译为 PlanAction 列表。

        参数：
            alert: 源告警
            recommendation: 待编译动作所在的 recommendation
            investigation: 可选的 investigation（用于融合置信度）
            evidence_chain: 可选的 evidence chain（用于追溯）

        返回：
            元组（编译后的 PlanAction 列表, 被跳过动作数量）
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
        """编译单个 RecommendedAction；若不可编译则返回 None。"""
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
        """根据动作类型从告警实体中确定目标。"""
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
        """结合默认值与告警上下文构建动作参数。"""
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
        """为给定动作类型构建回滚动作。"""
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
        """返回该动作可追溯到的证据节点 ID 列表。"""
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
        """构建该动作被编译的可读解释。"""
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

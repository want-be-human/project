"""
行动安全评分器 v1 — 六维度归一化风险指数。

核心公式：
    ActionRiskIndex = Σ(effective_weight_i × normalized_value_i)   ∈ [0, 1]
    ActionSafetyScore = round(100 × (1 - ActionRiskIndex), 2)     ∈ [0, 100]

六个组件：
    1. ServiceDisruptionRisk  — 服务中断风险（dry-run 直传）
    2. ReachabilityDrop       — 可达性损失（dry-run 直传）
    3. ImpactedRatio          — 影响范围比例（饱和曲线）
    4. ConfidencePenalty      — 置信度惩罚（1 - confidence）
    5. IrreversibilityPenalty — 不可逆惩罚（可逆性 + 恢复成本映射）
    6. RollbackComplexity     — 回退复杂度（复杂度 + 回退风险复合）

当某些组件数据不可用时，其权重按比例重分配给可用组件。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.logging import get_logger
from app.core.utils import datetime_to_iso, utc_now
from app.schemas.analytics import (
    PostureComponentSchema,
    ScoreFactorSchema,
    ScoreResultSchema,
)
from app.services.analytics.scorers.base import BaseScorer

logger = get_logger(__name__)

# ══════════════════════════════════════════════════════════════
# 常量
# ══════════════════════════════════════════════════════════════

# 基础权重
_BASE_WEIGHTS: dict[str, float] = {
    "service_disruption_risk": 0.30,
    "reachability_drop": 0.25,
    "impacted_ratio": 0.15,
    "confidence_penalty": 0.10,
    "irreversibility_penalty": 0.10,
    "rollback_complexity": 0.10,
}

# 影响范围比例饱和曲线半饱和常数
_K_IMPACTED_RATIO = 0.3

# 恢复成本 → 不可逆惩罚映射
_RECOVERY_COST_MAP: dict[str, float] = {
    "none": 0.0,
    "low": 0.1,
    "medium": 0.3,
    "high": 0.6,
}

# 回退复杂度映射
_ROLLBACK_COMPLEXITY_MAP: dict[str, float] = {
    "trivial": 0.0,
    "simple": 0.15,
    "moderate": 0.5,
    "complex": 1.0,
}

# 回退风险映射
_ROLLBACK_RISK_MAP: dict[str, float] = {
    "none": 0.0,
    "low": 0.1,
    "medium": 0.3,
    "high": 0.5,
}

# 回退复杂度组件子权重
_ROLLBACK_COMPLEXITY_WEIGHT = 0.6
_ROLLBACK_RISK_WEIGHT = 0.4

# 中文组件名映射
_CN_NAMES: dict[str, str] = {
    "service_disruption_risk": "服务中断风险",
    "reachability_drop": "可达性损失",
    "impacted_ratio": "影响范围比例",
    "confidence_penalty": "置信度惩罚",
    "irreversibility_penalty": "不可逆惩罚",
    "rollback_complexity": "回退复杂度",
}


# ══════════════════════════════════════════════════════════════
# 内部数据结构
# ═══════════════════════════════════���══════════════════════════


@dataclass
class _ComponentResult:
    """单个组件的计算结果（内部使用）。"""

    name: str
    raw_value: float
    normalized_value: float
    available: bool
    description: str


# ══════════════════════════════════════════════════════════════
# 评分器
# ══════════════════════════════════════════════════════════════


class ActionSafetyScorer(BaseScorer):
    """
    行动安全评分器 v1 — 六维度归一化风险指数体系。

    衡量"如果现在执行推荐动作，会不会伤到业务"。
    从最新 dry-run 影响评估和三段式决策结果中提取数据，
    通过六个维度计算综合风险指数。
    缺失数据时自动降级并重分配权重。
    """

    version = "action_safety_v1"

    def compute(
        self,
        *,
        service_disruption_risk: float | None = None,
        reachability_drop: float | None = None,
        impacted_nodes_count: int | None = None,
        total_node_count: int | None = None,
        confidence: float | None = None,
        reversible: bool | None = None,
        recovery_cost: str | None = None,
        rollback_complexity: str | None = None,
        rollback_risk: str | None = None,
        **kwargs,
    ) -> ScoreResultSchema:
        """
        计算行动安全评分。

        参数:
            service_disruption_risk: 服务中断风险 [0,1]，来自 DryRunImpact
            reachability_drop: 可达性损失 [0,1]，来自 DryRunImpact
            impacted_nodes_count: 受影响节点数量，来自 DryRunImpact
            total_node_count: 拓扑总节点数量
            confidence: 评估置信度 [0,1]，来自 DryRunImpact
            reversible: 动作是否可逆，来自 DecisionAction
            recovery_cost: 恢复成本等级，来自 DecisionAction
            rollback_complexity: 回退复杂度等级，来自 RollbackPlan
            rollback_risk: 回退风险等级，来自 RollbackPlan
        """
        # ---- 计算六个组件 ----
        components = [
            self._service_disruption_risk(service_disruption_risk),
            self._reachability_drop(reachability_drop),
            self._impacted_ratio(impacted_nodes_count, total_node_count),
            self._confidence_penalty(confidence),
            self._irreversibility_penalty(reversible, recovery_cost),
            self._rollback_complexity(rollback_complexity, rollback_risk),
        ]

        # ---- 权重重分配 + 计算 RiskIndex ----
        risk_index = 0.0
        for comp in components:
            if comp.available:
                ew = self._effective_weight(comp, components)
                risk_index += ew * comp.normalized_value

        risk_index = round(min(1.0, max(0.0, risk_index)), 6)
        score = round(100.0 * (1.0 - risk_index), 2)

        # ---- 构建 posture_components（复用通用 Schema）----
        posture_components = self._build_posture_components(components)

        # ---- 构建 factors（向后兼容格式）----
        factors = [
            ScoreFactorSchema(
                name=pc.name,
                value=pc.normalized_value,
                weight=pc.effective_weight,
                description=pc.description,
            )
            for pc in posture_components
        ]

        # ---- 解释摘要（one_line_explanation）----
        explain_summary = self._build_explain_summary(
            score, risk_index, posture_components
        )

        # ---- 简短解释 ----
        available_count = sum(1 for c in components if c.available)
        explain = (
            f"行动安全评分 {score}（风险指数 {risk_index:.4f}）。"
            f"可用组件 {available_count}/6。"
        )

        # ---- 构建 breakdown ----
        breakdown = {
            "formula": "ActionSafetyScore = 100 × (1 - ActionRiskIndex)",
            "risk_index": risk_index,
            "components": {
                pc.name: {
                    "normalized": pc.normalized_value,
                    "effective_weight": pc.effective_weight,
                    "contribution": pc.contribution,
                    "available": pc.available,
                }
                for pc in posture_components
            },
        }

        return ScoreResultSchema(
            value=score,
            factors=factors,
            score_version=self.version,
            computed_at=datetime_to_iso(utc_now()),
            explain=explain,
            breakdown=breakdown,
            risk_index=risk_index,
            posture_components=posture_components,
            explain_summary=explain_summary,
        )

    # ------------------------------------------------------------------
    # 组件计算
    # ------------------------------------------------------------------

    def _service_disruption_risk(
        self, value: float | None
    ) -> _ComponentResult:
        """
        服务中断风险：直接使用 dry-run 计算的 service_disruption_risk [0,1]。
        衡量"执行动作后服务中断的可能性"。
        """
        if value is None:
            return _ComponentResult(
                name="service_disruption_risk",
                raw_value=0.0,
                normalized_value=0.0,
                available=False,
                description="服务中断风险：无 dry-run 数据，已降级",
            )

        normalized = min(1.0, max(0.0, value))
        return _ComponentResult(
            name="service_disruption_risk",
            raw_value=round(value, 4),
            normalized_value=round(normalized, 6),
            available=True,
            description=f"服务中断风险：{normalized:.3f}",
        )

    def _reachability_drop(self, value: float | None) -> _ComponentResult:
        """
        可达性损失：直接使用 dry-run 计算的 reachability_drop [0,1]。
        衡量"执行动作后网络可达性下降幅度"。
        """
        if value is None:
            return _ComponentResult(
                name="reachability_drop",
                raw_value=0.0,
                normalized_value=0.0,
                available=False,
                description="可达性损失：无 dry-run 数据，已降级",
            )

        normalized = min(1.0, max(0.0, value))
        return _ComponentResult(
            name="reachability_drop",
            raw_value=round(value, 4),
            normalized_value=round(normalized, 6),
            available=True,
            description=f"可达性损失：{normalized:.3f}",
        )

    def _impacted_ratio(
        self, impacted_count: int | None, total_count: int | None
    ) -> _ComponentResult:
        """
        影响范围比例：impacted_nodes_count / total_node_count，饱和曲线归一化。
        饱和曲线 r/(r+K) 防止小规模网络中单节点占比过高导致过度惩罚。
        """
        if impacted_count is None or total_count is None or total_count <= 0:
            return _ComponentResult(
                name="impacted_ratio",
                raw_value=0.0,
                normalized_value=0.0,
                available=False,
                description="影响范围比例：无拓扑数据，已降级",
            )

        ratio = impacted_count / total_count
        # 饱和曲线：ratio=0.3 时归一化值 = 0.5
        normalized = ratio / (ratio + _K_IMPACTED_RATIO) if ratio > 0 else 0.0

        return _ComponentResult(
            name="impacted_ratio",
            raw_value=round(ratio, 4),
            normalized_value=round(min(1.0, normalized), 6),
            available=True,
            description=f"影响范围比例：{ratio:.1%}，归一化 {normalized:.3f}",
        )

    def _confidence_penalty(self, confidence: float | None) -> _ComponentResult:
        """
        置信度惩罚：1 - confidence。
        置信度越低（评估越不确定），惩罚越高。
        """
        if confidence is None:
            return _ComponentResult(
                name="confidence_penalty",
                raw_value=0.0,
                normalized_value=0.0,
                available=False,
                description="置信度惩罚：无置信度数据，已降级",
            )

        clamped = min(1.0, max(0.0, confidence))
        penalty = 1.0 - clamped

        return _ComponentResult(
            name="confidence_penalty",
            raw_value=round(clamped, 4),
            normalized_value=round(penalty, 6),
            available=True,
            description=f"置信度惩罚：置信度 {clamped:.3f}，惩罚 {penalty:.3f}",
        )

    def _irreversibility_penalty(
        self, reversible: bool | None, recovery_cost: str | None
    ) -> _ComponentResult:
        """
        不可逆惩罚：根据动作可逆性和恢复成本计算。
        不可逆动作直接惩罚 1.0；可逆动作根据恢复成本分级惩罚。
        """
        if reversible is None:
            return _ComponentResult(
                name="irreversibility_penalty",
                raw_value=0.0,
                normalized_value=0.0,
                available=False,
                description="不可逆惩罚：无决策数据，已降级",
            )

        if not reversible:
            return _ComponentResult(
                name="irreversibility_penalty",
                raw_value=1.0,
                normalized_value=1.0,
                available=True,
                description="不可逆惩罚：动作不可逆，惩罚 1.0",
            )

        cost_val = _RECOVERY_COST_MAP.get(recovery_cost or "none", 0.0)
        return _ComponentResult(
            name="irreversibility_penalty",
            raw_value=round(cost_val, 4),
            normalized_value=round(cost_val, 6),
            available=True,
            description=f"不可逆惩罚：可逆，恢复成本 {recovery_cost or 'none'}（{cost_val:.2f}）",
        )

    def _rollback_complexity(
        self, complexity: str | None, risk: str | None
    ) -> _ComponentResult:
        """
        回退复杂度：综合回退操作复杂度和回退风险。
        公式：0.6 × complexity_map + 0.4 × risk_map。
        """
        if complexity is None:
            return _ComponentResult(
                name="rollback_complexity",
                raw_value=0.0,
                normalized_value=0.0,
                available=False,
                description="回退复杂度：无回退计划数据，已降级",
            )

        complexity_val = _ROLLBACK_COMPLEXITY_MAP.get(complexity, 0.0)
        risk_val = _ROLLBACK_RISK_MAP.get(risk or "none", 0.0)
        normalized = (
            _ROLLBACK_COMPLEXITY_WEIGHT * complexity_val
            + _ROLLBACK_RISK_WEIGHT * risk_val
        )

        return _ComponentResult(
            name="rollback_complexity",
            raw_value=round(complexity_val, 4),
            normalized_value=round(min(1.0, normalized), 6),
            available=True,
            description=(
                f"回退复杂度：{complexity}（{complexity_val:.2f}）"
                f"+ 风险 {risk or 'none'}（{risk_val:.2f}）= {normalized:.3f}"
            ),
        )

    # ------------------------------------------------------------------
    # 权重重分配
    # ------------------------------------------------------------------

    def _effective_weight(
        self, comp: _ComponentResult, all_components: list[_ComponentResult]
    ) -> float:
        """计算单个组件的有效权重（不可用组件权重按比例分配给可用组件）。"""
        if not comp.available:
            return 0.0

        base_w = _BASE_WEIGHTS[comp.name]
        available_sum = sum(
            _BASE_WEIGHTS[c.name] for c in all_components if c.available
        )
        if available_sum <= 0:
            return 0.0

        return base_w / available_sum

    # ------------------------------------------------------------------
    # 构建输出
    # ------------------------------------------------------------------

    def _build_posture_components(
        self, components: list[_ComponentResult]
    ) -> list[PostureComponentSchema]:
        """将内部计算结果转换为输出 Schema（复用 PostureComponentSchema）。"""
        result = []
        for comp in components:
            ew = self._effective_weight(comp, components)
            contribution = (
                round(ew * comp.normalized_value, 6) if comp.available else 0.0
            )

            result.append(
                PostureComponentSchema(
                    name=comp.name,
                    raw_value=comp.raw_value,
                    normalized_value=comp.normalized_value,
                    weight=_BASE_WEIGHTS[comp.name],
                    effective_weight=round(ew, 6),
                    contribution=contribution,
                    trend_direction="unknown",
                    available=comp.available,
                    description=comp.description,
                )
            )
        return result

    def _build_explain_summary(
        self,
        score: float,
        risk_index: float,
        components: list[PostureComponentSchema],
    ) -> str:
        """
        生成解释摘要（one_line_explanation）。
        分三级：高安全（≥80）、中安全（50-79）、低安全（<50）。
        低安全时精确指出风险来源。
        """
        available = [c for c in components if c.available]
        sorted_by_contribution = sorted(
            available, key=lambda c: c.contribution, reverse=True
        )

        # 主要风险因子
        top_factors = []
        for c in sorted_by_contribution[:3]:
            if c.contribution > 0.01:
                cn = _CN_NAMES.get(c.name, c.name)
                top_factors.append(f"{cn}（{c.normalized_value:.2f}）")

        # 不可用组件说明
        unavailable = [c for c in components if not c.available]
        unavailable_text = ""
        if unavailable:
            names = "、".join(_CN_NAMES.get(c.name, c.name) for c in unavailable)
            unavailable_text = f"（{names} 数据缺失，已降级）"

        # 分级判断
        if score >= 80:
            summary = f"评分 {score}，处置安全性良好，可放心执行推荐动作"
        elif score >= 50:
            factors_text = "、".join(top_factors) if top_factors else "综合因素"
            summary = f"评分 {score}，处置安全性一般，主要风险：{factors_text}。建议复核后执行"
        else:
            # 低安全度：精确指出问题
            reasons = self._pinpoint_reasons(sorted_by_contribution)
            summary = f"评分 {score}，处置安全性偏低，{reasons}。建议暂缓执行或选用更安全的替代方案"

        if unavailable_text:
            summary += unavailable_text

        return summary + "。"

    @staticmethod
    def _pinpoint_reasons(
        sorted_components: list[PostureComponentSchema],
    ) -> str:
        """当安全度低时，精确指出哪些因子导致风险。"""
        # 问题描述映射（normalized_value > 0.5 视为问题显著）
        reason_templates: dict[str, str] = {
            "service_disruption_risk": "服务中断风险高",
            "reachability_drop": "可达性损失大",
            "impacted_ratio": "影响范围广",
            "confidence_penalty": "评估置信度不足",
            "irreversibility_penalty": "动作不可逆或恢复代价高",
            "rollback_complexity": "回退操作复杂",
        }

        reasons = []
        for c in sorted_components:
            if c.normalized_value > 0.3 and c.contribution > 0.01:
                reason = reason_templates.get(c.name, c.name)
                reasons.append(reason)

        return "、".join(reasons[:3]) if reasons else "综合风险偏高"

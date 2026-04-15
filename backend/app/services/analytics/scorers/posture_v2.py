"""
安全态势评分器 v2 — 归一化风险指数。
    RiskIndex = Σ(effective_weight_i × normalized_value_i)   ∈ [0, 1]
    PostureScore = round(100 × (1 - RiskIndex), 2)           ∈ [0, 100]

缺失组件的权重按比例重分配给可用组件。
"""

from __future__ import annotations

import math
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

_BASE_WEIGHTS: dict[str, float] = {
    "severity_pressure": 0.30,
    "open_pressure": 0.25,
    "trend_pressure": 0.20,
    "blast_radius": 0.15,
    "execution_risk": 0.10,
}

_SEVERITY_WEIGHTS: dict[str, float] = {
    "critical": 1.0,
    "high": 0.6,
    "medium": 0.2,
    "low": 0.05,
}

# 饱和曲线半饱和常数：10 个 critical 当量时压力 = 0.5
_K_SEVERITY = 10.0

_TREND_SLOPE_SCALE = 3.0

_BLAST_AVG_WEIGHT = 0.6
_BLAST_HIGH_RATIO_WEIGHT = 0.4
_BLAST_HIGH_THRESHOLD = 0.5

_OPEN_CONFIDENCE_THRESHOLD = 5.0

_CN_NAMES: dict[str, str] = {
    "severity_pressure": "严重性压力",
    "open_pressure": "开放告警压力",
    "trend_pressure": "趋势压力",
    "blast_radius": "爆炸半径",
    "execution_risk": "执行风险",
}


@dataclass
class _ComponentResult:
    name: str
    raw_value: float
    normalized_value: float
    available: bool
    trend_direction: str  # "improving" | "worsening" | "stable" | "unknown"
    description: str


class PostureScorerV2(BaseScorer):
    version = "posture_v2"

    def compute(
        self,
        *,
        alert_by_severity: dict[str, int] | None = None,
        alert_total: int = 0,
        alert_open_count: int = 0,
        trend_days: list | None = None,
        top_risk_nodes: list | None = None,
        dryrun_avg_disruption_risk: float = 0.0,
        dryrun_total: int = 0,
        **kwargs,
    ) -> ScoreResultSchema:
        alert_by_severity = alert_by_severity or {}
        trend_days = trend_days or []
        top_risk_nodes = top_risk_nodes or []

        components = [
            self._severity_pressure(alert_by_severity),
            self._open_pressure(alert_open_count, alert_total),
            self._trend_pressure(trend_days),
            self._blast_radius(top_risk_nodes),
            self._execution_risk(dryrun_avg_disruption_risk, dryrun_total),
        ]

        risk_index = 0.0
        for comp in components:
            if comp.available:
                ew = self._effective_weight(comp, components)
                risk_index += ew * comp.normalized_value

        risk_index = round(min(1.0, max(0.0, risk_index)), 6)
        score = round(100.0 * (1.0 - risk_index), 2)

        posture_components = self._build_posture_components(components)

        factors = [
            ScoreFactorSchema(
                name=pc.name,
                value=pc.normalized_value,
                weight=pc.effective_weight,
                description=pc.description,
            )
            for pc in posture_components
        ]

        explain_summary = self._build_explain_summary(
            score, risk_index, posture_components
        )

        explain = (
            f"态势评分 {score}（风险指数 {risk_index:.4f}）。"
            f"可用组件 {sum(1 for c in components if c.available)}/5。"
        )

        breakdown = {
            "formula": "PostureScore = 100 × (1 - RiskIndex)",
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

    def _severity_pressure(
        self, alert_by_severity: dict[str, int]
    ) -> _ComponentResult:
        weighted_sum = sum(
            alert_by_severity.get(sev, 0) * w
            for sev, w in _SEVERITY_WEIGHTS.items()
        )
        normalized = (
            weighted_sum / (weighted_sum + _K_SEVERITY) if weighted_sum > 0 else 0.0
        )

        return _ComponentResult(
            name="severity_pressure",
            raw_value=round(weighted_sum, 4),
            normalized_value=round(normalized, 6),
            available=True,
            trend_direction="unknown",
            description=f"严重性压力：加权告警当量 {weighted_sum:.1f}，归一化 {normalized:.3f}",
        )

    def _open_pressure(self, open_count: int, total: int) -> _ComponentResult:
        open_ratio = open_count / max(total, 1)
        # 小样本阻尼：不足 5 个告警时按比例降低置信度
        confidence = min(1.0, total / _OPEN_CONFIDENCE_THRESHOLD)
        normalized = open_ratio * confidence

        return _ComponentResult(
            name="open_pressure",
            raw_value=round(open_ratio, 4),
            normalized_value=round(min(1.0, normalized), 6),
            available=True,
            trend_direction="unknown",
            description=f"开放压力：开放比例 {open_ratio:.1%}，置信度 {confidence:.2f}",
        )

    def _trend_pressure(self, trend_days: list) -> _ComponentResult:
        if len(trend_days) < 2:
            return _ComponentResult(
                name="trend_pressure",
                raw_value=0.0,
                normalized_value=0.0,
                available=False,
                trend_direction="unknown",
                description="趋势压力：数据不足（< 2 天），已降级",
            )

        daily_values = []
        for day in trend_days:
            # 兼容 TrendDaySchema 对象和 dict
            if hasattr(day, "critical"):
                day_val = (
                    getattr(day, "critical", 0) * _SEVERITY_WEIGHTS["critical"]
                    + getattr(day, "high", 0) * _SEVERITY_WEIGHTS["high"]
                    + getattr(day, "medium", 0) * _SEVERITY_WEIGHTS["medium"]
                    + getattr(day, "low", 0) * _SEVERITY_WEIGHTS["low"]
                )
            else:
                day_val = (
                    day.get("critical", 0) * _SEVERITY_WEIGHTS["critical"]
                    + day.get("high", 0) * _SEVERITY_WEIGHTS["high"]
                    + day.get("medium", 0) * _SEVERITY_WEIGHTS["medium"]
                    + day.get("low", 0) * _SEVERITY_WEIGHTS["low"]
                )
            daily_values.append(day_val)

        slope = self._linear_slope(daily_values)
        # 只惩罚恶化趋势（斜率 > 0），改善不额外加分
        normalized = max(0.0, math.tanh(slope / _TREND_SLOPE_SCALE))

        if slope > 0.1:
            direction = "worsening"
        elif slope < -0.1:
            direction = "improving"
        else:
            direction = "stable"

        return _ComponentResult(
            name="trend_pressure",
            raw_value=round(slope, 4),
            normalized_value=round(normalized, 6),
            available=True,
            trend_direction=direction,
            description=f"趋势压力：斜率 {slope:.3f}，方向 {direction}",
        )

    def _blast_radius(self, top_risk_nodes: list) -> _ComponentResult:
        if not top_risk_nodes:
            return _ComponentResult(
                name="blast_radius",
                raw_value=0.0,
                normalized_value=0.0,
                available=False,
                trend_direction="unknown",
                description="爆炸半径：无拓扑数据，已降级",
            )

        risks = []
        for node in top_risk_nodes[:10]:
            r = (
                node.get("risk", 0.0)
                if isinstance(node, dict)
                else getattr(node, "risk", 0.0)
            )
            risks.append(float(r))

        if not risks:
            return _ComponentResult(
                name="blast_radius",
                raw_value=0.0,
                normalized_value=0.0,
                available=False,
                trend_direction="unknown",
                description="爆炸半径：无风险数据，已降级",
            )

        avg_risk = sum(risks) / len(risks)
        high_risk_count = sum(1 for r in risks if r > _BLAST_HIGH_THRESHOLD)
        high_risk_ratio = high_risk_count / len(risks)

        normalized = (
            _BLAST_AVG_WEIGHT * avg_risk
            + _BLAST_HIGH_RATIO_WEIGHT * high_risk_ratio
        )

        return _ComponentResult(
            name="blast_radius",
            raw_value=round(avg_risk, 4),
            normalized_value=round(min(1.0, normalized), 6),
            available=True,
            trend_direction="unknown",
            description=f"爆炸半径：平均风险 {avg_risk:.3f}，高危占比 {high_risk_ratio:.1%}",
        )

    def _execution_risk(
        self, avg_risk: float, dryrun_total: int
    ) -> _ComponentResult:
        if dryrun_total == 0:
            return _ComponentResult(
                name="execution_risk",
                raw_value=0.0,
                normalized_value=0.0,
                available=False,
                trend_direction="unknown",
                description="执行风险：无 dry-run 数据，已降级",
            )

        normalized = min(1.0, max(0.0, avg_risk))

        return _ComponentResult(
            name="execution_risk",
            raw_value=round(avg_risk, 4),
            normalized_value=round(normalized, 6),
            available=True,
            trend_direction="unknown",
            description=f"执行风险：平均中断风险 {avg_risk:.3f}",
        )

    def _effective_weight(
        self, comp: _ComponentResult, all_components: list[_ComponentResult]
    ) -> float:
        if not comp.available:
            return 0.0

        base_w = _BASE_WEIGHTS[comp.name]
        available_sum = sum(
            _BASE_WEIGHTS[c.name] for c in all_components if c.available
        )
        if available_sum <= 0:
            return 0.0

        return base_w / available_sum

    def _build_posture_components(
        self, components: list[_ComponentResult]
    ) -> list[PostureComponentSchema]:
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
                    trend_direction=comp.trend_direction,
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
        available = [c for c in components if c.available]
        sorted_by_contribution = sorted(
            available, key=lambda c: c.contribution, reverse=True
        )

        top_factors = []
        for c in sorted_by_contribution[:3]:
            if c.contribution > 0.01:
                top_factors.append(
                    f"{_CN_NAMES.get(c.name, c.name)}（{c.normalized_value:.2f}）"
                )

        trend_comp = next(
            (c for c in components if c.name == "trend_pressure"), None
        )
        trend_text = ""
        if trend_comp and trend_comp.available:
            if trend_comp.trend_direction == "worsening":
                trend_text = "，趋势恶化中"
            elif trend_comp.trend_direction == "improving":
                trend_text = "，趋势改善中"
            else:
                trend_text = "，趋势平稳"

        if score >= 80:
            level = "态势良好"
        elif score >= 60:
            level = "态势一般"
        elif score >= 40:
            level = "态势偏低"
        else:
            level = "态势严峻"

        parts = [f"评分 {score}（{level}）"]

        if top_factors:
            parts.append(f"主要压力：{'、'.join(top_factors)}")

        unavailable = [c for c in components if not c.available]
        if unavailable:
            names = "、".join(_CN_NAMES.get(c.name, c.name) for c in unavailable)
            parts.append(f"（{names} 数据缺失，已降级）")

        return "。".join(parts) + trend_text + "。"

    @staticmethod
    def _linear_slope(values: list[float]) -> float:
        """对等距时间序列做 OLS 线性回归，返回斜率。"""
        n = len(values)
        if n < 2:
            return 0.0

        x_mean = (n - 1) / 2.0
        y_mean = sum(values) / n

        numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return 0.0

        return numerator / denominator

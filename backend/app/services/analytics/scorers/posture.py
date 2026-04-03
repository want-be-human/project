"""
安全态势评分器 v1。
吸收前端 HeroSection.tsx 中的 calcPostureScore 公式，
在后端统一计算，支持因子分解与版本化。
"""

from app.core.logging import get_logger
from app.core.utils import datetime_to_iso, utc_now
from app.schemas.analytics import ScoreFactorSchema, ScoreResultSchema
from app.services.analytics.scorers.base import BaseScorer

logger = get_logger(__name__)

# 评分公式常量
_CRITICAL_PENALTY = 15
_HIGH_PENALTY = 8
_OPEN_PENALTY = 2
_AVG_RISK_PENALTY = 20


class PostureScorer(BaseScorer):
    """
    安全态势评分器 v1。
    公式：max(0, 100 - critical*15 - high*8 - open*2 - avg_risk*20)
    接收预聚合指标值，不直接查询数据库，便于测试和复用。
    """

    version = "posture_v1"

    def compute(
        self,
        critical_count: int = 0,
        high_count: int = 0,
        open_count: int = 0,
        avg_disruption_risk: float = 0.0,
        **kwargs,
    ) -> ScoreResultSchema:
        """计算态势评分。"""
        # 各因子扣分
        critical_deduct = critical_count * _CRITICAL_PENALTY
        high_deduct = high_count * _HIGH_PENALTY
        open_deduct = open_count * _OPEN_PENALTY
        risk_deduct = avg_disruption_risk * _AVG_RISK_PENALTY

        raw = 100 - critical_deduct - high_deduct - open_deduct - risk_deduct
        value = round(max(0.0, raw), 2)

        factors = [
            ScoreFactorSchema(
                name="critical_alerts",
                value=float(critical_count),
                weight=_CRITICAL_PENALTY,
                description=f"严重告警数 × {_CRITICAL_PENALTY}",
            ),
            ScoreFactorSchema(
                name="high_alerts",
                value=float(high_count),
                weight=_HIGH_PENALTY,
                description=f"高危告警数 × {_HIGH_PENALTY}",
            ),
            ScoreFactorSchema(
                name="open_alerts",
                value=float(open_count),
                weight=_OPEN_PENALTY,
                description=f"开放告警数 × {_OPEN_PENALTY}",
            ),
            ScoreFactorSchema(
                name="avg_disruption_risk",
                value=float(avg_disruption_risk),
                weight=_AVG_RISK_PENALTY,
                description=f"平均中断风险 × {_AVG_RISK_PENALTY}",
            ),
        ]

        # 可读解释
        explain = (
            f"态势评分 {value}：基础 100 分，"
            f"严重告警扣 {critical_deduct}，高危告警扣 {high_deduct}，"
            f"开放告警扣 {open_deduct}，中断风险扣 {risk_deduct:.1f}"
        )

        return ScoreResultSchema(
            value=value,
            factors=factors,
            score_version=self.version,
            computed_at=datetime_to_iso(utc_now()),
            explain=explain,
            breakdown={
                "base": 100,
                "critical_deduction": critical_deduct,
                "high_deduction": high_deduct,
                "open_deduction": open_deduct,
                "risk_deduction": round(risk_deduct, 2),
            },
        )

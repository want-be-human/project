"""
行动安全评分器（占位）。
预留返回结构，具体计算逻辑后续接入。
"""

from app.core.utils import datetime_to_iso, utc_now
from app.schemas.analytics import ScoreResultSchema
from app.services.analytics.scorers.base import BaseScorer


class ActionSafetyScorer(BaseScorer):
    """行动安全评分器占位实现。返回固定结构，value=-1 表示未实现。"""

    version = "action_safety_v0"

    def compute(self, **kwargs) -> ScoreResultSchema:
        return ScoreResultSchema(
            value=-1,
            factors=[],
            score_version=self.version,
            computed_at=datetime_to_iso(utc_now()),
            explain="行动安全评分尚未实现",
        )

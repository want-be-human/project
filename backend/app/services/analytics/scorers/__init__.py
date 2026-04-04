"""
评分器注册表。
按 version 字符串查找评分器类，便于版本化管理和动态切换。
"""

from app.services.analytics.scorers.action_safety import ActionSafetyScorer
from app.services.analytics.scorers.base import BaseScorer
from app.services.analytics.scorers.posture import PostureScorer
from app.services.analytics.scorers.posture_v2 import PostureScorerV2

SCORER_REGISTRY: dict[str, type[BaseScorer]] = {
    "posture_v1": PostureScorer,
    "posture_v2": PostureScorerV2,
    "action_safety_v1": ActionSafetyScorer,
}

__all__ = [
    "BaseScorer",
    "PostureScorer",
    "PostureScorerV2",
    "ActionSafetyScorer",
    "SCORER_REGISTRY",
]

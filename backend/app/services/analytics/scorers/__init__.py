"""
评分器注册表。
按 version 字符串查找评分器类，便于版本化管理和动态切换。
"""

from app.services.analytics.scorers.action_safety import ActionSafetyScorer
from app.services.analytics.scorers.base import BaseScorer
from app.services.analytics.scorers.posture import PostureScorer

SCORER_REGISTRY: dict[str, type[BaseScorer]] = {
    "posture_v1": PostureScorer,
    "action_safety_v0": ActionSafetyScorer,
}

__all__ = [
    "BaseScorer",
    "PostureScorer",
    "ActionSafetyScorer",
    "SCORER_REGISTRY",
]

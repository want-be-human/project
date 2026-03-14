"""
Workflow stages for agent operations.

Import stages directly where needed to avoid circular imports:
    from app.workflows.stages.triage import TriageStage
    from app.workflows.stages.investigation import InvestigationStage
    from app.workflows.stages.recommendation import RecommendationStage
"""

from app.workflows.stages.base import BaseStage, StageContext, StageResult

__all__ = [
    "BaseStage",
    "StageContext",
    "StageResult",
]

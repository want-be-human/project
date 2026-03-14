"""
Investigation stage – delegates to AgentService.investigate().
"""

from app.services.agent.service import AgentService
from app.workflows.stages.base import BaseStage, StageContext, StageResult


class InvestigationStage(BaseStage):
    """Generate structured investigation analysis for an alert."""

    @property
    def name(self) -> str:
        return "investigate"

    def execute(self, context: StageContext) -> StageResult:
        service = AgentService(context.db)
        investigation = service.investigate(context.alert, language=context.language)
        return StageResult(
            output=investigation,
            metadata={
                "alert_id": context.alert.id,
                "investigation_id": investigation.id,
                "language": context.language,
            },
        )

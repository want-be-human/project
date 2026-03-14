"""
Triage stage – delegates to AgentService.triage().
"""

from app.services.agent.service import AgentService
from app.workflows.stages.base import BaseStage, StageContext, StageResult


class TriageStage(BaseStage):
    """Generate triage summary for an alert."""

    @property
    def name(self) -> str:
        return "triage"

    def execute(self, context: StageContext) -> StageResult:
        service = AgentService(context.db)
        summary = service.triage(context.alert, language=context.language)
        return StageResult(
            output=summary,
            metadata={"alert_id": context.alert.id, "language": context.language},
        )

"""
调查阶段：委托给 AgentService.investigate() 执行。
"""

from app.services.agent.service import AgentService
from app.workflows.stages.base import BaseStage, StageContext, StageResult


class InvestigationStage(BaseStage):
    """为告警生成结构化调查分析。"""

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

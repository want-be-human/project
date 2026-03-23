"""
建议阶段：委托给 AgentService.recommend() 执行。
"""

from app.services.agent.service import AgentService
from app.workflows.stages.base import BaseStage, StageContext, StageResult


class RecommendationStage(BaseStage):
    """为告警生成处置建议。"""

    @property
    def name(self) -> str:
        return "recommend"

    def execute(self, context: StageContext) -> StageResult:
        service = AgentService(context.db)
        recommendation = service.recommend(context.alert, language=context.language)
        return StageResult(
            output=recommendation,
            metadata={
                "alert_id": context.alert.id,
                "recommendation_id": recommendation.id,
                "language": context.language,
            },
        )

"""
编译方案阶段：委托给 PlanCompilerService 执行。
"""

from app.services.plan_compiler.service import PlanCompilerService
from app.workflows.stages.base import BaseStage, StageContext, StageResult


class CompilePlanStage(BaseStage):
    """将智能体建议编译为结构化 Twin ActionPlan。"""

    @property
    def name(self) -> str:
        return "compile_plan"

    def execute(self, context: StageContext) -> StageResult:
        service = PlanCompilerService(context.db)
        recommendation_id = context.previous_outputs.get("recommendation_id")
        response = service.compile_for_alert(
            alert_id=context.alert.id,
            recommendation_id=recommendation_id,
            language=context.language,
        )
        return StageResult(
            output=response,
            metadata={
                "alert_id": context.alert.id,
                "plan_id": response.plan.id,
                "recommendation_id": response.compilation.recommendation_id,
                "rules_matched": response.compilation.rules_matched,
                "actions_skipped": response.compilation.actions_skipped,
                "language": context.language,
            },
        )

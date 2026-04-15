from app.services.plan_compiler.service import PlanCompilerService
from app.workflows.stages.base import BaseStage, StageContext, StageResult


class CompilePlanStage(BaseStage):
    @property
    def name(self) -> str:
        return "compile_plan"

    def execute(self, context: StageContext) -> StageResult:
        service = PlanCompilerService(context.db)
        response = service.compile_for_alert(
            alert_id=context.alert.id,
            recommendation_id=context.previous_outputs.get("recommendation_id"),
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

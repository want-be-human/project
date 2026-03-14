"""
Workflow Engine – orchestrates stage execution with tracing.
Delegates actual analysis to existing AgentService via stage wrappers.
"""

import json
import time
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.utils import generate_uuid, utc_now, datetime_to_iso
from app.models.alert import Alert
from app.workflows.models import WorkflowExecution
from app.workflows.schemas import StageExecutionLog
from app.workflows.stages.base import BaseStage, StageContext
from app.workflows.stages.triage import TriageStage
from app.workflows.stages.investigation import InvestigationStage
from app.workflows.stages.recommendation import RecommendationStage
from app.workflows.stages.compile_plan import CompilePlanStage

logger = get_logger(__name__)

# Stage registry: maps stage name → Stage class
_STAGE_REGISTRY: dict[str, type[BaseStage]] = {
    "triage": TriageStage,
    "investigate": InvestigationStage,
    "recommend": RecommendationStage,
    "compile_plan": CompilePlanStage,
}


class WorkflowEngine:
    """
    Orchestrates agent workflow stages with execution trace recording.

    Usage:
        engine = WorkflowEngine(db)
        result = engine.run_stage("triage", alert, language="en")
    """

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_stage(
        self,
        stage_name: str,
        alert: Alert,
        language: str = "en",
        **kwargs: Any,
    ) -> Any:
        """
        Execute a single stage and record its execution trace.

        Returns the stage output (compatible with the original service return type).
        """
        stage_cls = _STAGE_REGISTRY.get(stage_name)
        if stage_cls is None:
            raise ValueError(f"Unknown stage: {stage_name}")

        stage = stage_cls()
        context = StageContext(
            alert=alert,
            language=language,
            previous_outputs=kwargs.get("previous_outputs", {}),
            db=self.db,
        )

        # Create execution record
        execution = self._create_execution(alert.id, stage_name)

        # Execute stage with timing
        stage_log = StageExecutionLog(
            stage_name=stage_name,
            status="running",
            started_at=datetime_to_iso(utc_now()),
            input_snapshot={"alert_id": alert.id, "language": language},
        )

        try:
            t0 = time.monotonic()
            result = stage.execute(context)
            elapsed_ms = (time.monotonic() - t0) * 1000

            stage_log.status = "completed"
            stage_log.completed_at = datetime_to_iso(utc_now())
            stage_log.latency_ms = round(elapsed_ms, 2)
            stage_log.output_snapshot = self._build_output_snapshot(stage_name, result.output)

            execution.status = "completed"
            execution.completed_at = utc_now()
            execution.stages_log = json.dumps(
                [stage_log.model_dump()], ensure_ascii=False
            )
            self.db.commit()

            logger.info(
                "Workflow stage '%s' completed for alert %s in %.1f ms",
                stage_name,
                alert.id,
                elapsed_ms,
            )
            return result.output

        except Exception:
            stage_log.status = "failed"
            stage_log.completed_at = datetime_to_iso(utc_now())
            stage_log.latency_ms = round((time.monotonic() - t0) * 1000, 2)
            stage_log.error = "Stage execution failed"

            execution.status = "failed"
            execution.completed_at = utc_now()
            execution.stages_log = json.dumps(
                [stage_log.model_dump()], ensure_ascii=False
            )
            try:
                self.db.commit()
            except Exception:
                self.db.rollback()

            raise

    def run_pipeline(
        self,
        stage_names: list[str],
        alert: Alert,
        language: str = "en",
    ) -> dict[str, Any]:
        """
        Run multiple stages sequentially, passing outputs forward.

        Returns a dict mapping stage_name → stage output.
        """
        execution = self._create_execution(alert.id, "full_pipeline")
        previous_outputs: dict[str, Any] = {}
        stage_logs: list[StageExecutionLog] = []

        for stage_name in stage_names:
            stage_cls = _STAGE_REGISTRY.get(stage_name)
            if stage_cls is None:
                raise ValueError(f"Unknown stage: {stage_name}")

            stage = stage_cls()
            context = StageContext(
                alert=alert,
                language=language,
                previous_outputs=previous_outputs,
                db=self.db,
            )

            stage_log = StageExecutionLog(
                stage_name=stage_name,
                status="running",
                started_at=datetime_to_iso(utc_now()),
                input_snapshot={"alert_id": alert.id, "language": language},
            )

            try:
                t0 = time.monotonic()
                result = stage.execute(context)
                elapsed_ms = (time.monotonic() - t0) * 1000

                stage_log.status = "completed"
                stage_log.completed_at = datetime_to_iso(utc_now())
                stage_log.latency_ms = round(elapsed_ms, 2)
                stage_log.output_snapshot = self._build_output_snapshot(stage_name, result.output)

                previous_outputs[stage_name] = result.output
                stage_logs.append(stage_log)

            except Exception:
                stage_log.status = "failed"
                stage_log.completed_at = datetime_to_iso(utc_now())
                stage_log.latency_ms = round((time.monotonic() - t0) * 1000, 2)
                stage_log.error = "Stage execution failed"
                stage_logs.append(stage_log)

                execution.status = "failed"
                execution.completed_at = utc_now()
                execution.stages_log = json.dumps(
                    [s.model_dump() for s in stage_logs], ensure_ascii=False
                )
                try:
                    self.db.commit()
                except Exception:
                    self.db.rollback()
                raise

        execution.status = "completed"
        execution.completed_at = utc_now()
        execution.stages_log = json.dumps(
            [s.model_dump() for s in stage_logs], ensure_ascii=False
        )
        self.db.commit()

        logger.info(
            "Workflow pipeline [%s] completed for alert %s",
            ", ".join(stage_names),
            alert.id,
        )
        return previous_outputs

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_execution(self, alert_id: str, workflow_type: str) -> WorkflowExecution:
        """Create and persist a new WorkflowExecution record."""
        execution = WorkflowExecution(
            id=generate_uuid(),
            alert_id=alert_id,
            workflow_type=workflow_type,
            status="running",
        )
        self.db.add(execution)
        self.db.flush()  # ensure id is available but defer final commit to caller
        return execution

    @staticmethod
    def _build_output_snapshot(stage_name: str, output: Any) -> dict[str, Any]:
        """Build a compact output snapshot for the execution log."""
        if stage_name == "triage":
            return {"triage_summary_length": len(output) if isinstance(output, str) else 0}
        if hasattr(output, "id"):
            return {"id": output.id}
        return {}

import json
import time
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
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

_STAGE_REGISTRY: dict[str, type[BaseStage]] = {
    "triage": TriageStage,
    "investigate": InvestigationStage,
    "recommend": RecommendationStage,
    "compile_plan": CompilePlanStage,
}

# triage 归入 investigate 阶段的 PipelineStage 枚举
_STAGE_TO_PIPELINE = {
    "triage": "investigate",
    "investigate": "investigate",
    "recommend": "recommend",
    "compile_plan": "compile_plan",
}


class WorkflowEngine:
    def __init__(self, db: Session):
        self.db = db

    def run_stage(
        self,
        stage_name: str,
        alert: Alert,
        language: str = "en",
        **kwargs: Any,
    ) -> Any:
        stage_cls = _STAGE_REGISTRY.get(stage_name)
        if stage_cls is None:
            raise ValueError(f"未知阶段: {stage_name}")

        stage = stage_cls()
        context = StageContext(
            alert=alert,
            language=language,
            previous_outputs=kwargs.get("previous_outputs", {}),
            db=self.db,
        )

        execution = self._create_exec(alert.id, stage_name)
        log = StageExecutionLog(
            stage_name=stage_name,
            status="running",
            started_at=datetime_to_iso(utc_now()),
            input_snapshot={"alert_id": alert.id, "language": language},
        )

        t0 = time.monotonic()
        try:
            result = stage.execute(context)
            elapsed = (time.monotonic() - t0) * 1000

            log.status = "completed"
            log.completed_at = datetime_to_iso(utc_now())
            log.latency_ms = round(elapsed, 2)
            log.output_snapshot = self._snapshot(stage_name, result.output)

            execution.status = "completed"
            execution.completed_at = utc_now()
            execution.stages_log = json.dumps([log.model_dump()], ensure_ascii=False)
            self.db.commit()

            logger.info(
                "工作流阶段 '%s' 已完成，告警 %s，耗时 %.1f ms",
                stage_name, alert.id, elapsed,
            )
            self._bridge(alert, log)
            return result.output

        except Exception:
            log.status = "failed"
            log.completed_at = datetime_to_iso(utc_now())
            log.latency_ms = round((time.monotonic() - t0) * 1000, 2)
            log.error = "阶段执行失败"

            execution.status = "failed"
            execution.completed_at = utc_now()
            execution.stages_log = json.dumps([log.model_dump()], ensure_ascii=False)
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
        execution = self._create_exec(alert.id, "full_pipeline")
        prev: dict[str, Any] = {}
        logs: list[StageExecutionLog] = []

        for stage_name in stage_names:
            stage_cls = _STAGE_REGISTRY.get(stage_name)
            if stage_cls is None:
                raise ValueError(f"未知阶段: {stage_name}")

            stage = stage_cls()
            context = StageContext(
                alert=alert,
                language=language,
                previous_outputs=prev,
                db=self.db,
            )
            log = StageExecutionLog(
                stage_name=stage_name,
                status="running",
                started_at=datetime_to_iso(utc_now()),
                input_snapshot={"alert_id": alert.id, "language": language},
            )

            t0 = time.monotonic()
            try:
                result = stage.execute(context)
                elapsed = (time.monotonic() - t0) * 1000

                log.status = "completed"
                log.completed_at = datetime_to_iso(utc_now())
                log.latency_ms = round(elapsed, 2)
                log.output_snapshot = self._snapshot(stage_name, result.output)

                prev[stage_name] = result.output
                logs.append(log)

            except Exception:
                log.status = "failed"
                log.completed_at = datetime_to_iso(utc_now())
                log.latency_ms = round((time.monotonic() - t0) * 1000, 2)
                log.error = "阶段执行失败"
                logs.append(log)

                execution.status = "failed"
                execution.completed_at = utc_now()
                execution.stages_log = json.dumps(
                    [s.model_dump() for s in logs], ensure_ascii=False
                )
                try:
                    self.db.commit()
                except Exception:
                    self.db.rollback()
                raise

        execution.status = "completed"
        execution.completed_at = utc_now()
        execution.stages_log = json.dumps(
            [s.model_dump() for s in logs], ensure_ascii=False
        )
        self.db.commit()

        logger.info(
            "工作流流水线 [%s] 已完成，告警 %s",
            ", ".join(stage_names), alert.id,
        )
        return prev

    def _create_exec(self, alert_id: str, workflow_type: str) -> WorkflowExecution:
        execution = WorkflowExecution(
            id=generate_uuid(),
            alert_id=alert_id,
            workflow_type=workflow_type,
            status="running",
        )
        self.db.add(execution)
        self.db.flush()
        return execution

    @staticmethod
    def _snapshot(stage_name: str, output: Any) -> dict[str, Any]:
        if stage_name == "triage":
            return {"triage_summary_length": len(output) if isinstance(output, str) else 0}
        if hasattr(output, "id"):
            return {"id": output.id}
        return {}

    def _bridge(self, alert: Alert, log: StageExecutionLog) -> None:
        if not settings.PIPELINE_OBSERVABILITY_ENABLED:
            return

        pipeline_stage = _STAGE_TO_PIPELINE.get(log.stage_name)
        if not pipeline_stage:
            return

        try:
            from app.models.pipeline import PipelineRunModel
            from app.services.pipeline.models import StageRecord
            from app.models.flow import Flow
            from app.models.alert import alert_flows as af_table

            row = (
                self.db.query(Flow.pcap_id)
                .join(af_table, af_table.c.flow_id == Flow.id)
                .filter(af_table.c.alert_id == alert.id)
                .first()
            )
            if not row:
                return
            pcap_id = row[0]

            run = (
                self.db.query(PipelineRunModel)
                .filter(PipelineRunModel.pcap_id == pcap_id)
                .order_by(PipelineRunModel.created_at.desc())
                .first()
            )
            if not run:
                return

            stages = json.loads(run.stages_log or "[]")
            record = StageRecord(
                stage_name=pipeline_stage,
                status=log.status,
                started_at=log.started_at,
                completed_at=log.completed_at,
                latency_ms=log.latency_ms,
                key_metrics=log.output_snapshot,
                input_summary=log.input_snapshot,
                output_summary=log.output_snapshot,
                error_summary=log.error,
            )

            # 替换同名阶段记录，否则追加
            for i, s in enumerate(stages):
                if s.get("stage_name") == pipeline_stage:
                    stages[i] = record.model_dump()
                    break
            else:
                stages.append(record.model_dump())

            run.stages_log = json.dumps(stages, ensure_ascii=False)
            self.db.flush()

        except Exception:
            logger.debug("桥接工作流阶段到流水线失败", exc_info=True)

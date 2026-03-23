"""
Workflow Engine – orchestrates stage execution with tracing.
Delegates actual analysis to existing AgentService via stage wrappers.
"""

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

# 阶段注册表：将阶段名映射到阶段类
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
    # 对外 API
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

        # 创建执行记录
        execution = self._create_execution(alert.id, stage_name)

        # 执行阶段并计时
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

            # 对接到流水线可观测性
            self._bridge_to_pipeline(alert, stage_log)

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
    # 内部辅助方法
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

    # ------------------------------------------------------------------
    # 流水线可观测性桥接
    # ------------------------------------------------------------------

    # 将工作流阶段名映射到 PipelineStage 枚举值
    _STAGE_TO_PIPELINE = {
        "triage": "investigate",       # triage is part of the investigate phase
        "investigate": "investigate",
        "recommend": "recommend",
        "compile_plan": "compile_plan",
    }

    def _bridge_to_pipeline(self, alert: Alert, stage_log: StageExecutionLog) -> None:
        """
        If pipeline observability is enabled, append the stage record
        to the corresponding PipelineRun (looked up by alert's pcap_id).
        """
        if not settings.PIPELINE_OBSERVABILITY_ENABLED:
            return
        try:
            from app.models.pipeline import PipelineRunModel
            from app.services.pipeline.models import StageRecord

            pipeline_stage = self._STAGE_TO_PIPELINE.get(stage_log.stage_name)
            if not pipeline_stage:
                return

            # 通过 alert 关联的 flow 查找 PCAP id
            from app.models.flow import Flow
            flow = (
                self.db.query(Flow.pcap_id)
                .join(
                    Alert.__table__.metadata.tables.get("alert_flows", None)
                    or self.db.execute(
                        __import__("sqlalchemy").text("SELECT 1")
                    ),  # 兜底分支（理论上不应触发）
                )
                .filter(Flow.pcap_id.isnot(None))
                .first()
            )
            # 更直接：通过 alert_flows → flow → pcap_id 查询
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

            # 查找该 pcap 对应的现有 pipeline run
            pipeline_run = (
                self.db.query(PipelineRunModel)
                .filter(PipelineRunModel.pcap_id == pcap_id)
                .order_by(PipelineRunModel.created_at.desc())
                .first()
            )
            if not pipeline_run:
                return

            import json as _json
            existing_stages = _json.loads(pipeline_run.stages_log or "[]")

            record = StageRecord(
                stage_name=pipeline_stage,
                status=stage_log.status,
                started_at=stage_log.started_at,
                completed_at=stage_log.completed_at,
                latency_ms=stage_log.latency_ms,
                key_metrics=stage_log.output_snapshot,
                input_summary=stage_log.input_snapshot,
                output_summary=stage_log.output_snapshot,
                error_summary=stage_log.error,
            )

            # 替换已存在阶段记录，或追加新记录
            replaced = False
            for i, s in enumerate(existing_stages):
                if s.get("stage_name") == pipeline_stage:
                    existing_stages[i] = record.model_dump()
                    replaced = True
                    break
            if not replaced:
                existing_stages.append(record.model_dump())

            pipeline_run.stages_log = _json.dumps(existing_stages, ensure_ascii=False)
            self.db.flush()

        except Exception:
            logger.debug("Failed to bridge workflow stage to pipeline", exc_info=True)

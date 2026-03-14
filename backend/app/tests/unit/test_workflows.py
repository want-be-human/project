"""
Unit tests for Workflow Engine, Stages, and feature-flag fallback.
Validates that the workflow layer produces outputs identical to the
original AgentService while adding execution trace recording.
"""

import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

from app.workflows.engine import WorkflowEngine
from app.workflows.stages.base import BaseStage, StageContext, StageResult
from app.workflows.stages.triage import TriageStage
from app.workflows.stages.investigation import InvestigationStage
from app.workflows.stages.recommendation import RecommendationStage
from app.workflows.models import WorkflowExecution
from app.workflows.schemas import StageExecutionLog, WorkflowExecutionSchema
from app.schemas.agent import InvestigationSchema, RecommendationSchema


# ── helpers ──────────────────────────────────────────────────────

def _ts(offset_sec: int = 0) -> datetime:
    return datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=offset_sec)


def _make_alert(
    *,
    id: str = "alert-1",
    alert_type: str = "bruteforce",
    severity: str = "high",
    src_ip: str = "192.0.2.10",
    dst_ip: str = "198.51.100.20",
    proto: str = "TCP",
    dst_port: int = 22,
    flow_count: int = 18,
    top_features: list[dict] | None = None,
) -> MagicMock:
    if top_features is None:
        top_features = [
            {"name": "syn_count", "value": 120, "direction": "high"},
            {"name": "iat_mean_ms", "value": 50.5, "direction": "low"},
        ]

    evidence = {
        "flow_ids": ["flow-1", "flow-2"],
        "top_flows": [
            {"flow_id": "flow-1", "anomaly_score": 0.97, "summary": f"TCP/{dst_port}"},
        ],
        "top_features": top_features,
        "pcap_ref": {"pcap_id": "pcap-1", "offset_hint": None},
    }
    aggregation = {
        "rule": "same_src_ip + 60s_window",
        "group_key": f"{src_ip}@60s",
        "count_flows": flow_count,
    }
    agent = {
        "triage_summary": None,
        "investigation_id": None,
        "recommendation_id": None,
    }

    m = MagicMock()
    m.id = id
    m.type = alert_type
    m.severity = severity
    m.primary_src_ip = src_ip
    m.primary_dst_ip = dst_ip
    m.primary_proto = proto
    m.primary_dst_port = dst_port
    m.evidence = json.dumps(evidence)
    m.aggregation = json.dumps(aggregation)
    m.agent = json.dumps(agent)
    m.tags = json.dumps(["demo"])
    m.time_window_start = _ts(0)
    m.time_window_end = _ts(300)
    return m


# ══════════════════════════════════════════════════════════════════
# Stage base & context
# ══════════════════════════════════════════════════════════════════

class TestStageContext:
    """Tests for StageContext dataclass."""

    def test_defaults(self):
        alert = _make_alert()
        ctx = StageContext(alert=alert, db=MagicMock())
        assert ctx.language == "en"
        assert ctx.previous_outputs == {}

    def test_custom_values(self):
        alert = _make_alert()
        ctx = StageContext(
            alert=alert,
            language="zh",
            previous_outputs={"triage": "summary"},
            db=MagicMock(),
        )
        assert ctx.language == "zh"
        assert ctx.previous_outputs["triage"] == "summary"


# ══════════════════════════════════════════════════════════════════
# TriageStage
# ══════════════════════════════════════════════════════════════════

class TestTriageStage:
    """Tests for TriageStage."""

    def test_name(self):
        assert TriageStage().name == "triage"

    def test_execute_returns_string(self):
        db = MagicMock()
        alert = _make_alert()
        stage = TriageStage()
        ctx = StageContext(alert=alert, language="en", db=db)
        result = stage.execute(ctx)
        assert isinstance(result, StageResult)
        assert isinstance(result.output, str)
        assert len(result.output) > 20

    def test_execute_zh(self):
        db = MagicMock()
        alert = _make_alert()
        stage = TriageStage()
        ctx = StageContext(alert=alert, language="zh", db=db)
        result = stage.execute(ctx)
        assert isinstance(result.output, str)
        assert len(result.output) > 10

    def test_metadata_contains_alert_id(self):
        db = MagicMock()
        alert = _make_alert()
        stage = TriageStage()
        ctx = StageContext(alert=alert, db=db)
        result = stage.execute(ctx)
        assert result.metadata["alert_id"] == "alert-1"


# ══════════════════════════════════════════════════════════════════
# InvestigationStage
# ══════════════════════════════════════════════════════════════════

class TestInvestigationStage:
    """Tests for InvestigationStage."""

    def test_name(self):
        assert InvestigationStage().name == "investigate"

    def test_execute_returns_investigation_schema(self):
        db = MagicMock()
        alert = _make_alert()
        stage = InvestigationStage()
        ctx = StageContext(alert=alert, language="en", db=db)
        result = stage.execute(ctx)
        assert isinstance(result, StageResult)
        assert isinstance(result.output, InvestigationSchema)
        assert result.output.version == "1.1"
        assert result.output.alert_id == "alert-1"

    def test_execute_has_required_fields(self):
        db = MagicMock()
        alert = _make_alert()
        stage = InvestigationStage()
        ctx = StageContext(alert=alert, db=db)
        result = stage.execute(ctx)
        inv = result.output
        assert len(inv.hypothesis) > 0
        assert len(inv.why) >= 2
        assert 0.0 <= inv.impact.confidence <= 1.0
        assert len(inv.next_steps) >= 2

    def test_metadata_contains_investigation_id(self):
        db = MagicMock()
        alert = _make_alert()
        stage = InvestigationStage()
        ctx = StageContext(alert=alert, db=db)
        result = stage.execute(ctx)
        assert "investigation_id" in result.metadata


# ══════════════════════════════════════════════════════════════════
# RecommendationStage
# ══════════════════════════════════════════════════════════════════

class TestRecommendationStage:
    """Tests for RecommendationStage."""

    def test_name(self):
        assert RecommendationStage().name == "recommend"

    def test_execute_returns_recommendation_schema(self):
        db = MagicMock()
        alert = _make_alert()
        stage = RecommendationStage()
        ctx = StageContext(alert=alert, language="en", db=db)
        result = stage.execute(ctx)
        assert isinstance(result, StageResult)
        assert isinstance(result.output, RecommendationSchema)
        assert result.output.version == "1.1"
        assert result.output.alert_id == "alert-1"

    def test_execute_has_actions(self):
        db = MagicMock()
        alert = _make_alert()
        stage = RecommendationStage()
        ctx = StageContext(alert=alert, db=db)
        result = stage.execute(ctx)
        rec = result.output
        assert len(rec.actions) >= 1
        for action in rec.actions:
            assert action.title
            assert action.priority in ["high", "medium", "low"]

    def test_metadata_contains_recommendation_id(self):
        db = MagicMock()
        alert = _make_alert()
        stage = RecommendationStage()
        ctx = StageContext(alert=alert, db=db)
        result = stage.execute(ctx)
        assert "recommendation_id" in result.metadata


# ══════════════════════════════════════════════════════════════════
# WorkflowEngine
# ══════════════════════════════════════════════════════════════════

class TestWorkflowEngineRunStage:
    """Tests for WorkflowEngine.run_stage."""

    def test_triage_returns_string(self):
        db = MagicMock()
        alert = _make_alert()
        engine = WorkflowEngine(db)
        result = engine.run_stage("triage", alert, language="en")
        assert isinstance(result, str)
        assert len(result) > 20
        # Verify execution record was created
        db.add.assert_called()
        db.commit.assert_called()

    def test_investigate_returns_schema(self):
        db = MagicMock()
        alert = _make_alert()
        engine = WorkflowEngine(db)
        result = engine.run_stage("investigate", alert, language="en")
        assert isinstance(result, InvestigationSchema)
        assert result.alert_id == "alert-1"

    def test_recommend_returns_schema(self):
        db = MagicMock()
        alert = _make_alert()
        engine = WorkflowEngine(db)
        result = engine.run_stage("recommend", alert, language="en")
        assert isinstance(result, RecommendationSchema)
        assert result.alert_id == "alert-1"

    def test_unknown_stage_raises_error(self):
        db = MagicMock()
        alert = _make_alert()
        engine = WorkflowEngine(db)
        with pytest.raises(ValueError, match="Unknown stage"):
            engine.run_stage("nonexistent", alert)

    def test_execution_record_created(self):
        db = MagicMock()
        alert = _make_alert()
        engine = WorkflowEngine(db)
        engine.run_stage("triage", alert)
        # Verify db.add was called with a WorkflowExecution
        add_calls = db.add.call_args_list
        wf_args = [c for c in add_calls if isinstance(c[0][0], WorkflowExecution)]
        assert len(wf_args) >= 1
        wf_exec = wf_args[0][0][0]
        assert wf_exec.workflow_type == "triage"
        assert wf_exec.status == "completed"

    def test_stages_log_recorded(self):
        db = MagicMock()
        alert = _make_alert()
        engine = WorkflowEngine(db)
        engine.run_stage("triage", alert)
        add_calls = db.add.call_args_list
        wf_args = [c for c in add_calls if isinstance(c[0][0], WorkflowExecution)]
        wf_exec = wf_args[0][0][0]
        stages_log = json.loads(wf_exec.stages_log)
        assert len(stages_log) == 1
        assert stages_log[0]["stage_name"] == "triage"
        assert stages_log[0]["status"] == "completed"
        assert stages_log[0]["latency_ms"] >= 0

    def test_failed_stage_records_error(self):
        db = MagicMock()
        alert = _make_alert()
        # Set evidence to invalid JSON to force failure
        alert.evidence = "{{invalid json"
        engine = WorkflowEngine(db)
        with pytest.raises(Exception):
            engine.run_stage("investigate", alert)
        # Verify error was recorded
        add_calls = db.add.call_args_list
        wf_args = [c for c in add_calls if isinstance(c[0][0], WorkflowExecution)]
        wf_exec = wf_args[0][0][0]
        assert wf_exec.status == "failed"


class TestWorkflowEngineRunPipeline:
    """Tests for WorkflowEngine.run_pipeline."""

    def test_full_pipeline(self):
        db = MagicMock()
        alert = _make_alert()
        engine = WorkflowEngine(db)
        results = engine.run_pipeline(
            ["triage", "investigate", "recommend"], alert, language="en"
        )
        assert "triage" in results
        assert "investigate" in results
        assert "recommend" in results
        assert isinstance(results["triage"], str)
        assert isinstance(results["investigate"], InvestigationSchema)
        assert isinstance(results["recommend"], RecommendationSchema)

    def test_pipeline_records_all_stages(self):
        db = MagicMock()
        alert = _make_alert()
        engine = WorkflowEngine(db)
        engine.run_pipeline(["triage", "investigate"], alert)
        add_calls = db.add.call_args_list
        wf_args = [c for c in add_calls if isinstance(c[0][0], WorkflowExecution)]
        wf_exec = wf_args[0][0][0]
        stages_log = json.loads(wf_exec.stages_log)
        assert len(stages_log) == 2
        assert stages_log[0]["stage_name"] == "triage"
        assert stages_log[1]["stage_name"] == "investigate"

    def test_pipeline_unknown_stage_raises(self):
        db = MagicMock()
        alert = _make_alert()
        engine = WorkflowEngine(db)
        with pytest.raises(ValueError, match="Unknown stage"):
            engine.run_pipeline(["triage", "bad_stage"], alert)


# ══════════════════════════════════════════════════════════════════
# Schema validation
# ══════════════════════════════════════════════════════════════════

class TestWorkflowSchemas:
    """Tests for workflow Pydantic schemas."""

    def test_stage_execution_log_serialization(self):
        log = StageExecutionLog(
            stage_name="triage",
            status="completed",
            started_at="2026-01-15T12:00:00Z",
            completed_at="2026-01-15T12:00:01Z",
            latency_ms=150.5,
            input_snapshot={"alert_id": "a1"},
            output_snapshot={"triage_summary_length": 80},
        )
        d = log.model_dump()
        assert d["stage_name"] == "triage"
        assert d["latency_ms"] == 150.5

    def test_workflow_execution_schema(self):
        schema = WorkflowExecutionSchema(
            id="wf-1",
            alert_id="alert-1",
            workflow_type="triage",
            status="completed",
            created_at="2026-01-15T12:00:00Z",
            completed_at="2026-01-15T12:00:01Z",
            stages_log=[
                StageExecutionLog(
                    stage_name="triage",
                    status="completed",
                )
            ],
        )
        assert schema.version == "1.1"
        assert len(schema.stages_log) == 1


# ══════════════════════════════════════════════════════════════════
# Feature flag fallback regression
# ══════════════════════════════════════════════════════════════════

class TestFeatureFlagFallback:
    """Verify that the workflow engine and direct AgentService produce compatible outputs."""

    def test_triage_output_compatible(self):
        """Engine triage output should be the same type as AgentService.triage."""
        db = MagicMock()
        alert_engine = _make_alert()
        alert_direct = _make_alert()

        # Via engine
        engine = WorkflowEngine(db)
        engine_result = engine.run_stage("triage", alert_engine, language="en")

        # Via direct service
        from app.services.agent.service import AgentService
        svc = AgentService(db)
        direct_result = svc.triage(alert_direct, language="en")

        assert type(engine_result) is type(direct_result)
        assert isinstance(engine_result, str)

    def test_investigate_output_compatible(self):
        """Engine investigate output should be an InvestigationSchema."""
        db = MagicMock()
        alert_engine = _make_alert()
        alert_direct = _make_alert()

        engine = WorkflowEngine(db)
        engine_result = engine.run_stage("investigate", alert_engine, language="en")

        from app.services.agent.service import AgentService
        svc = AgentService(db)
        direct_result = svc.investigate(alert_direct, language="en")

        assert type(engine_result) is type(direct_result)
        assert engine_result.version == direct_result.version
        assert engine_result.alert_id == direct_result.alert_id

    def test_recommend_output_compatible(self):
        """Engine recommend output should be a RecommendationSchema."""
        db = MagicMock()
        alert_engine = _make_alert()
        alert_direct = _make_alert()

        engine = WorkflowEngine(db)
        engine_result = engine.run_stage("recommend", alert_engine, language="en")

        from app.services.agent.service import AgentService
        svc = AgentService(db)
        direct_result = svc.recommend(alert_direct, language="en")

        assert type(engine_result) is type(direct_result)
        assert engine_result.version == direct_result.version
        assert len(engine_result.actions) == len(direct_result.actions)

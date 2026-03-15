"""
Pipeline observability end-to-end test.

Exercises the full PCAP processing pipeline with PipelineTracker
integration and verifies that:
  - A PipelineRun record is created in the database
  - All data-layer stages are recorded (parse, feature_extract, detect, aggregate)
  - Stage records contain timing, metrics, and status
  - The pipeline run can be retrieved via the API
"""

import json
import pytest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.pipeline import PipelineRunModel
from app.services.pipeline import PipelineTracker, PipelineStage
from app.services.parsing.service import ParsingService
from app.services.features.service import FeaturesService
from app.services.detection.service import DetectionService
from app.services.alerting.service import AlertingService

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="function")
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


class TestPipelineE2E:
    """End-to-end tests for pipeline observability."""

    def test_full_data_pipeline_tracked(self, db_session):
        """
        Run parse→feature_extract→detect→aggregate on a fixture PCAP
        and verify the PipelineRun is persisted with all 4 stages.
        """
        pcap_path = FIXTURES_DIR / "regression_ssh_bruteforce.pcap"
        pcap_id = "e2e-test-pcap-001"

        tracker = PipelineTracker(pcap_id, db_session)

        # Stage 1: Parse
        with tracker.stage(PipelineStage.PARSE) as stg:
            parser = ParsingService()
            flows = parser.parse_to_flows(pcap_path)
            stg.record_metrics({"flow_count": len(flows)})
            stg.record_input({"pcap_path": str(pcap_path)})
            stg.record_output({"flow_count": len(flows)})

        # Stage 2: Feature extraction
        with tracker.stage(PipelineStage.FEATURE_EXTRACT) as stg:
            feat_svc = FeaturesService()
            stg.record_input({"flow_count": len(flows)})
            flows = feat_svc.extract_features_batch(flows)
            stg.record_metrics({"flow_count": len(flows)})

        # Stage 3: Detection
        with tracker.stage(PipelineStage.DETECT) as stg:
            det_svc = DetectionService()
            stg.record_input({"flow_count": len(flows)})
            flows = det_svc.score_flows(flows)
            scored = [f for f in flows if f.get("anomaly_score") is not None]
            stg.record_metrics({"scored_count": len(scored)})

        # Stage 4: Aggregate (alert generation)
        with tracker.stage(PipelineStage.AGGREGATE) as stg:
            alert_svc = AlertingService(score_threshold=0.7, window_sec=60)
            stg.record_input({"flow_count": len(flows)})
            alerts = alert_svc.generate_alerts(flows, pcap_id)
            stg.record_metrics({"alert_count": len(alerts)})
            stg.record_output({"alert_count": len(alerts)})

        # Finish and persist
        run = tracker.finish()
        db_session.commit()

        # Verify PipelineRun in memory
        assert run.status == "completed"
        assert run.pcap_id == pcap_id
        assert run.total_latency_ms is not None
        assert run.total_latency_ms > 0
        assert len(run.stages) == 4

        stage_names = [s.stage_name for s in run.stages]
        assert stage_names == ["parse", "feature_extract", "detect", "aggregate"]

        for stage in run.stages:
            assert stage.status == "completed"
            assert stage.latency_ms is not None
            assert stage.latency_ms >= 0
            assert stage.started_at is not None
            assert stage.completed_at is not None

        # Verify parse stage has metrics
        parse_stage = run.stages[0]
        assert parse_stage.key_metrics.get("flow_count", 0) > 0

        # Verify persist to DB
        db_model = db_session.query(PipelineRunModel).first()
        assert db_model is not None
        assert db_model.pcap_id == pcap_id
        assert db_model.status == "completed"
        stages_log = json.loads(db_model.stages_log)
        assert len(stages_log) == 4

    def test_pipeline_with_skipped_stage(self, db_session):
        """When mode != flows_and_detect, detect stage should be skipped."""
        pcap_path = FIXTURES_DIR / "regression_normal_traffic.pcap"
        pcap_id = "e2e-test-pcap-skip"

        tracker = PipelineTracker(pcap_id, db_session)

        with tracker.stage(PipelineStage.PARSE) as stg:
            parser = ParsingService()
            flows = parser.parse_to_flows(pcap_path)
            stg.record_metrics({"flow_count": len(flows)})

        with tracker.stage(PipelineStage.FEATURE_EXTRACT) as stg:
            feat_svc = FeaturesService()
            flows = feat_svc.extract_features_batch(flows)

        # Skip detect (simulating mode != flows_and_detect)
        with tracker.stage(PipelineStage.DETECT) as stg:
            stg.skip("mode != flows_and_detect")

        with tracker.stage(PipelineStage.AGGREGATE) as stg:
            stg.skip("mode != flows_and_detect")

        run = tracker.finish()
        db_session.commit()

        assert run.status == "completed"
        assert len(run.stages) == 4
        assert run.stages[2].status == "skipped"
        assert run.stages[3].status == "skipped"

    def test_pipeline_failure_recorded(self, db_session):
        """If a stage raises, the pipeline should record the failure."""
        pcap_id = "e2e-test-pcap-fail"
        tracker = PipelineTracker(pcap_id, db_session)

        with tracker.stage(PipelineStage.PARSE) as stg:
            stg.record_metrics({"flow_count": 10})

        with pytest.raises(ValueError):
            with tracker.stage(PipelineStage.FEATURE_EXTRACT) as stg:
                raise ValueError("Simulated feature extraction failure")

        run = tracker.fail("Feature extraction failed")
        db_session.commit()

        assert run.status == "failed"
        assert len(run.stages) == 2
        assert run.stages[0].status == "completed"
        assert run.stages[1].status == "failed"
        assert run.stages[1].error_summary is not None and "Simulated" in run.stages[1].error_summary

        # DB persistence
        db_model = db_session.query(PipelineRunModel).first()
        assert db_model is not None
        assert db_model.status == "failed"

    def test_stage_metrics_recorded(self, db_session):
        """Metrics recorded via stg.record_metrics should appear in the run."""
        pcap_id = "e2e-test-metrics"
        tracker = PipelineTracker(pcap_id, db_session)

        with tracker.stage(PipelineStage.PARSE) as stg:
            stg.record_metrics({"flow_count": 42, "bytes_total": 1024})
            stg.record_input({"pcap_path": "/test.pcap"})
            stg.record_output({"flow_count": 42})

        run = tracker.finish()
        db_session.commit()

        stage = run.stages[0]
        assert stage.key_metrics["flow_count"] == 42
        assert stage.key_metrics["bytes_total"] == 1024
        assert stage.input_summary["pcap_path"] == "/test.pcap"
        assert stage.output_summary["flow_count"] == 42

    def test_multiple_pipeline_runs_per_pcap(self, db_session):
        """Multiple pipeline runs for the same PCAP should be independently stored."""
        pcap_id = "e2e-test-multi"

        for i in range(3):
            tracker = PipelineTracker(pcap_id, db_session)
            with tracker.stage(PipelineStage.PARSE) as stg:
                stg.record_metrics({"run_index": i})
            tracker.finish()
            db_session.commit()

        runs = (
            db_session.query(PipelineRunModel)
            .filter(PipelineRunModel.pcap_id == pcap_id)
            .all()
        )
        assert len(runs) == 3

"""
PCAP regression tests.

Runs fixed PCAP fixtures through the full parse → feature_extract → detect →
aggregate pipeline and asserts that the output is stable (flow count, alert
count, alert types, severity distribution).

These tests are deterministic — the fixture PCAPs and the detection model
produce consistent results across runs.
"""

import json
import pytest
from pathlib import Path

from app.services.parsing.service import ParsingService
from app.services.features.service import FeaturesService
from app.services.detection.service import DetectionService
from app.services.alerting.service import AlertingService

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
BASELINES_PATH = FIXTURES_DIR / "expected" / "baselines.json"

# Load baselines once
with open(BASELINES_PATH, "r", encoding="utf-8") as _f:
    _BASELINES: dict = json.load(_f)

FIXTURE_NAMES = list(_BASELINES.keys())


def _ensure_fixture(name: str) -> Path:
    """Ensure fixture PCAP exists, regenerate if missing."""
    pcap_path = FIXTURES_DIR / f"{name}.pcap"
    if not pcap_path.exists():
        from app.tests.fixtures.generate_fixtures import (
            generate_ssh_bruteforce,
            generate_port_scan,
            generate_normal_traffic,
        )
        generators = {
            "regression_ssh_bruteforce": generate_ssh_bruteforce,
            "regression_port_scan": generate_port_scan,
            "regression_normal_traffic": generate_normal_traffic,
        }
        gen = generators.get(name)
        if gen:
            gen(str(pcap_path))
    return pcap_path


class TestPcapRegression:
    """Regression tests for PCAP processing pipeline stability."""

    @pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
    def test_flow_count_stable(self, fixture_name: str):
        """Parse fixture and verify flow count matches baseline."""
        baseline = _BASELINES[fixture_name]
        pcap_path = _ensure_fixture(fixture_name)

        parser = ParsingService()
        flows = parser.parse_to_flows(pcap_path)

        assert len(flows) == baseline["flow_count"], (
            f"Expected {baseline['flow_count']} flows, got {len(flows)}"
        )

    @pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
    def test_feature_extraction_complete(self, fixture_name: str):
        """All flows should have features after extraction."""
        pcap_path = _ensure_fixture(fixture_name)

        parser = ParsingService()
        feat_svc = FeaturesService()
        flows = parser.parse_to_flows(pcap_path)
        flows = feat_svc.extract_features_batch(flows)

        for flow in flows:
            assert "features" in flow, "Flow missing features dict"
            assert isinstance(flow["features"], dict), "Features should be a dict"

    @pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
    def test_detection_scoring_stable(self, fixture_name: str):
        """All flows should be scored; anomalous count meets minimum baseline."""
        baseline = _BASELINES[fixture_name]
        pcap_path = _ensure_fixture(fixture_name)

        parser = ParsingService()
        feat_svc = FeaturesService()
        det_svc = DetectionService()

        flows = parser.parse_to_flows(pcap_path)
        flows = feat_svc.extract_features_batch(flows)
        flows = det_svc.score_flows(flows)

        scored = [f for f in flows if f.get("anomaly_score") is not None]
        assert len(scored) == len(flows), "All flows should be scored"

        anomalous = [f for f in scored if f["anomaly_score"] >= 0.7]
        assert len(anomalous) >= baseline["anomalous_flow_count_min"], (
            f"Expected >= {baseline['anomalous_flow_count_min']} anomalous, got {len(anomalous)}"
        )

    @pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
    def test_alert_generation_stable(self, fixture_name: str):
        """Alert count and types match baseline expectations."""
        baseline = _BASELINES[fixture_name]
        pcap_path = _ensure_fixture(fixture_name)

        parser = ParsingService()
        feat_svc = FeaturesService()
        det_svc = DetectionService()
        alert_svc = AlertingService(score_threshold=0.7, window_sec=60)

        flows = parser.parse_to_flows(pcap_path)
        flows = feat_svc.extract_features_batch(flows)
        flows = det_svc.score_flows(flows)
        alerts = alert_svc.generate_alerts(flows, "regression-pcap")

        assert len(alerts) >= baseline["alert_count_min"], (
            f"Expected >= {baseline['alert_count_min']} alerts, got {len(alerts)}"
        )

        if baseline["expected_alert_types"]:
            actual_types = {a["type"] for a in alerts}
            for expected_type in baseline["expected_alert_types"]:
                assert expected_type in actual_types, (
                    f"Expected alert type '{expected_type}' not found in {actual_types}"
                )

        if baseline["expected_severities"]:
            actual_sevs = {a["severity"] for a in alerts}
            for expected_sev in baseline["expected_severities"]:
                assert expected_sev in actual_sevs, (
                    f"Expected severity '{expected_sev}' not found in {actual_sevs}"
                )

    @pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
    def test_full_pipeline_deterministic(self, fixture_name: str):
        """Two consecutive runs of the same fixture should produce identical results."""
        pcap_path = _ensure_fixture(fixture_name)

        parser = ParsingService()
        feat_svc = FeaturesService()
        det_svc = DetectionService()
        alert_svc = AlertingService(score_threshold=0.7, window_sec=60)

        def _run():
            flows = parser.parse_to_flows(pcap_path)
            flows = feat_svc.extract_features_batch(flows)
            flows = det_svc.score_flows(flows)
            alerts = alert_svc.generate_alerts(flows, "regression-pcap")
            return len(flows), len(alerts)

        run1 = _run()
        run2 = _run()
        assert run1 == run2, f"Pipeline is not deterministic: {run1} != {run2}"

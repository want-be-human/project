"""
Scenario regression tests.

Uses fixed scenario definitions against fixture PCAPs to ensure
the full analysis pipeline (parse → detect → aggregate → scenario check)
produces stable, verifiable results.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
from app.services.parsing.service import ParsingService
from app.services.features.service import FeaturesService
from app.services.detection.service import DetectionService
from app.services.alerting.service import AlertingService

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _ts() -> datetime:
    return datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


def _generate_alerts_from_fixture(fixture_name: str) -> list[dict]:
    """Run the full data pipeline on a fixture PCAP and return alert dicts."""
    pcap_path = FIXTURES_DIR / f"{fixture_name}.pcap"
    parser = ParsingService()
    feat_svc = FeaturesService()
    det_svc = DetectionService()
    alert_svc = AlertingService(score_threshold=0.7, window_sec=60)

    flows = parser.parse_to_flows(pcap_path)
    flows = feat_svc.extract_features_batch(flows)
    flows = det_svc.score_flows(flows)
    return alert_svc.generate_alerts(flows, "scenario-regression")


def _mock_alert_from_dict(ad: dict) -> MagicMock:
    """Convert an alert dict to a mock alert object matching ScenariosService expectations."""
    m = MagicMock()
    m.id = ad["id"]
    m.type = ad["type"]
    m.severity = ad["severity"]
    m.evidence = ad["evidence"] if isinstance(ad["evidence"], str) else json.dumps(ad["evidence"])
    m.agent = ad["agent"] if isinstance(ad["agent"], str) else json.dumps(ad["agent"])
    m.twin = ad["twin"] if isinstance(ad["twin"], str) else json.dumps(ad["twin"])
    m.created_at = ad.get("created_at", _ts())
    return m


def _make_scenario_model(
    *,
    scenario_id: str,
    name: str,
    pcap_id: str,
    expectations: dict,
    tags: list[str],
) -> MagicMock:
    """Build a mock scenario ORM model."""
    payload = {"expectations": expectations, "tags": tags}
    m = MagicMock()
    m.id = scenario_id
    m.created_at = _ts()
    m.version = "1.1"
    m.name = name
    m.description = f"Regression scenario: {name}"
    m.pcap_id = pcap_id
    m.payload = json.dumps(payload)
    return m


class TestScenarioRegression:
    """Regression tests using fixed scenarios against fixture PCAPs."""

    def test_ssh_bruteforce_scenario_passes(self):
        """
        SSH brute-force fixture should produce alerts that satisfy
        scenario expectations (min_alerts >= 1, must_have bruteforce).
        """
        alerts = _generate_alerts_from_fixture("regression_ssh_bruteforce")
        assert len(alerts) >= 1, "SSH brute-force fixture should produce at least 1 alert"

        # Verify alert types match expectations
        alert_types = {a["type"] for a in alerts}
        assert "bruteforce" in alert_types, "Expected bruteforce alert type"

        # Verify all alerts have the required structure
        for alert in alerts:
            assert "severity" in alert
            assert "evidence" in alert
            assert "type" in alert

        # Check that severities are at least medium
        severity_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        for alert in alerts:
            sev_val = severity_order.get(alert["severity"], -1)
            assert sev_val >= severity_order["medium"], (
                f"Alert severity {alert['severity']} is below 'medium'"
            )

    def test_normal_traffic_no_alerts(self):
        """Normal traffic fixture should produce 0 alerts."""
        alerts = _generate_alerts_from_fixture("regression_normal_traffic")
        assert len(alerts) == 0, "Normal traffic should produce no alerts"

    def test_port_scan_no_alerts(self):
        """Port scan fixture (below threshold) should produce 0 alerts."""
        alerts = _generate_alerts_from_fixture("regression_port_scan")
        assert len(alerts) == 0, "Port scan fixture should produce no alerts with default threshold"

    def test_scenario_results_deterministic(self):
        """Two runs of the same scenario should produce identical results."""
        run1 = _generate_alerts_from_fixture("regression_ssh_bruteforce")
        run2 = _generate_alerts_from_fixture("regression_ssh_bruteforce")
        assert len(run1) == len(run2), "Alert count should be deterministic"
        for a1, a2 in zip(run1, run2):
            assert a1["type"] == a2["type"]
            assert a1["severity"] == a2["severity"]

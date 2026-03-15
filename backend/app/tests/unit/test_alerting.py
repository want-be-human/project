"""
Unit tests for AlertingService.
Covers DOC B B4.5 & DOC B B6 requirements:
  - generate_alerts:合成 flows → alerts 数量与 evidence 正确
"""

from datetime import datetime, timezone, timedelta

from app.services.alerting.service import AlertingService


def _make_flow(
    *,
    src_ip: str = "192.0.2.10",
    dst_ip: str = "198.51.100.20",
    dst_port: int = 22,
    proto: str = "TCP",
    anomaly_score: float = 0.95,
    ts_start: datetime | None = None,
    ts_end: datetime | None = None,
    flow_id: str | None = None,
    features: dict | None = None,
) -> dict:
    """Build a minimal flow dict for testing."""
    now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    return {
        "id": flow_id or f"flow-{id(dst_port)}",
        "src_ip": src_ip,
        "dst_ip": dst_ip,
        "src_port": 54321,
        "dst_port": dst_port,
        "proto": proto,
        "anomaly_score": anomaly_score,
        "ts_start": ts_start or now,
        "ts_end": ts_end or (now + timedelta(seconds=5)),
        "features": features or {"syn_count": 15, "total_packets": 120, "rst_ratio": 0.0},
        "packets_fwd": 100,
        "packets_bwd": 20,
        "bytes_fwd": 8000,
        "bytes_bwd": 1200,
    }


# --------------- TestGenerateAlerts ---------------

class TestGenerateAlerts:
    """Tests for AlertingService.generate_alerts."""

    def test_no_anomalous_flows_returns_empty(self):
        """Flows below threshold produce no alerts."""
        svc = AlertingService(score_threshold=0.7)
        flows = [_make_flow(anomaly_score=0.3), _make_flow(anomaly_score=0.5)]
        alerts = svc.generate_alerts(flows, pcap_id="pcap-1")
        assert alerts == []

    def test_single_group_single_alert(self):
        """Multiple flows from same src_ip + same window → one alert."""
        svc = AlertingService(score_threshold=0.7, window_sec=60)
        base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        flows = [
            _make_flow(src_ip="10.0.0.1", anomaly_score=0.9,
                       ts_start=base, flow_id="f1"),
            _make_flow(src_ip="10.0.0.1", anomaly_score=0.85,
                       ts_start=base + timedelta(seconds=10), flow_id="f2"),
            _make_flow(src_ip="10.0.0.1", anomaly_score=0.8,
                       ts_start=base + timedelta(seconds=30), flow_id="f3"),
        ]
        alerts = svc.generate_alerts(flows, pcap_id="pcap-1")
        assert len(alerts) == 1

    def test_different_src_ips_multiple_alerts(self):
        """Flows from different src_ip → separate alerts."""
        svc = AlertingService(score_threshold=0.7, window_sec=60)
        base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        flows = [
            _make_flow(src_ip="10.0.0.1", anomaly_score=0.9, ts_start=base, flow_id="f1"),
            _make_flow(src_ip="10.0.0.2", anomaly_score=0.85, ts_start=base, flow_id="f2"),
        ]
        alerts = svc.generate_alerts(flows, pcap_id="pcap-1")
        assert len(alerts) == 2

    def test_different_time_windows_multiple_alerts(self):
        """Same src_ip but different time buckets → separate alerts."""
        svc = AlertingService(score_threshold=0.7, window_sec=60)
        t1 = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        t2 = t1 + timedelta(seconds=120)  # 2 minutes later → different bucket
        flows = [
            _make_flow(src_ip="10.0.0.1", anomaly_score=0.9, ts_start=t1, flow_id="f1"),
            _make_flow(src_ip="10.0.0.1", anomaly_score=0.85, ts_start=t2, flow_id="f2"),
        ]
        alerts = svc.generate_alerts(flows, pcap_id="pcap-1")
        assert len(alerts) == 2

    def test_alert_has_required_fields(self):
        """Generated alert dict contains all DOC C required field keys."""
        svc = AlertingService(score_threshold=0.5)
        flows = [_make_flow(anomaly_score=0.9, flow_id="flow-1")]
        alerts = svc.generate_alerts(flows, pcap_id="pcap-1")
        assert len(alerts) == 1
        alert = alerts[0]

        required_keys = {
            "id", "version", "created_at", "severity", "status", "type",
            "time_window_start", "time_window_end",
            "primary_src_ip", "primary_dst_ip", "primary_proto", "primary_dst_port",
            "evidence", "aggregation", "agent", "twin", "tags", "notes",
        }
        assert required_keys.issubset(alert.keys())

    def test_evidence_contains_flow_ids(self):
        """Evidence JSON includes flow_ids list."""
        import json
        svc = AlertingService(score_threshold=0.5)
        flows = [_make_flow(anomaly_score=0.95, flow_id="flow-abc")]
        alerts = svc.generate_alerts(flows, pcap_id="pcap-1")
        evidence = json.loads(alerts[0]["evidence"])
        assert "flow-abc" in evidence["flow_ids"]

    def test_evidence_top_flows_present(self):
        """Evidence JSON includes top_flows list."""
        import json
        svc = AlertingService(score_threshold=0.5)
        flows = [_make_flow(anomaly_score=0.95, flow_id="flow-1")]
        alerts = svc.generate_alerts(flows, pcap_id="pcap-1")
        evidence = json.loads(alerts[0]["evidence"])
        assert len(evidence["top_flows"]) >= 1
        assert evidence["top_flows"][0]["flow_id"] == "flow-1"

    def test_evidence_pcap_ref(self):
        """Evidence JSON includes pcap_ref with correct pcap_id."""
        import json
        svc = AlertingService(score_threshold=0.5)
        flows = [_make_flow(anomaly_score=0.95)]
        alerts = svc.generate_alerts(flows, pcap_id="pcap-xyz")
        evidence = json.loads(alerts[0]["evidence"])
        assert evidence["pcap_ref"]["pcap_id"] == "pcap-xyz"

    def test_aggregation_rule_format(self):
        """Aggregation rule matches 'same_src_ip + {window}s_window'."""
        import json
        svc = AlertingService(score_threshold=0.5, window_sec=120)
        flows = [_make_flow(anomaly_score=0.95)]
        alerts = svc.generate_alerts(flows, pcap_id="pcap-1")
        agg = json.loads(alerts[0]["aggregation"])
        assert agg["rule"] == "same_src_ip + 120s_window"
        assert agg["count_flows"] == 1


# --------------- TestSeverityMapping ---------------

class TestSeverityMapping:
    """Tests for severity calculation."""

    def test_critical_severity(self):
        svc = AlertingService(score_threshold=0.5)
        flows = [_make_flow(anomaly_score=0.96)]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        assert alerts[0]["severity"] == "critical"

    def test_high_severity(self):
        svc = AlertingService(score_threshold=0.5)
        flows = [_make_flow(anomaly_score=0.88)]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        assert alerts[0]["severity"] == "high"

    def test_medium_severity(self):
        svc = AlertingService(score_threshold=0.5)
        flows = [_make_flow(anomaly_score=0.75)]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        assert alerts[0]["severity"] == "medium"

    def test_low_severity(self):
        svc = AlertingService(score_threshold=0.1)
        flows = [_make_flow(anomaly_score=0.15)]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        assert alerts[0]["severity"] == "low"


# --------------- TestAlertType ---------------

class TestAlertType:
    """Tests for alert type detection heuristics."""

    def test_scan_many_dst_ports(self):
        """Many distinct dst_ports → scan type."""
        svc = AlertingService(score_threshold=0.5)
        base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        flows = [
            _make_flow(anomaly_score=0.9, dst_port=p, ts_start=base, flow_id=f"f-{p}")
            for p in range(22, 45)  # 23 unique ports
        ]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        assert alerts[0]["type"] == "scan"

    def test_default_anomaly_type(self):
        """Single normal flow → anomaly type."""
        svc = AlertingService(score_threshold=0.5)
        flows = [_make_flow(anomaly_score=0.9, features={"syn_count": 1, "total_packets": 5})]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        assert alerts[0]["type"] == "anomaly"


# --------------- TestFlowIdsMetadata ---------------

class TestFlowIdsMetadata:
    """Tests for _flow_ids metadata needed for alert_flows insertion."""

    def test_flow_ids_in_output(self):
        """Alert dict should have _flow_ids list for DB association."""
        svc = AlertingService(score_threshold=0.5)
        flows = [
            _make_flow(anomaly_score=0.9, flow_id="f1"),
            _make_flow(anomaly_score=0.85, flow_id="f2"),
        ]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        # All alerts combined should reference both flow IDs
        all_fids = []
        for a in alerts:
            all_fids.extend(a.get("_flow_ids", []))
        assert "f1" in all_fids
        assert "f2" in all_fids

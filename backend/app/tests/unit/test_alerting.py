"""
Unit tests for AlertingService.
Covers DOC B B4.5 & DOC B B6 requirements:
  - generate_alerts:合成 flows → alerts 数量与 evidence 正确
  - 多维聚合键拆分逻辑
  - 复合严重度评分
"""

import json
from datetime import datetime, timezone, timedelta

from app.services.alerting.service import AlertingService


def _make_flow(
    *,
    src_ip: str = "192.0.2.10",
    dst_ip: str = "198.51.100.20",
    dst_port: int = 443,
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
        "features": features or {"syn_count": 2, "total_packets": 50, "rst_ratio": 0.0},
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
        """同源同目标同服务同时间窗 → 一条告警。"""
        svc = AlertingService(score_threshold=0.7, window_sec=60)
        base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        flows = [
            _make_flow(src_ip="10.0.0.1", dst_ip="10.0.0.2", dst_port=443,
                       anomaly_score=0.9, ts_start=base, flow_id="f1"),
            _make_flow(src_ip="10.0.0.1", dst_ip="10.0.0.2", dst_port=443,
                       anomaly_score=0.85, ts_start=base + timedelta(seconds=10), flow_id="f2"),
            _make_flow(src_ip="10.0.0.1", dst_ip="10.0.0.2", dst_port=443,
                       anomaly_score=0.8, ts_start=base + timedelta(seconds=30), flow_id="f3"),
        ]
        alerts = svc.generate_alerts(flows, pcap_id="pcap-1")
        assert len(alerts) == 1

    def test_different_src_ips_multiple_alerts(self):
        """不同源 IP → 拆分为不同告警。"""
        svc = AlertingService(score_threshold=0.7, window_sec=60)
        base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        flows = [
            _make_flow(src_ip="10.0.0.1", anomaly_score=0.9, ts_start=base, flow_id="f1"),
            _make_flow(src_ip="10.0.0.2", anomaly_score=0.85, ts_start=base, flow_id="f2"),
        ]
        alerts = svc.generate_alerts(flows, pcap_id="pcap-1")
        assert len(alerts) == 2

    def test_different_time_windows_multiple_alerts(self):
        """同源但不同时间桶 → 拆分为不同告警。"""
        svc = AlertingService(score_threshold=0.7, window_sec=60)
        t1 = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        t2 = t1 + timedelta(seconds=120)  # 不同桶
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
        svc = AlertingService(score_threshold=0.5)
        flows = [_make_flow(anomaly_score=0.95, flow_id="flow-abc")]
        alerts = svc.generate_alerts(flows, pcap_id="pcap-1")
        evidence = json.loads(alerts[0]["evidence"])
        assert "flow-abc" in evidence["flow_ids"]

    def test_evidence_top_flows_present(self):
        """Evidence JSON includes top_flows list."""
        svc = AlertingService(score_threshold=0.5)
        flows = [_make_flow(anomaly_score=0.95, flow_id="flow-1")]
        alerts = svc.generate_alerts(flows, pcap_id="pcap-1")
        evidence = json.loads(alerts[0]["evidence"])
        assert len(evidence["top_flows"]) >= 1
        assert evidence["top_flows"][0]["flow_id"] == "flow-1"

    def test_evidence_pcap_ref(self):
        """Evidence JSON includes pcap_ref with correct pcap_id."""
        svc = AlertingService(score_threshold=0.5)
        flows = [_make_flow(anomaly_score=0.95)]
        alerts = svc.generate_alerts(flows, pcap_id="pcap-xyz")
        evidence = json.loads(alerts[0]["evidence"])
        assert evidence["pcap_ref"]["pcap_id"] == "pcap-xyz"

    def test_aggregation_rule_format(self):
        """Aggregation rule 使用新的多维格式。"""
        svc = AlertingService(score_threshold=0.5, window_sec=120)
        flows = [_make_flow(anomaly_score=0.95)]
        alerts = svc.generate_alerts(flows, pcap_id="pcap-1")
        agg = json.loads(alerts[0]["aggregation"])
        assert agg["rule"] == "src_ip+dst_target+service+type+120s_window"
        assert agg["count_flows"] == 1


# --------------- TestMultiDimensionAggregation ---------------

class TestMultiDimensionAggregation:
    """测试多维聚合键拆分逻辑。"""

    def test_same_src_different_inferred_type_splits(self):
        """同源 IP 同时间窗，但推断类型不同（anomaly vs bruteforce）→ 拆分。"""
        svc = AlertingService(score_threshold=0.7, window_sec=60)
        base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        # anomaly 类型流（普通端口，低 SYN 比例）
        f_anomaly = _make_flow(
            src_ip="10.0.0.1", dst_ip="10.0.0.2", dst_port=8080,
            anomaly_score=0.9, ts_start=base, flow_id="f-anomaly",
            features={"syn_count": 1, "total_packets": 50, "rst_ratio": 0.0},
        )
        # bruteforce 类型流（SSH 端口）
        f_brute = _make_flow(
            src_ip="10.0.0.1", dst_ip="10.0.0.2", dst_port=22,
            anomaly_score=0.88, ts_start=base, flow_id="f-brute",
            features={"syn_count": 1, "total_packets": 50, "rst_ratio": 0.0},
        )
        alerts = svc.generate_alerts([f_anomaly, f_brute], pcap_id="p1")
        assert len(alerts) == 2

    def test_same_src_different_dst_ip_splits(self):
        """同源 IP 同时间窗同推断类型，但不同目标 IP → 拆分。"""
        svc = AlertingService(score_threshold=0.7, window_sec=60)
        base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        f1 = _make_flow(
            src_ip="10.0.0.1", dst_ip="10.0.0.2", dst_port=8080,
            anomaly_score=0.9, ts_start=base, flow_id="f1",
        )
        f2 = _make_flow(
            src_ip="10.0.0.1", dst_ip="10.0.0.3", dst_port=8080,
            anomaly_score=0.85, ts_start=base, flow_id="f2",
        )
        alerts = svc.generate_alerts([f1, f2], pcap_id="p1")
        assert len(alerts) == 2

    def test_same_src_different_service_splits(self):
        """同源同目标 IP，但不同服务端口 → 拆分。"""
        svc = AlertingService(score_threshold=0.7, window_sec=60)
        base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        f1 = _make_flow(
            src_ip="10.0.0.1", dst_ip="10.0.0.2", dst_port=80,
            anomaly_score=0.9, ts_start=base, flow_id="f1",
        )
        f2 = _make_flow(
            src_ip="10.0.0.1", dst_ip="10.0.0.2", dst_port=443,
            anomaly_score=0.85, ts_start=base, flow_id="f2",
        )
        alerts = svc.generate_alerts([f1, f2], pcap_id="p1")
        assert len(alerts) == 2

    def test_scan_flows_merge_to_single_alert(self):
        """scan 推断类型的流合并目标维度为 multi，不会按端口拆分。"""
        svc = AlertingService(score_threshold=0.5, window_sec=60)
        base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        # 高 SYN 比例 → 推断为 scan
        scan_features = {"syn_count": 80, "total_packets": 100, "rst_ratio": 0.0}
        flows = [
            _make_flow(
                src_ip="10.0.0.1", dst_ip=f"10.0.0.{i}", dst_port=p,
                anomaly_score=0.9, ts_start=base, flow_id=f"f-{p}",
                features=scan_features,
            )
            for i, p in enumerate(range(22, 35), start=2)
        ]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        # 所有 scan 流应合并为一条告警（dst_target=multi, service_key=multi）
        assert len(alerts) == 1


# --------------- TestSeverityMapping ---------------

class TestSeverityMapping:
    """测试复合严重度评分。"""

    def test_critical_severity_multi_flow(self):
        """20+ 高分流持续 5 分钟（大窗口聚合）→ critical。"""
        svc = AlertingService(score_threshold=0.7, window_sec=600)
        base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        flows = [
            _make_flow(
                anomaly_score=0.95,
                ts_start=base + timedelta(seconds=i * 15),
                ts_end=base + timedelta(seconds=i * 15 + 5),
                flow_id=f"f{i}",
            )
            for i in range(20)
        ]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        assert alerts[0]["severity"] == "critical"

    def test_high_severity_moderate_cluster(self):
        """10 条中高分流持续 2 分钟 → high。"""
        svc = AlertingService(score_threshold=0.7)
        base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        flows = [
            _make_flow(
                anomaly_score=0.9,
                ts_start=base + timedelta(seconds=i * 12),
                ts_end=base + timedelta(seconds=i * 12 + 5),
                flow_id=f"f{i}",
            )
            for i in range(10)
        ]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        assert alerts[0]["severity"] == "high"

    def test_medium_severity_single_flow(self):
        """单条高分流 → medium（复合分数不足以达到 high）。"""
        svc = AlertingService(score_threshold=0.5)
        flows = [_make_flow(anomaly_score=0.9)]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        assert alerts[0]["severity"] == "medium"

    def test_low_severity(self):
        """单条低分流 → low。"""
        svc = AlertingService(score_threshold=0.1)
        flows = [_make_flow(anomaly_score=0.15)]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        assert alerts[0]["severity"] == "low"


# --------------- TestCompositeScoring ---------------

class TestCompositeScoring:
    """测试复合分数计算细节。"""

    def test_composite_score_in_aggregation(self):
        """aggregation JSON 包含 composite_score 和 score_breakdown。"""
        svc = AlertingService(score_threshold=0.5)
        flows = [_make_flow(anomaly_score=0.95)]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        agg = json.loads(alerts[0]["aggregation"])
        assert "composite_score" in agg
        assert "score_breakdown" in agg
        assert "dimensions" in agg
        breakdown = agg["score_breakdown"]
        assert set(breakdown.keys()) == {
            "max_score", "flow_density", "duration_factor",
            "aggregation_quality", "composite",
        }

    def test_single_flow_not_critical(self):
        """单条 0.96 分流不应为 critical（需要规模/持续性支撑）。"""
        svc = AlertingService(score_threshold=0.5)
        flows = [_make_flow(anomaly_score=0.96)]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        assert alerts[0]["severity"] != "critical"

    def test_many_flows_boost_composite(self):
        """大量流提升 flow_density 因子，拉高复合分数。"""
        svc = AlertingService(score_threshold=0.5, window_sec=600)
        base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        flows = [
            _make_flow(
                anomaly_score=0.85,
                ts_start=base + timedelta(seconds=i * 15),
                ts_end=base + timedelta(seconds=i * 15 + 5),
                flow_id=f"f{i}",
            )
            for i in range(25)
        ]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        agg = json.loads(alerts[0]["aggregation"])
        # flow_density 应为 1.0（25/20 capped）
        assert agg["score_breakdown"]["flow_density"] == 1.0
        # 复合分数应显著高于单流场景
        assert agg["composite_score"] > 0.7


# --------------- TestAlertType ---------------

class TestAlertType:
    """Tests for alert type detection heuristics."""

    def test_scan_many_dst_ports(self):
        """多目标端口 + scan 推断 → scan 类型。"""
        svc = AlertingService(score_threshold=0.5)
        base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        # 高 SYN 比例确保推断为 scan，合并到同一组
        scan_features = {"syn_count": 80, "total_packets": 100, "rst_ratio": 0.0}
        flows = [
            _make_flow(
                anomaly_score=0.9, dst_port=p, dst_ip=f"10.0.0.{i}",
                ts_start=base, flow_id=f"f-{p}",
                features=scan_features,
            )
            for i, p in enumerate(range(22, 45), start=2)
        ]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        assert alerts[0]["type"] == "scan"

    def test_default_anomaly_type(self):
        """单条普通流 → anomaly 类型。"""
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


# --------------- TestInferFlowType ---------------

class TestInferFlowType:
    """测试单流类型推断（聚合分组用）。"""

    def test_scan_high_syn_ratio(self):
        """SYN 比例 > 0.5 → scan。"""
        flow = _make_flow(features={"syn_count": 80, "total_packets": 100})
        assert AlertingService._infer_flow_type(flow) == "scan"

    def test_bruteforce_ssh_port(self):
        """SSH 端口 → bruteforce。"""
        flow = _make_flow(dst_port=22, features={"syn_count": 1, "total_packets": 10})
        assert AlertingService._infer_flow_type(flow) == "bruteforce"

    def test_dos_high_bytes(self):
        """单流 >200KB → dos。"""
        flow = _make_flow(dst_port=80, features={"syn_count": 1, "total_packets": 10, "total_bytes": 300000})
        assert AlertingService._infer_flow_type(flow) == "dos"

    def test_anomaly_default(self):
        """普通流 → anomaly。"""
        flow = _make_flow(dst_port=8080, features={"syn_count": 1, "total_packets": 10})
        assert AlertingService._infer_flow_type(flow) == "anomaly"

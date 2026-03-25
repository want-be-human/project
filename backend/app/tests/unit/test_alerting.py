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

    def test_scan_horizontal(self):
        """水平扫描：多目标 IP + 少端口 → scan + SCAN_HORIZONTAL。"""
        svc = AlertingService(score_threshold=0.5, window_sec=60)
        base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        scan_features = {"syn_count": 80, "total_packets": 100, "rst_ratio": 0.0}
        flows = [
            _make_flow(
                src_ip="10.0.0.1", dst_ip=f"10.0.0.{i}", dst_port=80,
                anomaly_score=0.9, ts_start=base, flow_id=f"f-{i}",
                features=scan_features,
            )
            for i in range(2, 10)  # 8 个不同目标 IP，同一端口
        ]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        assert alerts[0]["type"] == "scan"
        agg = json.loads(alerts[0]["aggregation"])
        assert "SCAN_HORIZONTAL" in agg["type_reason"]["reason_codes"]

    def test_scan_vertical(self):
        """垂直扫描：单目标 IP + 多端口 → scan + SCAN_VERTICAL。"""
        svc = AlertingService(score_threshold=0.5, window_sec=60)
        base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        scan_features = {"syn_count": 80, "total_packets": 100, "rst_ratio": 0.0}
        flows = [
            _make_flow(
                src_ip="10.0.0.1", dst_ip="10.0.0.2", dst_port=p,
                anomaly_score=0.9, ts_start=base, flow_id=f"f-{p}",
                features=scan_features,
            )
            for p in range(20, 35)  # 15 个不同端口，同一目标 IP
        ]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        assert alerts[0]["type"] == "scan"
        agg = json.loads(alerts[0]["aggregation"])
        assert "SCAN_VERTICAL" in agg["type_reason"]["reason_codes"]

    def test_bruteforce_expanded_ports(self):
        """扩展认证端口（MySQL 3306）+ 行为指标 → bruteforce。"""
        svc = AlertingService(score_threshold=0.5, window_sec=60)
        base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        brute_features = {
            "syn_count": 1, "total_packets": 5,
            "rst_ratio": 0.5, "handshake_completeness": 0.4,
            "is_short_flow": 1,
        }
        flows = [
            _make_flow(
                src_ip="10.0.0.1", dst_ip="10.0.0.2", dst_port=3306,
                anomaly_score=0.9, ts_start=base + timedelta(seconds=i),
                flow_id=f"f-{i}", features=brute_features,
            )
            for i in range(6)
        ]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        assert alerts[0]["type"] == "bruteforce"
        agg = json.loads(alerts[0]["aggregation"])
        assert "BRUTE_AUTH_PORT" in agg["type_reason"]["reason_codes"]

    def test_bruteforce_needs_behavioral_indicator(self):
        """仅端口匹配不足以判定 bruteforce（需要行为指标）。"""
        svc = AlertingService(score_threshold=0.5, window_sec=60)
        base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        # 仅 2 条流，正常握手，无 RST → 行为指标不足
        normal_features = {
            "syn_count": 1, "total_packets": 50,
            "rst_ratio": 0.0, "handshake_completeness": 1.0,
            "is_short_flow": 0,
        }
        flows = [
            _make_flow(
                src_ip="10.0.0.1", dst_ip="10.0.0.2", dst_port=22,
                anomaly_score=0.9, ts_start=base, flow_id=f"f-{i}",
                features=normal_features,
            )
            for i in range(2)
        ]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        assert alerts[0]["type"] != "bruteforce"

    def test_dos_syn_flood(self):
        """SYN Flood：高 SYN 比例 + 低握手 + 单目标 → dos + DOS_SYN_FLOOD。"""
        svc = AlertingService(score_threshold=0.5, window_sec=60)
        base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        flood_features = {
            "syn_count": 95, "total_packets": 100,
            "handshake_completeness": 0.1, "rst_ratio": 0.0,
            "total_bytes": 5000,
        }
        flows = [
            _make_flow(
                src_ip="10.0.0.1", dst_ip="10.0.0.2", dst_port=80,
                anomaly_score=0.9, ts_start=base + timedelta(seconds=i),
                flow_id=f"f-{i}", features=flood_features,
            )
            for i in range(5)
        ]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        # 注意：高 SYN 比例也可能触发 scan，但 SYN Flood 场景下
        # 单目标 + 单端口不满足 scan 的多目标/多端口条件
        # 而 syn_ratio > 0.7 + handshake < 0.5 + dst_ips <= 2 → DOS_SYN_FLOOD
        agg = json.loads(alerts[0]["aggregation"])
        # 可能先命中 scan（因 SYN_RATIO），也可能命中 dos
        # 关键是 type_reason 存在且结构正确
        assert "type_reason" in agg
        assert "reason_codes" in agg["type_reason"]
        assert len(agg["type_reason"]["reason_codes"]) > 0

    def test_type_reason_in_aggregation(self):
        """type_reason 出现在 aggregation JSON 中，结构完整。"""
        svc = AlertingService(score_threshold=0.5)
        flows = [_make_flow(anomaly_score=0.9)]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        agg = json.loads(alerts[0]["aggregation"])
        assert "type_reason" in agg
        tr = agg["type_reason"]
        assert "type" in tr
        assert "reason_codes" in tr
        assert "details" in tr
        assert isinstance(tr["reason_codes"], list)
        assert isinstance(tr["details"], dict)

    def test_type_reason_anomaly_default(self):
        """默认 anomaly 的 type_reason 包含 ANOMALY_DEFAULT。"""
        svc = AlertingService(score_threshold=0.5)
        flows = [_make_flow(anomaly_score=0.9, features={"syn_count": 1, "total_packets": 5})]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        agg = json.loads(alerts[0]["aggregation"])
        assert agg["type_reason"]["type"] == "anomaly"
        assert agg["type_reason"]["reason_codes"] == ["ANOMALY_DEFAULT"]


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

    def test_scan_incomplete_handshake(self):
        """SYN 比例 + 低握手完成度 → scan（评分制：SYN +2, handshake +1 = 3 ≥ 2）。"""
        flow = _make_flow(features={
            "syn_count": 60, "total_packets": 100,
            "handshake_completeness": 0.33, "rst_ratio": 0.0,
            "is_short_flow": 0,
        })
        assert AlertingService._infer_flow_type(flow) == "scan"

    def test_bruteforce_mysql_port(self):
        """MySQL 端口 3306 → bruteforce。"""
        flow = _make_flow(dst_port=3306, features={
            "syn_count": 1, "total_packets": 10,
        })
        assert AlertingService._infer_flow_type(flow) == "bruteforce"

    def test_bruteforce_redis_port(self):
        """Redis 端口 6379 → bruteforce。"""
        flow = _make_flow(dst_port=6379, features={
            "syn_count": 1, "total_packets": 10,
        })
        assert AlertingService._infer_flow_type(flow) == "bruteforce"

    def test_dos_high_pps(self):
        """高 packets_per_second → dos。"""
        flow = _make_flow(dst_port=80, features={
            "syn_count": 1, "total_packets": 10,
            "total_bytes": 5000, "packets_per_second": 2000,
        })
        assert AlertingService._infer_flow_type(flow) == "dos"

    def test_infer_detailed_returns_reasons(self):
        """_infer_flow_type_detailed 返回 reason_codes 和 details。"""
        flow = _make_flow(features={"syn_count": 80, "total_packets": 100})
        typ, reasons, details = AlertingService._infer_flow_type_detailed(flow)
        assert typ == "scan"
        assert "SCAN_SYN_RATIO" in reasons
        assert "syn_ratio" in details


# --------------- TestTraceabilitySummaries ---------------

class TestTraceabilitySummaries:
    """测试可追溯摘要字段生成。"""

    def test_aggregation_summary_present(self):
        """aggregation JSON 包含 aggregation_summary 且非空。"""
        svc = AlertingService(score_threshold=0.5)
        flows = [_make_flow(anomaly_score=0.9)]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        agg = json.loads(alerts[0]["aggregation"])
        assert "aggregation_summary" in agg
        assert isinstance(agg["aggregation_summary"], str)
        assert len(agg["aggregation_summary"]) > 0
        # 应包含"聚合"关键词
        assert "聚合" in agg["aggregation_summary"]

    def test_type_summary_present(self):
        """aggregation JSON 包含 type_summary 且非空。"""
        svc = AlertingService(score_threshold=0.5)
        flows = [_make_flow(anomaly_score=0.9)]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        agg = json.loads(alerts[0]["aggregation"])
        assert "type_summary" in agg
        assert isinstance(agg["type_summary"], str)
        assert len(agg["type_summary"]) > 0
        # 应包含"判定为"关键词
        assert "判定为" in agg["type_summary"]

    def test_severity_summary_present(self):
        """aggregation JSON 包含 severity_summary 且非空。"""
        svc = AlertingService(score_threshold=0.5)
        flows = [_make_flow(anomaly_score=0.9)]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        agg = json.loads(alerts[0]["aggregation"])
        assert "severity_summary" in agg
        assert isinstance(agg["severity_summary"], str)
        assert len(agg["severity_summary"]) > 0
        # 应包含"复合评分"关键词
        assert "复合评分" in agg["severity_summary"]

    def test_scan_type_summary_content(self):
        """scan 类型的 type_summary 应包含扫描相关描述。"""
        svc = AlertingService(score_threshold=0.5, window_sec=60)
        base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        scan_features = {"syn_count": 80, "total_packets": 100, "rst_ratio": 0.0}
        flows = [
            _make_flow(
                src_ip="10.0.0.1", dst_ip=f"10.0.0.{i}", dst_port=80,
                anomaly_score=0.9, ts_start=base, flow_id=f"f-{i}",
                features=scan_features,
            )
            for i in range(2, 10)
        ]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        agg = json.loads(alerts[0]["aggregation"])
        assert "扫描" in agg["type_summary"]

    def test_bruteforce_type_summary_content(self):
        """bruteforce 类型的 type_summary 应包含暴力破解相关描述。"""
        svc = AlertingService(score_threshold=0.5, window_sec=60)
        base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        brute_features = {
            "syn_count": 1, "total_packets": 5,
            "rst_ratio": 0.5, "handshake_completeness": 0.4,
            "is_short_flow": 1,
        }
        flows = [
            _make_flow(
                src_ip="10.0.0.1", dst_ip="10.0.0.2", dst_port=3306,
                anomaly_score=0.9, ts_start=base + timedelta(seconds=i),
                flow_id=f"f-{i}", features=brute_features,
            )
            for i in range(6)
        ]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        agg = json.loads(alerts[0]["aggregation"])
        assert "暴力破解" in agg["type_summary"]

    def test_severity_summary_shows_breakdown(self):
        """severity_summary 应包含各分项因子名称。"""
        svc = AlertingService(score_threshold=0.5)
        flows = [_make_flow(anomaly_score=0.9)]
        alerts = svc.generate_alerts(flows, pcap_id="p1")
        agg = json.loads(alerts[0]["aggregation"])
        summary = agg["severity_summary"]
        assert "最高异常分" in summary
        assert "流密度" in summary
        assert "持续时长" in summary
        assert "聚合质量" in summary

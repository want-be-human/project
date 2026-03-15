"""
Unit tests for TopologyService.
Covers DOC B B4.6 & DOC F Week-5/6 DoD:
  - build_graph 返回 nodes / edges / activeIntervals
  - ip 模式与 subnet 模式
  - edge.alert_ids 关联
  - Week 6: _merge_intervals, interval clamping, risk capping, dst_node risk
"""

import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from app.services.topology.service import TopologyService
from app.schemas.topology import GraphResponseSchema, GraphNode, GraphMeta


# ── helpers ──────────────────────────────────────────────────────

def _ts(offset_sec: int = 0) -> datetime:
    base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    return base + timedelta(seconds=offset_sec)


def _make_flow_model(
    *,
    id: str = "flow-1",
    src_ip: str = "192.168.1.10",
    dst_ip: str = "10.0.0.1",
    src_port: int = 54321,
    dst_port: int = 80,
    proto: str = "TCP",
    ts_start: datetime | None = None,
    ts_end: datetime | None = None,
    anomaly_score: float | None = None,
) -> MagicMock:
    """Create a mock Flow ORM object."""
    m = MagicMock()
    m.id = id
    m.src_ip = src_ip
    m.dst_ip = dst_ip
    m.src_port = src_port
    m.dst_port = dst_port
    m.proto = proto
    m.ts_start = ts_start or _ts(0)
    m.ts_end = ts_end or _ts(5)
    m.anomaly_score = anomaly_score
    return m


def _make_alert_model(
    *,
    id: str = "alert-1",
    evidence_flow_ids: list[str] | None = None,
    time_window_start: datetime | None = None,
    time_window_end: datetime | None = None,
) -> MagicMock:
    """Create a mock Alert ORM object."""
    m = MagicMock()
    m.id = id
    m.time_window_start = time_window_start or _ts(0)
    m.time_window_end = time_window_end or _ts(60)
    m.evidence = json.dumps({
        "flow_ids": evidence_flow_ids or [],
    })
    return m


def _setup_db(flows, alerts):
    """Build a mock DB session that returns flows and alerts."""
    db = MagicMock()

    def fake_query(model):
        q = MagicMock()

        def fake_filter(*args):
            # Return the right dataset based on what was queried
            q2 = MagicMock()
            q2.all.return_value = flows if model.__name__ == "Flow" else alerts
            q2.filter.return_value = q2  # chaining
            return q2

        q.filter = fake_filter
        return q

    db.query = fake_query
    return db


# ── TestBuildGraph ───────────────────────────────────────────────

class TestBuildGraph:
    """Tests for TopologyService.build_graph."""

    def test_empty_flows_returns_empty_graph(self):
        """No flows → empty graph with correct meta."""
        db = _setup_db([], [])
        svc = TopologyService(db)
        g = svc.build_graph(_ts(0), _ts(3600), mode="ip")

        assert isinstance(g, GraphResponseSchema)
        assert g.nodes == []
        assert g.edges == []
        assert g.meta.mode == "ip"

    def test_single_flow_creates_two_nodes_one_edge(self):
        """One flow → 2 nodes (src + dst) + 1 edge."""
        flow = _make_flow_model(src_ip="1.2.3.4", dst_ip="5.6.7.8", proto="TCP", dst_port=443)
        db = _setup_db([flow], [])
        svc = TopologyService(db)
        g = svc.build_graph(_ts(0), _ts(3600))

        assert len(g.nodes) == 2
        assert len(g.edges) == 1

        node_ids = {n.id for n in g.nodes}
        assert "ip:1.2.3.4" in node_ids
        assert "ip:5.6.7.8" in node_ids

        edge = g.edges[0]
        assert edge.source == "ip:1.2.3.4"
        assert edge.target == "ip:5.6.7.8"
        assert edge.proto == "TCP"
        assert edge.dst_port == 443
        assert edge.weight == 1

    def test_active_intervals_iso8601(self):
        """Edge activeIntervals are 2D arrays of ISO8601 strings."""
        flow = _make_flow_model(ts_start=_ts(0), ts_end=_ts(10))
        db = _setup_db([flow], [])
        svc = TopologyService(db)
        g = svc.build_graph(_ts(0), _ts(3600))

        assert len(g.edges) == 1
        intervals = g.edges[0].activeIntervals
        assert len(intervals) == 1
        assert isinstance(intervals[0], list)
        assert len(intervals[0]) == 2
        # Verify ISO format
        assert intervals[0][0].endswith("Z")
        assert intervals[0][1].endswith("Z")

    def test_multiple_flows_same_edge_accumulates(self):
        """Multiple flows on the same 5-tuple merge into one edge with weight=N."""
        flows = [
            _make_flow_model(id="f1", src_ip="10.0.0.1", dst_ip="10.0.0.2",
                             proto="TCP", dst_port=80, ts_start=_ts(0), ts_end=_ts(5)),
            _make_flow_model(id="f2", src_ip="10.0.0.1", dst_ip="10.0.0.2",
                             proto="TCP", dst_port=80, ts_start=_ts(10), ts_end=_ts(15)),
        ]
        db = _setup_db(flows, [])
        svc = TopologyService(db)
        g = svc.build_graph(_ts(0), _ts(3600))

        assert len(g.nodes) == 2
        assert len(g.edges) == 1
        assert g.edges[0].weight == 2
        assert len(g.edges[0].activeIntervals) == 2

    def test_anomaly_score_propagated_to_risk(self):
        """Edge and node risk values reflect max anomaly_score."""
        flow = _make_flow_model(anomaly_score=0.87)
        db = _setup_db([flow], [])
        svc = TopologyService(db)
        g = svc.build_graph(_ts(0), _ts(3600))

        assert g.edges[0].risk == 0.87
        src_node = [n for n in g.nodes if n.id.startswith("ip:192")][0]
        assert src_node.risk == 0.87

    def test_alert_ids_on_edge(self):
        """Edges referencing alerted flows carry alert_ids."""
        flow = _make_flow_model(id="f1", anomaly_score=0.9)
        alert = _make_alert_model(id="alert-x", evidence_flow_ids=["f1"])
        db = _setup_db([flow], [alert])
        svc = TopologyService(db)
        g = svc.build_graph(_ts(0), _ts(3600))

        assert "alert-x" in g.edges[0].alert_ids

    def test_subnet_mode_groups_ips(self):
        """mode='subnet' collapses IPs into /24 subnets."""
        flows = [
            _make_flow_model(id="f1", src_ip="10.0.1.5", dst_ip="172.16.0.10"),
            _make_flow_model(id="f2", src_ip="10.0.1.99", dst_ip="172.16.0.200",
                             proto="TCP", dst_port=80),
        ]
        db = _setup_db(flows, [])
        svc = TopologyService(db)
        g = svc.build_graph(_ts(0), _ts(3600), mode="subnet")

        node_ids = {n.id for n in g.nodes}
        assert "subnet:10.0.1.0/24" in node_ids
        assert "subnet:172.16.0.0/24" in node_ids
        # All nodes are subnet type
        for n in g.nodes:
            assert n.type == "subnet"

    def test_version_is_1_1(self):
        """Graph version must be '1.1'."""
        db = _setup_db([], [])
        svc = TopologyService(db)
        g = svc.build_graph(_ts(0), _ts(3600))
        assert g.version == "1.1"


# ── TestComputeGraphHash ─────────────────────────────────────────

class TestComputeGraphHash:
    """Tests for TopologyService.compute_graph_hash."""

    def test_same_graph_same_hash(self):
        """Identical graphs produce identical hashes."""
        db = MagicMock()
        svc = TopologyService(db)

        graph = GraphResponseSchema(
            version="1.1",
            nodes=[GraphNode(id="ip:1.2.3.4", label="1.2.3.4", type="host", risk=0.0)],
            edges=[],
            meta=GraphMeta(start="2026-01-01T00:00:00Z", end="2026-01-02T00:00:00Z", mode="ip"),
        )

        h1 = svc.compute_graph_hash(graph)
        h2 = svc.compute_graph_hash(graph)
        assert h1 == h2
        assert h1.startswith("sha256:")

    def test_different_graphs_different_hash(self):
        """Adding a node changes the hash."""
        db = MagicMock()
        svc = TopologyService(db)

        g1 = GraphResponseSchema(
            version="1.1",
            nodes=[GraphNode(id="ip:1.2.3.4", label="1.2.3.4", type="host", risk=0.0)],
            edges=[],
            meta=GraphMeta(start="t", end="t", mode="ip"),
        )
        g2 = GraphResponseSchema(
            version="1.1",
            nodes=[
                GraphNode(id="ip:1.2.3.4", label="1.2.3.4", type="host", risk=0.0),
                GraphNode(id="ip:5.6.7.8", label="5.6.7.8", type="host", risk=0.0),
            ],
            edges=[],
            meta=GraphMeta(start="t", end="t", mode="ip"),
        )

        assert svc.compute_graph_hash(g1) != svc.compute_graph_hash(g2)


# ── Week 6: TestMergeIntervals ───────────────────────────────────

class TestMergeIntervals:
    """Tests for TopologyService._merge_intervals (Week 6)."""

    def test_empty(self):
        """Empty input → empty output."""
        assert TopologyService._merge_intervals([]) == []

    def test_single_interval(self):
        """Single interval returned as-is."""
        iv = [["2026-01-15T12:00:00Z", "2026-01-15T12:00:05Z"]]
        assert TopologyService._merge_intervals(iv) == iv

    def test_non_overlapping_sorted(self):
        """Disjoint intervals are sorted by start but not merged."""
        ivs = [
            ["2026-01-15T12:00:10Z", "2026-01-15T12:00:15Z"],
            ["2026-01-15T12:00:00Z", "2026-01-15T12:00:05Z"],
        ]
        result = TopologyService._merge_intervals(ivs)
        assert len(result) == 2
        assert result[0][0] == "2026-01-15T12:00:00Z"
        assert result[1][0] == "2026-01-15T12:00:10Z"

    def test_overlapping_merged(self):
        """Overlapping intervals are merged into one."""
        ivs = [
            ["2026-01-15T12:00:00Z", "2026-01-15T12:00:10Z"],
            ["2026-01-15T12:00:05Z", "2026-01-15T12:00:15Z"],
        ]
        result = TopologyService._merge_intervals(ivs)
        assert len(result) == 1
        assert result[0] == ["2026-01-15T12:00:00Z", "2026-01-15T12:00:15Z"]

    def test_adjacent_merged(self):
        """Adjacent (touching) intervals are merged."""
        ivs = [
            ["2026-01-15T12:00:00Z", "2026-01-15T12:00:05Z"],
            ["2026-01-15T12:00:05Z", "2026-01-15T12:00:10Z"],
        ]
        result = TopologyService._merge_intervals(ivs)
        assert len(result) == 1
        assert result[0] == ["2026-01-15T12:00:00Z", "2026-01-15T12:00:10Z"]

    def test_complex_mix(self):
        """Mix: 3 input intervals → 2 merged groups."""
        ivs = [
            ["2026-01-15T12:00:20Z", "2026-01-15T12:00:30Z"],  # group 2
            ["2026-01-15T12:00:00Z", "2026-01-15T12:00:08Z"],  # group 1 start
            ["2026-01-15T12:00:05Z", "2026-01-15T12:00:12Z"],  # group 1 extends
        ]
        result = TopologyService._merge_intervals(ivs)
        assert len(result) == 2
        assert result[0] == ["2026-01-15T12:00:00Z", "2026-01-15T12:00:12Z"]
        assert result[1] == ["2026-01-15T12:00:20Z", "2026-01-15T12:00:30Z"]

    def test_contained_interval(self):
        """Interval fully inside another is absorbed."""
        ivs = [
            ["2026-01-15T12:00:00Z", "2026-01-15T12:00:20Z"],
            ["2026-01-15T12:00:05Z", "2026-01-15T12:00:10Z"],
        ]
        result = TopologyService._merge_intervals(ivs)
        assert len(result) == 1
        assert result[0] == ["2026-01-15T12:00:00Z", "2026-01-15T12:00:20Z"]


# ── Week 6: TestIntervalClamping ─────────────────────────────────

class TestIntervalClamping:
    """Flow intervals are clamped to the query window (Week 6)."""

    def test_flow_wider_than_window(self):
        """Flow spanning beyond the window gets clamped on both sides."""
        flow = _make_flow_model(
            ts_start=_ts(-100),
            ts_end=_ts(200),
        )
        window_start = _ts(0)
        window_end = _ts(100)
        db = _setup_db([flow], [])
        svc = TopologyService(db)
        g = svc.build_graph(window_start, window_end)

        interval = g.edges[0].activeIntervals[0]
        # Start should be clamped to window start, end to window end
        from app.core.utils import datetime_to_iso
        assert interval[0] == datetime_to_iso(window_start)
        assert interval[1] == datetime_to_iso(window_end)

    def test_flow_within_window_unclamped(self):
        """Flow fully inside window: interval equals flow's own times."""
        flow = _make_flow_model(ts_start=_ts(10), ts_end=_ts(50))
        db = _setup_db([flow], [])
        svc = TopologyService(db)
        g = svc.build_graph(_ts(0), _ts(3600))

        from app.core.utils import datetime_to_iso
        interval = g.edges[0].activeIntervals[0]
        assert interval[0] == datetime_to_iso(_ts(10))
        assert interval[1] == datetime_to_iso(_ts(50))


# ── Week 6: TestRiskBehavior ─────────────────────────────────────

class TestRiskBehavior:
    """Risk capping and dst-node risk propagation (Week 6)."""

    def test_risk_capped_at_1(self):
        """Edge risk capped to 1.0 even if anomaly_score > 1."""
        flow = _make_flow_model(anomaly_score=1.5)
        db = _setup_db([flow], [])
        svc = TopologyService(db)
        g = svc.build_graph(_ts(0), _ts(3600))

        assert g.edges[0].risk <= 1.0

    def test_dst_node_risk_is_half(self):
        """Destination node risk = anomaly_score * 0.5."""
        flow = _make_flow_model(
            src_ip="10.0.0.1", dst_ip="10.0.0.2", anomaly_score=0.8
        )
        db = _setup_db([flow], [])
        svc = TopologyService(db)
        g = svc.build_graph(_ts(0), _ts(3600))

        src = [n for n in g.nodes if n.id == "ip:10.0.0.1"][0]
        dst = [n for n in g.nodes if n.id == "ip:10.0.0.2"][0]
        assert src.risk == 0.8
        assert dst.risk == pytest.approx(0.4, abs=0.01)

    def test_alert_ids_sorted(self):
        """Alert IDs on edges are returned in sorted order."""
        flow = _make_flow_model(id="f1", anomaly_score=0.9)
        alerts = [
            _make_alert_model(id="z-alert", evidence_flow_ids=["f1"]),
            _make_alert_model(id="a-alert", evidence_flow_ids=["f1"]),
        ]
        db = _setup_db([flow], alerts)
        svc = TopologyService(db)
        g = svc.build_graph(_ts(0), _ts(3600))

        assert g.edges[0].alert_ids == ["a-alert", "z-alert"]

    def test_node_type_is_host_in_ip_mode(self):
        """IP mode produces type='host' nodes, not 'gateway'."""
        flow = _make_flow_model()
        db = _setup_db([flow], [])
        svc = TopologyService(db)
        g = svc.build_graph(_ts(0), _ts(3600), mode="ip")

        for n in g.nodes:
            assert n.type == "host"

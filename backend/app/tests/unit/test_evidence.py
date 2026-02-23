"""
Unit tests for EvidenceService.
Covers DOC B B4.8 & DOC F Week-5 DoD:
  - evidence chain 至少包含 alert + flow + feature 节点
  - 边类型：supports / explains
  - fallback feature extraction from DB flows
"""

import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

from app.services.evidence.service import EvidenceService
from app.schemas.evidence import EvidenceChainSchema, EvidenceNode, EvidenceEdge


# ── helpers ──────────────────────────────────────────────────────

def _ts(offset_sec: int = 0) -> datetime:
    base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    return base + timedelta(seconds=offset_sec)


def _make_alert(
    *,
    id: str = "alert-1",
    alert_type: str = "scan",
    severity: str = "high",
    top_flows: list[dict] | None = None,
    top_features: list[dict] | None = None,
    flow_ids: list[str] | None = None,
    investigation_id: str | None = None,
    recommendation_id: str | None = None,
    dry_run_id: str | None = None,
) -> MagicMock:
    """Create a mock Alert ORM object."""
    if top_flows is None:
        top_flows = [
            {"flow_id": "flow-1", "summary": "192.168.1.10:54321→10.0.0.1:80/TCP", "anomaly_score": 0.92},
        ]
    if flow_ids is None:
        flow_ids = [tf["flow_id"] for tf in top_flows]

    evidence = {
        "flow_ids": flow_ids,
        "top_flows": top_flows,
        "top_features": top_features or [],
        "pcap_ref": {"pcap_id": "pcap-1", "offset_hint": None},
    }
    agent = {
        "triage_summary": None,
        "investigation_id": investigation_id,
        "recommendation_id": recommendation_id,
    }
    twin = {
        "dry_run_id": dry_run_id,
    }

    m = MagicMock()
    m.id = id
    m.type = alert_type
    m.severity = severity
    m.evidence = json.dumps(evidence)
    m.agent = json.dumps(agent)
    m.twin = json.dumps(twin)
    return m


def _make_flow_orm(
    *,
    id: str = "flow-1",
    features: dict | None = None,
) -> MagicMock:
    """Create a mock Flow ORM object for DB queries."""
    m = MagicMock()
    m.id = id
    m.features = json.dumps(features or {
        "total_packets": 50,
        "total_bytes": 4200,
        "bytes_per_packet": 84.0,
        "flow_duration_ms": 120.0,
        "syn_count": 3,
        "rst_ratio": 0.0,
    })
    return m


def _mock_db(flow_orms=None):
    """Return a mock db session.  Handles query/filter/in_ chains + add/commit/delete."""
    db = MagicMock()

    # For the feature-fallback path: db.query(Flow).filter(Flow.id.in_(...)).all()
    filter_mock = MagicMock()
    filter_mock.all.return_value = flow_orms or []
    query_mock = MagicMock()
    query_mock.filter.return_value = filter_mock

    # For the cache-evict path: db.query(EvidenceChain).filter(...).delete()
    ec_query = MagicMock()
    ec_filter = MagicMock()
    ec_filter.delete.return_value = 0
    ec_query.filter.return_value = ec_filter

    def fake_query(model):
        name = getattr(model, "__name__", "") or getattr(model, "__tablename__", "")
        if "Flow" in str(name):
            return query_mock
        return ec_query  # EvidenceChain

    db.query = fake_query
    return db


# ── TestBuildEvidenceChain ───────────────────────────────────────

class TestBuildEvidenceChain:
    """Tests for EvidenceService.build_evidence_chain."""

    def test_alert_node_present(self):
        """Chain always has an alert node."""
        alert = _make_alert()
        db = _mock_db()
        svc = EvidenceService(db)
        chain = svc.build_evidence_chain(alert)

        alert_nodes = [n for n in chain.nodes if n.type == "alert"]
        assert len(alert_nodes) == 1
        assert alert_nodes[0].id == f"alert:{alert.id}"

    def test_flow_nodes_present(self):
        """Chain has flow nodes from top_flows."""
        alert = _make_alert(top_flows=[
            {"flow_id": "f1", "summary": "src→dst:80/TCP", "anomaly_score": 0.9},
            {"flow_id": "f2", "summary": "src→dst:443/TCP", "anomaly_score": 0.8},
        ])
        db = _mock_db()
        svc = EvidenceService(db)
        chain = svc.build_evidence_chain(alert)

        flow_nodes = [n for n in chain.nodes if n.type == "flow"]
        assert len(flow_nodes) == 2

    def test_supports_edges(self):
        """Flow→alert edges use type='supports'."""
        alert = _make_alert()
        db = _mock_db()
        svc = EvidenceService(db)
        chain = svc.build_evidence_chain(alert)

        supports = [e for e in chain.edges if e.type == "supports"]
        assert len(supports) >= 1
        for edge in supports:
            assert edge.target.startswith("alert:")

    def test_feature_nodes_from_top_features(self):
        """When top_features exist, feature nodes are created."""
        alert = _make_alert(top_features=[
            {"name": "syn_count", "value": 42, "direction": "high"},
            {"name": "rst_ratio", "value": 0.5, "direction": "high"},
        ])
        db = _mock_db()
        svc = EvidenceService(db)
        chain = svc.build_evidence_chain(alert)

        feat_nodes = [n for n in chain.nodes if n.type == "feature"]
        assert len(feat_nodes) == 2
        assert any("syn_count" in n.label for n in feat_nodes)

    def test_explains_edges(self):
        """Feature→flow edges use type='explains'."""
        alert = _make_alert(top_features=[
            {"name": "syn_count", "value": 42, "direction": "high"},
        ])
        db = _mock_db()
        svc = EvidenceService(db)
        chain = svc.build_evidence_chain(alert)

        explains = [e for e in chain.edges if e.type == "explains"]
        assert len(explains) >= 1
        for edge in explains:
            assert edge.source.startswith("feat:")

    def test_feature_fallback_from_db_flows(self):
        """When top_features is empty, features are extracted from DB Flow records."""
        alert = _make_alert(
            top_features=[],
            flow_ids=["flow-1", "flow-2"],
        )
        flow_orms = [
            _make_flow_orm(id="flow-1", features={
                "total_packets": 50,
                "bytes_per_packet": 84.0,
                "syn_count": 3,
            }),
            _make_flow_orm(id="flow-2", features={
                "total_packets": 120,
                "bytes_per_packet": 60.0,
                "syn_count": 1,
            }),
        ]
        db = _mock_db(flow_orms=flow_orms)
        svc = EvidenceService(db)
        chain = svc.build_evidence_chain(alert)

        feat_nodes = [n for n in chain.nodes if n.type == "feature"]
        # Fallback should produce at least 1 feature node
        assert len(feat_nodes) >= 1

    def test_minimum_node_types_alert_flow_feature(self):
        """DOC F: chain 至少包含 alert + flow + feature."""
        alert = _make_alert(
            top_features=[],
            flow_ids=["flow-1"],
            top_flows=[
                {"flow_id": "flow-1", "summary": "s→d:80/TCP", "anomaly_score": 0.9},
            ],
        )
        flow_orms = [
            _make_flow_orm(id="flow-1", features={
                "total_bytes": 5000,
                "bytes_per_packet": 100.0,
                "flow_duration_ms": 200.0,
            }),
        ]
        db = _mock_db(flow_orms=flow_orms)
        svc = EvidenceService(db)
        chain = svc.build_evidence_chain(alert)

        types = {n.type for n in chain.nodes}
        assert "alert" in types
        assert "flow" in types
        assert "feature" in types

    def test_version_is_1_1(self):
        """Chain version must be '1.1'."""
        alert = _make_alert()
        db = _mock_db()
        svc = EvidenceService(db)
        chain = svc.build_evidence_chain(alert)
        assert chain.version == "1.1"

    def test_chain_has_alert_id(self):
        """Chain carries the parent alert_id."""
        alert = _make_alert(id="alert-abc")
        db = _mock_db()
        svc = EvidenceService(db)
        chain = svc.build_evidence_chain(alert)
        assert chain.alert_id == "alert-abc"

    def test_no_flows_no_crash(self):
        """Alert with no flows produces just alert node (no crash)."""
        alert = _make_alert(top_flows=[], flow_ids=[])
        db = _mock_db()
        svc = EvidenceService(db)
        chain = svc.build_evidence_chain(alert)
        assert any(n.type == "alert" for n in chain.nodes)

    def test_max_5_flow_nodes(self):
        """Top flows are capped at 5."""
        flows = [
            {"flow_id": f"f{i}", "summary": f"flow-{i}", "anomaly_score": 0.8}
            for i in range(10)
        ]
        alert = _make_alert(top_flows=flows)
        db = _mock_db()
        svc = EvidenceService(db)
        chain = svc.build_evidence_chain(alert)

        flow_nodes = [n for n in chain.nodes if n.type == "flow"]
        assert len(flow_nodes) == 5

    def test_max_5_feature_nodes(self):
        """Top features are capped at 5."""
        feats = [
            {"name": f"feat_{i}", "value": float(i), "direction": "high"}
            for i in range(10)
        ]
        alert = _make_alert(top_features=feats)
        db = _mock_db()
        svc = EvidenceService(db)
        chain = svc.build_evidence_chain(alert)

        feat_nodes = [n for n in chain.nodes if n.type == "feature"]
        assert len(feat_nodes) == 5


# ── TestExtractFeaturesFromFlows ─────────────────────────────────

class TestExtractFeaturesFromFlows:
    """Tests for EvidenceService._extract_features_from_flows."""

    def test_empty_flow_ids_returns_empty(self):
        db = _mock_db()
        svc = EvidenceService(db)
        result = svc._extract_features_from_flows([])
        assert result == []

    def test_returns_top_3_by_value(self):
        """Picks top-3 features sorted by absolute value."""
        flow_orms = [
            _make_flow_orm(id="f1", features={
                "total_bytes": 99999,
                "total_packets": 500,
                "bytes_per_packet": 200.0,
                "syn_count": 2,
                "rst_ratio": 0.01,
            }),
        ]
        db = _mock_db(flow_orms=flow_orms)
        svc = EvidenceService(db)
        result = svc._extract_features_from_flows(["f1"])

        assert len(result) == 3
        names = [r["name"] for r in result]
        # total_bytes (99999) > total_packets (500) > bytes_per_packet (200)
        assert names[0] == "total_bytes"
        assert names[1] == "total_packets"
        assert names[2] == "bytes_per_packet"

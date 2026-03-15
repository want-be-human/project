"""
Integration tests for threat enrichment in AgentService.
Validates that investigation and recommendation outputs correctly
include / omit threat_context based on the feature flag,
and that the schema remains backward-compatible.
"""

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.base import Base
from app.models.alert import Alert
from app.schemas.agent import InvestigationSchema, RecommendationSchema
from app.services.agent.service import AgentService


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def db():
    """Create a disposable in-memory SQLite database for each test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    engine.dispose()


def _make_alert(db: Session, alert_type: str = "scan") -> Alert:
    """Insert a minimal Alert and return it."""
    now = datetime.now(timezone.utc)
    alert = Alert(
        id="test-alert-001",
        severity="high",
        status="new",
        type=alert_type,
        time_window_start=now,
        time_window_end=now,
        primary_src_ip="192.168.1.100",
        primary_dst_ip="10.0.0.1",
        primary_proto="tcp",
        primary_dst_port=22,
        evidence=json.dumps({
            "flow_ids": ["f1", "f2"],
            "top_flows": [],
            "top_features": [
                {"name": "syn_ratio", "value": 0.85, "direction": "high"},
                {"name": "total_packets", "value": 200, "direction": "high"},
            ],
        }),
        aggregation=json.dumps({
            "rule": "src_ip+window",
            "group_key": "192.168.1.100|window",
            "count_flows": 15,
        }),
        agent=json.dumps({}),
        twin=json.dumps({}),
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


# ── Tests: investigation with enrichment ─────────────────────────────────


class TestInvestigateWithEnrichment:
    def test_investigate_has_threat_context(self, db):
        alert = _make_alert(db, "scan")
        with patch("app.services.agent.service.settings") as mock_settings:
            mock_settings.THREAT_ENRICHMENT_ENABLED = True
            svc = AgentService(db)
            result = svc.investigate(alert, language="en")

        assert isinstance(result, InvestigationSchema)
        assert result.threat_context is not None
        assert len(result.threat_context.techniques) > 0
        assert "T1595" in {t.technique_id for t in result.threat_context.techniques}
        # Hypothesis should mention MITRE
        assert "MITRE" in result.hypothesis or "T1595" in result.hypothesis

    def test_investigate_enriched_why_includes_mitre(self, db):
        alert = _make_alert(db, "bruteforce")
        with patch("app.services.agent.service.settings") as mock_settings:
            mock_settings.THREAT_ENRICHMENT_ENABLED = True
            svc = AgentService(db)
            result = svc.investigate(alert, language="en")

        why_joined = " ".join(result.why)
        assert "MITRE" in why_joined

    def test_investigate_without_enrichment_flag(self, db):
        alert = _make_alert(db, "scan")
        with patch("app.services.agent.service.settings") as mock_settings:
            mock_settings.THREAT_ENRICHMENT_ENABLED = False
            svc = AgentService(db)
            result = svc.investigate(alert, language="en")

        assert isinstance(result, InvestigationSchema)
        assert result.threat_context is None
        # Hypothesis should NOT mention MITRE
        assert "MITRE" not in result.hypothesis

    def test_investigate_chinese_with_enrichment(self, db):
        alert = _make_alert(db, "dos")
        with patch("app.services.agent.service.settings") as mock_settings:
            mock_settings.THREAT_ENRICHMENT_ENABLED = True
            svc = AgentService(db)
            result = svc.investigate(alert, language="zh")

        assert result.threat_context is not None
        assert "MITRE" in result.hypothesis or "T1498" in result.hypothesis


# ── Tests: recommendation with enrichment ────────────────────────────────


class TestRecommendWithEnrichment:
    def test_recommend_has_threat_context(self, db):
        alert = _make_alert(db, "bruteforce")
        with patch("app.services.agent.service.settings") as mock_settings:
            mock_settings.THREAT_ENRICHMENT_ENABLED = True
            svc = AgentService(db)
            result = svc.recommend(alert, language="en")

        assert isinstance(result, RecommendationSchema)
        assert result.threat_context is not None
        assert len(result.threat_context.techniques) > 0

    def test_recommend_without_enrichment_flag(self, db):
        alert = _make_alert(db, "scan")
        with patch("app.services.agent.service.settings") as mock_settings:
            mock_settings.THREAT_ENRICHMENT_ENABLED = False
            svc = AgentService(db)
            result = svc.recommend(alert, language="en")

        assert result.threat_context is None


# ── Tests: backward compatibility ────────────────────────────────────────


class TestSchemaBackwardCompatibility:
    def test_investigation_without_threat_context_serializes(self, db):
        """threat_context=None should serialize cleanly (excluded or null)."""
        alert = _make_alert(db, "anomaly")
        with patch("app.services.agent.service.settings") as mock_settings:
            mock_settings.THREAT_ENRICHMENT_ENABLED = False
            svc = AgentService(db)
            result = svc.investigate(alert)

        data = result.model_dump()
        assert "hypothesis" in data
        assert "why" in data
        # threat_context is None — should be present as None
        assert data["threat_context"] is None

    def test_recommendation_with_threat_context_serializes(self, db):
        """Full enrichment should produce valid JSON."""
        alert = _make_alert(db, "dos")
        with patch("app.services.agent.service.settings") as mock_settings:
            mock_settings.THREAT_ENRICHMENT_ENABLED = True
            svc = AgentService(db)
            result = svc.recommend(alert)

        payload = result.model_dump_json()
        parsed = json.loads(payload)
        assert "threat_context" in parsed
        assert isinstance(parsed["threat_context"]["techniques"], list)
        assert parsed["threat_context"]["enrichment_source"] == "local_mitre_v1"

    def test_original_fields_intact(self, db):
        """Core fields must not be altered by enrichment."""
        alert = _make_alert(db, "scan")
        with patch("app.services.agent.service.settings") as mock_settings:
            mock_settings.THREAT_ENRICHMENT_ENABLED = True
            svc = AgentService(db)
            inv = svc.investigate(alert)

        assert inv.version == "1.1"
        assert inv.alert_id == alert.id
        assert inv.id  # UUID present
        assert inv.impact.confidence > 0
        assert len(inv.next_steps) > 0

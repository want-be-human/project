"""
Unit tests for PlanCompiler.
Covers:
  - action_type mapping (keyword → action_type)
  - target resolution (alert entities → ActionTarget)
  - confidence computation (severity × priority × evidence)
  - non-compilable actions are skipped
  - Chinese and English language support
  - rollback generation
  - evidence traceability
"""

import pytest
from unittest.mock import MagicMock

from app.schemas.agent import RecommendedAction, RecommendationSchema, InvestigationSchema, InvestigationImpact
from app.schemas.evidence import EvidenceChainSchema, EvidenceNode, EvidenceEdge
from app.services.plan_compiler.compiler import PlanCompiler
from app.services.plan_compiler.rules import match_action_type, compute_confidence


# ── Helpers ─────────────────────────────────────────────────────

def _make_alert(
    *,
    alert_id: str = "alert-1",
    alert_type: str = "bruteforce",
    severity: str = "high",
    src_ip: str = "192.0.2.10",
    dst_ip: str = "198.51.100.20",
    proto: str = "TCP",
    dst_port: int = 22,
) -> MagicMock:
    m = MagicMock()
    m.id = alert_id
    m.type = alert_type
    m.severity = severity
    m.primary_src_ip = src_ip
    m.primary_dst_ip = dst_ip
    m.primary_proto = proto
    m.primary_dst_port = dst_port
    return m


def _make_recommendation(
    *,
    alert_id: str = "alert-1",
    rec_id: str = "rec-1",
    actions: list[RecommendedAction] | None = None,
) -> RecommendationSchema:
    if actions is None:
        actions = [
            RecommendedAction(
                title="Temporary block source IP 192.0.2.10",
                priority="high",
                steps=["Add firewall rule to block 192.0.2.10"],
                rollback=["Remove firewall rule"],
                risk="May block legitimate traffic",
            ),
            RecommendedAction(
                title="Rate limit traffic to TCP/22",
                priority="medium",
                steps=["Configure rate limiting"],
                rollback=["Remove rate limiting rules"],
                risk="May impact high-volume users",
            ),
            RecommendedAction(
                title="Enhance monitoring for related entities",
                priority="medium",
                steps=["Add 192.0.2.10 to watchlist"],
                rollback=["Remove from watchlist"],
                risk="Increased log storage",
            ),
        ]
    return RecommendationSchema(
        version="1.1",
        id=rec_id,
        created_at="2026-01-15T12:00:00Z",
        alert_id=alert_id,
        actions=actions,
    )


def _make_investigation(
    *,
    alert_id: str = "alert-1",
    confidence: float = 0.8,
) -> InvestigationSchema:
    return InvestigationSchema(
        version="1.1",
        id="inv-1",
        created_at="2026-01-15T12:00:00Z",
        alert_id=alert_id,
        hypothesis="Possible brute-force attack",
        why=["Detected 18 anomalous flows", "Feature syn_count shows high value"],
        impact=InvestigationImpact(scope=["dst_ip:198.51.100.20"], confidence=confidence),
        next_steps=["Review flow records"],
    )


def _make_evidence_chain(
    *,
    alert_id: str = "alert-1",
) -> EvidenceChainSchema:
    return EvidenceChainSchema(
        version="1.1",
        id="ec-1",
        created_at="2026-01-15T12:00:00Z",
        alert_id=alert_id,
        nodes=[
            EvidenceNode(id=f"alert:{alert_id}", type="alert", label="bruteforce suspected"),
            EvidenceNode(id="flow:flow-1", type="flow", label="TCP/22 score=0.97"),
            EvidenceNode(id="flow:flow-2", type="flow", label="TCP/22 score=0.90"),
            EvidenceNode(id="feat:syn_count", type="feature", label="syn_count=120"),
            EvidenceNode(id="hyp:inv-1", type="hypothesis", label="Brute-force attack"),
        ],
        edges=[
            EvidenceEdge(source="flow:flow-1", target=f"alert:{alert_id}", type="supports"),
            EvidenceEdge(source="flow:flow-2", target=f"alert:{alert_id}", type="supports"),
            EvidenceEdge(source="feat:syn_count", target="flow:flow-1", type="explains"),
        ],
    )


# ══════════════════════════════════════════════════════════════════
# Rules: match_action_type
# ══════════════════════════════════════════════════════════════════

class TestMatchActionType:
    """Tests for keyword → action_type mapping."""

    @pytest.mark.parametrize("title,expected", [
        ("Temporary block source IP 192.0.2.10", "block_ip"),
        ("临时封禁源 IP 192.0.2.10", "block_ip"),
        ("Add to firewall blocklist", "block_ip"),
        ("Ban the attacker IP", "block_ip"),
        ("Isolate compromised host", "isolate_host"),
        ("隔离受感染主机", "isolate_host"),
        ("Quarantine the node", "isolate_host"),
        ("Segment internal network", "segment_subnet"),
        ("网络分段隔离", "segment_subnet"),
        ("Rate limit traffic to TCP/22", "rate_limit_service"),
        ("对 TCP/22 的流量进行速率限制", "rate_limit_service"),
        ("限流 SSH 服务", "rate_limit_service"),
        ("Throttle incoming connections", "rate_limit_service"),
    ])
    def test_compilable_actions(self, title: str, expected: str):
        assert match_action_type(title) == expected

    @pytest.mark.parametrize("title", [
        "Enhance monitoring for related entities",
        "加强对相关实体的监控",
        "Add to watchlist",
        "Enable detailed logging",
        "Set up alerts for similar patterns",
        "Enable SSH key-only authentication",
        "启用密钥认证",
    ])
    def test_non_compilable_actions_return_none(self, title: str):
        assert match_action_type(title) is None

    def test_unknown_title_returns_none(self):
        assert match_action_type("Do something entirely new") is None


# ══════════════════════════════════════════════════════════════════
# Rules: compute_confidence
# ══════════════════════════════════════════════════════════════════

class TestComputeConfidence:
    """Tests for confidence score calculation."""

    def test_critical_high_priority(self):
        score = compute_confidence("critical", "high", evidence_node_count=5)
        assert 0.9 <= score <= 0.95

    def test_low_severity_low_priority(self):
        score = compute_confidence("low", "low", evidence_node_count=0)
        assert score == 0.45

    def test_with_investigation_confidence(self):
        score = compute_confidence("high", "high", evidence_node_count=3, investigation_confidence=0.9)
        # 0.7 * (0.80 + 0.05 + 0.03) + 0.3 * 0.9 = 0.7 * 0.88 + 0.27 = 0.886
        assert 0.8 <= score <= 0.95

    def test_clamped_at_095(self):
        score = compute_confidence("critical", "high", evidence_node_count=100, investigation_confidence=0.99)
        assert score <= 0.95

    def test_clamped_at_0(self):
        score = compute_confidence("unknown", "unknown", evidence_node_count=0)
        assert score >= 0.0


# ══════════════════════════════════════════════════════════════════
# PlanCompiler
# ══════════════════════════════════════════════════════════════════

class TestPlanCompiler:
    """Tests for PlanCompiler.compile()."""

    def setup_method(self):
        self.compiler = PlanCompiler()
        self.alert = _make_alert()
        self.recommendation = _make_recommendation()
        self.investigation = _make_investigation()
        self.evidence_chain = _make_evidence_chain()

    def test_compile_returns_correct_count(self):
        """3 recommended actions → 2 compiled (monitoring skipped)."""
        compiled, skipped = self.compiler.compile(
            self.alert, self.recommendation, self.investigation, self.evidence_chain,
        )
        assert len(compiled) == 2
        assert skipped == 1

    def test_compiled_action_types(self):
        compiled, _ = self.compiler.compile(
            self.alert, self.recommendation, self.investigation, self.evidence_chain,
        )
        types = [a.action_type for a in compiled]
        assert "block_ip" in types
        assert "rate_limit_service" in types

    def test_block_ip_target(self):
        compiled, _ = self.compiler.compile(
            self.alert, self.recommendation, self.investigation, self.evidence_chain,
        )
        block_action = [a for a in compiled if a.action_type == "block_ip"][0]
        assert block_action.target.type == "ip"
        assert block_action.target.value == "192.0.2.10"

    def test_rate_limit_target(self):
        compiled, _ = self.compiler.compile(
            self.alert, self.recommendation, self.investigation, self.evidence_chain,
        )
        rl_action = [a for a in compiled if a.action_type == "rate_limit_service"][0]
        assert rl_action.target.type == "service"
        assert rl_action.target.value == "TCP/22"

    def test_rollback_generated(self):
        compiled, _ = self.compiler.compile(
            self.alert, self.recommendation, self.investigation, self.evidence_chain,
        )
        for action in compiled:
            assert action.rollback is not None
            assert action.rollback.action_type

    def test_confidence_populated(self):
        compiled, _ = self.compiler.compile(
            self.alert, self.recommendation, self.investigation, self.evidence_chain,
        )
        for action in compiled:
            assert action.confidence is not None
            assert 0.0 <= action.confidence <= 0.95

    def test_evidence_traced(self):
        compiled, _ = self.compiler.compile(
            self.alert, self.recommendation, self.investigation, self.evidence_chain,
        )
        for action in compiled:
            assert action.derived_from_evidence is not None
            assert len(action.derived_from_evidence) > 0
            # Should contain the alert node
            assert any("alert:" in eid for eid in action.derived_from_evidence)

    def test_reasoning_summary_populated(self):
        compiled, _ = self.compiler.compile(
            self.alert, self.recommendation, self.investigation, self.evidence_chain,
        )
        for action in compiled:
            assert action.reasoning_summary is not None
            assert len(action.reasoning_summary) > 10

    def test_reasoning_chinese(self):
        compiled, _ = self.compiler.compile(
            self.alert, self.recommendation, self.investigation, self.evidence_chain,
            language="zh",
        )
        for action in compiled:
            assert action.reasoning_summary is not None and ("编译为" in action.reasoning_summary or "置信度" in action.reasoning_summary)

    def test_compile_without_investigation(self):
        """Investigation is optional, should still compile."""
        compiled, skipped = self.compiler.compile(
            self.alert, self.recommendation, investigation=None, evidence_chain=None,
        )
        assert len(compiled) == 2
        assert skipped == 1

    def test_compile_no_compilable_actions(self):
        """All monitoring actions → 0 compiled."""
        rec = _make_recommendation(actions=[
            RecommendedAction(
                title="Enhance monitoring for related entities",
                priority="medium",
                steps=["Add to watchlist"],
                rollback=["Remove from watchlist"],
                risk="Log overhead",
            ),
        ])
        compiled, skipped = self.compiler.compile(self.alert, rec)
        assert len(compiled) == 0
        assert skipped == 1


class TestPlanCompilerTargetResolution:
    """Tests for _resolve_target edge cases."""

    def setup_method(self):
        self.compiler = PlanCompiler()

    def test_isolate_host_target(self):
        alert = _make_alert()
        rec = _make_recommendation(actions=[
            RecommendedAction(
                title="Isolate the compromised host",
                priority="high",
                steps=["Isolate"],
                rollback=["Restore"],
                risk="Downtime",
            ),
        ])
        compiled, _ = self.compiler.compile(alert, rec)
        assert len(compiled) == 1
        assert compiled[0].action_type == "isolate_host"
        assert compiled[0].target.type == "ip"
        assert compiled[0].target.value == "192.0.2.10"

    def test_segment_subnet_target(self):
        alert = _make_alert()
        rec = _make_recommendation(actions=[
            RecommendedAction(
                title="Segment the internal network",
                priority="medium",
                steps=["Segment"],
                rollback=["Unsegment"],
                risk="Connectivity",
            ),
        ])
        compiled, _ = self.compiler.compile(alert, rec)
        assert len(compiled) == 1
        assert compiled[0].action_type == "segment_subnet"
        assert compiled[0].target.type == "subnet"
        assert compiled[0].target.value == "192.0.2.0/24"

    def test_dos_alert_rate_limit(self):
        """DoS alert should map rate-limit to correct service."""
        alert = _make_alert(alert_type="dos", dst_port=80, proto="TCP")
        rec = _make_recommendation(actions=[
            RecommendedAction(
                title="Rate limit traffic to TCP/80",
                priority="high",
                steps=["Configure rate limiting"],
                rollback=["Remove rate limiting"],
                risk="May impact users",
            ),
        ])
        compiled, _ = self.compiler.compile(alert, rec)
        assert len(compiled) == 1
        assert compiled[0].target.value == "TCP/80"
        assert compiled[0].params["port"] == 80


class TestPlanCompilerParams:
    """Tests for compiled action params."""

    def setup_method(self):
        self.compiler = PlanCompiler()

    def test_block_ip_has_default_duration(self):
        alert = _make_alert()
        rec = _make_recommendation(actions=[
            RecommendedAction(
                title="Block the attacker",
                priority="high",
                steps=["Block"],
                rollback=["Unblock"],
                risk="Risk",
            ),
        ])
        compiled, _ = self.compiler.compile(alert, rec)
        assert compiled[0].params["duration_minutes"] == 60

    def test_rate_limit_has_default_max_connections(self):
        alert = _make_alert()
        rec = _make_recommendation(actions=[
            RecommendedAction(
                title="Rate limit the service",
                priority="medium",
                steps=["Limit"],
                rollback=["Unlimit"],
                risk="Risk",
            ),
        ])
        compiled, _ = self.compiler.compile(alert, rec)
        assert compiled[0].params["max_connections_per_minute"] == 10

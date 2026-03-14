"""
End-to-end test: alert → recommend → compile → dry-run.
Validates the full PlanCompiler integration chain:
  1. AgentService.recommend() generates recommendations
  2. PlanCompiler compiles them into PlanActions
  3. TwinService.create_plan() persists the plan
  4. TwinService.dry_run() consumes the compiled plan
"""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from app.services.agent.service import AgentService
from app.services.plan_compiler.compiler import PlanCompiler
from app.services.twin.service import TwinService
from app.schemas.agent import RecommendationSchema
from app.schemas.twin import (
    ActionPlanSchema,
    DryRunResultSchema,
    PlanAction,
)
from app.schemas.topology import (
    GraphResponseSchema,
    GraphNode,
    GraphEdge,
    GraphMeta,
)


# ── Helpers ──────────────────────────────────────────────────────

def _ts(offset_sec: int = 0) -> datetime:
    return datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=offset_sec)


def _make_alert(
    *,
    alert_id: str = "alert-e2e",
    alert_type: str = "bruteforce",
    severity: str = "high",
    src_ip: str = "192.0.2.10",
    dst_ip: str = "198.51.100.20",
    proto: str = "TCP",
    dst_port: int = 22,
    flow_count: int = 18,
) -> MagicMock:
    evidence = {
        "flow_ids": ["flow-1", "flow-2"],
        "top_flows": [
            {"flow_id": "flow-1", "anomaly_score": 0.97, "summary": f"TCP/{dst_port}"},
        ],
        "top_features": [
            {"name": "syn_count", "value": 120, "direction": "high"},
            {"name": "iat_mean_ms", "value": 50.5, "direction": "low"},
        ],
        "pcap_ref": {"pcap_id": "pcap-1", "offset_hint": None},
    }
    aggregation = {
        "rule": "same_src_ip + 60s_window",
        "group_key": f"{src_ip}@60s",
        "count_flows": flow_count,
    }
    agent = {"triage_summary": None, "investigation_id": None, "recommendation_id": None}
    twin = {"plan_id": None, "dry_run_id": None}

    m = MagicMock()
    m.id = alert_id
    m.type = alert_type
    m.severity = severity
    m.primary_src_ip = src_ip
    m.primary_dst_ip = dst_ip
    m.primary_proto = proto
    m.primary_dst_port = dst_port
    m.evidence = json.dumps(evidence)
    m.aggregation = json.dumps(aggregation)
    m.agent = json.dumps(agent)
    m.twin = json.dumps(twin)
    m.tags = json.dumps(["demo"])
    m.time_window_start = _ts(0)
    m.time_window_end = _ts(300)
    return m


def _make_simple_graph() -> GraphResponseSchema:
    return GraphResponseSchema(
        version="1.1",
        nodes=[
            GraphNode(id="ip:192.0.2.10", label="192.0.2.10", type="host", risk=0.9),
            GraphNode(id="ip:198.51.100.20", label="198.51.100.20", type="host", risk=0.5),
            GraphNode(id="ip:203.0.113.5", label="203.0.113.5", type="host", risk=0.1),
        ],
        edges=[
            GraphEdge(
                id="e1", source="ip:192.0.2.10", target="ip:198.51.100.20",
                proto="TCP", dst_port=22, weight=18, risk=0.9,
                activeIntervals=[["2026-01-15T12:00:00Z", "2026-01-15T12:05:00Z"]],
                alert_ids=["alert-e2e"],
            ),
            GraphEdge(
                id="e2", source="ip:198.51.100.20", target="ip:203.0.113.5",
                proto="TCP", dst_port=443, weight=5, risk=0.2,
                activeIntervals=[["2026-01-15T12:00:00Z", "2026-01-15T12:05:00Z"]],
                alert_ids=[],
            ),
        ],
        meta=GraphMeta(start="2026-01-15T12:00:00Z", end="2026-01-15T12:05:00Z", mode="ip"),
    )


# ══════════════════════════════════════════════════════════════════
# E2E: recommend → compile → create_plan → dry-run
# ══════════════════════════════════════════════════════════════════

class TestCompileDryRunE2E:
    """
    Full chain: recommend → compile → plan → dry-run.
    Validates that PlanCompiler output is directly consumable by TwinService.
    """

    def test_full_chain(self):
        """
        1) AgentService.recommend() → RecommendationSchema
        2) PlanCompiler.compile() → compiled PlanAction[]
        3) TwinService.create_plan() → ActionPlanSchema
        4) TwinService.dry_run() → DryRunResultSchema with impact
        """
        db = MagicMock()
        alert = _make_alert()

        # Step 1: Generate recommendation
        agent_svc = AgentService(db)
        recommendation = agent_svc.recommend(alert, language="en")

        assert isinstance(recommendation, RecommendationSchema)
        assert len(recommendation.actions) >= 2  # block + monitoring at minimum

        # Step 2: Compile recommendation into PlanActions
        compiler = PlanCompiler()
        compiled_actions, skipped = compiler.compile(
            alert=alert,
            recommendation=recommendation,
        )

        assert len(compiled_actions) >= 1
        assert skipped >= 1  # monitoring action should be skipped

        # Verify compiled actions have correct structure
        for action in compiled_actions:
            assert action.action_type in {"block_ip", "isolate_host", "segment_subnet", "rate_limit_service"}
            assert action.target is not None
            assert action.confidence is not None
            assert action.reasoning_summary is not None

        # Step 3: Create plan via TwinService
        db_for_plan = MagicMock()
        db_for_plan.query.return_value.filter.return_value.first.return_value = alert
        twin_svc = TwinService(db_for_plan)
        plan = twin_svc.create_plan(
            alert_id=alert.id,
            actions=compiled_actions,
            source="agent",
            notes=f"Compiled from recommendation {recommendation.id}",
        )

        assert isinstance(plan, ActionPlanSchema)
        assert plan.source == "agent"
        assert len(plan.actions) == len(compiled_actions)

        # Step 4: Dry-run using the compiled plan
        with patch.object(TwinService, "__init__", lambda self, db: None):
            dry_svc = TwinService.__new__(TwinService)
            dry_svc.db = MagicMock()
            dry_svc.db.query.return_value.filter.return_value.first.return_value = alert
            dry_svc.topology_service = MagicMock()
            dry_svc.topology_service.build_graph.return_value = _make_simple_graph()
            dry_svc.topology_service.compute_graph_hash.side_effect = ["hash_before", "hash_after"]

            # Create a mock plan model matching what DB would return
            plan_model = MagicMock()
            plan_model.id = plan.id
            plan_model.alert_id = alert.id
            plan_model.actions = json.dumps([a.model_dump() for a in compiled_actions])

            result = dry_svc.dry_run(plan_model, _ts(0), _ts(300), "ip")

        assert isinstance(result, DryRunResultSchema)
        assert result.alert_id == alert.id
        assert result.plan_id == plan.id
        # Block IP 192.0.2.10 should impact at least edge e1
        assert result.impact.impacted_edges_count >= 1

    def test_recommendation_preserved(self):
        """Recommendation natural language output must be preserved."""
        db = MagicMock()
        alert = _make_alert()

        agent_svc = AgentService(db)
        recommendation = agent_svc.recommend(alert, language="en")

        # Compile
        compiler = PlanCompiler()
        compiled_actions, _ = compiler.compile(alert=alert, recommendation=recommendation)

        # Original recommendation unchanged
        for action in recommendation.actions:
            assert action.title  # title preserved
            assert action.steps  # steps preserved
            assert action.rollback  # rollback preserved

        # Compiled actions are separate objects
        assert len(compiled_actions) < len(recommendation.actions)  # monitoring skipped

    def test_chinese_chain(self):
        """Full chain with Chinese language."""
        db = MagicMock()
        alert = _make_alert()

        agent_svc = AgentService(db)
        recommendation = agent_svc.recommend(alert, language="zh")

        compiler = PlanCompiler()
        compiled_actions, skipped = compiler.compile(
            alert=alert,
            recommendation=recommendation,
            language="zh",
        )

        assert len(compiled_actions) >= 1
        # Reasoning summaries should be in Chinese
        for action in compiled_actions:
            assert "编译为" in action.reasoning_summary or "置信度" in action.reasoning_summary

    def test_dos_alert_chain(self):
        """DoS alert → rate_limit recommendation → compiled plan."""
        db = MagicMock()
        alert = _make_alert(alert_type="dos", severity="high", dst_port=80)

        agent_svc = AgentService(db)
        recommendation = agent_svc.recommend(alert, language="en")

        compiler = PlanCompiler()
        compiled_actions, _ = compiler.compile(alert=alert, recommendation=recommendation)

        # DoS should produce rate_limit_service
        rl_actions = [a for a in compiled_actions if a.action_type == "rate_limit_service"]
        assert len(rl_actions) >= 1
        assert rl_actions[0].target.value == "TCP/80"

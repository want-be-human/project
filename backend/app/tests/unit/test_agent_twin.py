"""
Unit tests for AgentService and TwinService.
Covers DOC B B4.7 / B4.9 / B6 / DOC F Week-7 DoD:
  - triage generates summary string
  - investigate returns Investigation with why/confidence/next_steps
  - recommend returns Recommendation with >=1 action
  - twin create_plan saves and returns ActionPlan
  - twin dry-run: 给简单图 + action → impact 断言 (DOC B B6)
"""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from app.services.agent.service import AgentService
from app.services.twin.service import TwinService
from app.schemas.agent import (
    InvestigationSchema,
    RecommendationSchema,
)
from app.schemas.twin import (
    ActionPlanSchema,
    DryRunResultSchema,
    PlanAction,
    ActionTarget,
    RollbackAction,
    ReachabilityDetail,
    ServiceRiskBreakdown,
    ExplainSection,
)
from app.schemas.topology import (
    GraphResponseSchema,
    GraphNode,
    GraphEdge,
    GraphMeta,
)


# ── helpers ──────────────────────────────────────────────────────

def _ts(offset_sec: int = 0) -> datetime:
    return datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=offset_sec)


def _make_alert(
    *,
    id: str = "alert-1",
    alert_type: str = "bruteforce",
    severity: str = "high",
    src_ip: str = "192.0.2.10",
    dst_ip: str = "198.51.100.20",
    proto: str = "TCP",
    dst_port: int = 22,
    flow_count: int = 18,
    top_features: list[dict] | None = None,
) -> MagicMock:
    if top_features is None:
        top_features = [
            {"name": "syn_count", "value": 120, "direction": "high"},
            {"name": "iat_mean_ms", "value": 50.5, "direction": "low"},
        ]

    evidence = {
        "flow_ids": ["flow-1", "flow-2"],
        "top_flows": [
            {"flow_id": "flow-1", "anomaly_score": 0.97, "summary": f"TCP/{dst_port}"},
        ],
        "top_features": top_features,
        "pcap_ref": {"pcap_id": "pcap-1", "offset_hint": None},
    }
    aggregation = {
        "rule": "same_src_ip + 60s_window",
        "group_key": f"{src_ip}@60s",
        "count_flows": flow_count,
    }
    agent = {
        "triage_summary": None,
        "investigation_id": None,
        "recommendation_id": None,
    }
    twin = {
        "plan_id": None,
        "dry_run_id": None,
    }

    m = MagicMock()
    m.id = id
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
    """
    简单图: A ---> B ---> C
    block A → 移除 A 相关边 → impact > 0
    """
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
                alert_ids=["alert-1"],
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
# Agent Service
# ══════════════════════════════════════════════════════════════════

class TestAgentTriage:
    """Tests for AgentService.triage."""

    def test_triage_returns_summary_en(self):
        db = MagicMock()
        alert = _make_alert()
        svc = AgentService(db)
        summary = svc.triage(alert, language="en")
        assert isinstance(summary, str)
        assert len(summary) > 20
        assert "critical" in summary or "high" in summary or alert.primary_src_ip in summary

    def test_triage_returns_summary_zh(self):
        db = MagicMock()
        alert = _make_alert()
        svc = AgentService(db)
        summary = svc.triage(alert, language="zh")
        assert isinstance(summary, str)
        assert len(summary) > 10

    def test_triage_updates_agent_field(self):
        db = MagicMock()
        alert = _make_alert()
        svc = AgentService(db)
        svc.triage(alert, language="en")
        # agent field should have been updated
        updated = json.loads(alert.agent)
        assert updated["triage_summary"] is not None
        db.commit.assert_called()


class TestAgentInvestigate:
    """Tests for AgentService.investigate."""

    def test_investigate_returns_investigation(self):
        db = MagicMock()
        alert = _make_alert()
        svc = AgentService(db)
        inv = svc.investigate(alert)
        assert isinstance(inv, InvestigationSchema)
        assert inv.version == "1.1"
        assert inv.alert_id == "alert-1"

    def test_investigation_has_required_fields(self):
        db = MagicMock()
        alert = _make_alert()
        svc = AgentService(db)
        inv = svc.investigate(alert)
        assert len(inv.hypothesis) > 0
        assert len(inv.why) >= 2
        assert 0.0 <= inv.impact.confidence <= 1.0
        assert len(inv.impact.scope) >= 1
        assert len(inv.next_steps) >= 2
        assert "Advisory" in inv.safety_note or "advisory" in inv.safety_note.lower()

    def test_investigate_saves_to_db(self):
        db = MagicMock()
        alert = _make_alert()
        svc = AgentService(db)
        inv = svc.investigate(alert)
        db.add.assert_called_once()
        db.commit.assert_called()
        # agent.investigation_id should be updated
        updated_agent = json.loads(alert.agent)
        assert updated_agent["investigation_id"] == inv.id


class TestAgentRecommend:
    """Tests for AgentService.recommend."""

    def test_recommend_returns_recommendation(self):
        db = MagicMock()
        alert = _make_alert()
        svc = AgentService(db)
        rec = svc.recommend(alert)
        assert isinstance(rec, RecommendationSchema)
        assert rec.version == "1.1"
        assert rec.alert_id == "alert-1"

    def test_recommendation_has_actions(self):
        db = MagicMock()
        alert = _make_alert()
        svc = AgentService(db)
        rec = svc.recommend(alert)
        assert len(rec.actions) >= 1
        for action in rec.actions:
            assert action.title
            assert action.priority in ["high", "medium", "low"]
            assert len(action.steps) >= 1
            assert len(action.rollback) >= 1

    def test_recommend_saves_to_db(self):
        db = MagicMock()
        alert = _make_alert()
        svc = AgentService(db)
        rec = svc.recommend(alert)
        db.add.assert_called_once()
        db.commit.assert_called()
        updated_agent = json.loads(alert.agent)
        assert updated_agent["recommendation_id"] == rec.id


# ══════════════════════════════════════════════════════════════════
# Twin Service
# ══════════════════════════════════════════════════════════════════

class TestTwinCreatePlan:
    """Tests for TwinService.create_plan."""

    def test_create_plan_returns_schema(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = _make_alert()
        svc = TwinService(db)
        actions = [
            PlanAction(
                action_type="block_ip",
                target=ActionTarget(type="ip", value="192.0.2.10"),
                params={"duration_minutes": 60},
                rollback=RollbackAction(action_type="unblock_ip", params={}),
            )
        ]
        plan = svc.create_plan(alert_id="alert-1", actions=actions, source="manual", notes="test")
        assert isinstance(plan, ActionPlanSchema)
        assert plan.version == "1.1"
        assert plan.alert_id == "alert-1"
        assert plan.source == "manual"
        assert len(plan.actions) == 1
        assert plan.actions[0].action_type == "block_ip"

    def test_create_plan_saves_to_db(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = _make_alert()
        svc = TwinService(db)
        actions = [PlanAction(action_type="block_ip", target=ActionTarget(type="ip", value="1.2.3.4"))]
        svc.create_plan(alert_id="alert-1", actions=actions, source="agent")
        db.add.assert_called_once()
        db.commit.assert_called()


class TestTwinDryRun:
    """
    Tests for TwinService.dry_run.
    DOC B B6 要求: 给简单图 + action → impact 断言
    """

    def _make_plan(self, actions_list):
        plan = MagicMock()
        plan.id = "plan-1"
        plan.alert_id = "alert-1"
        plan.actions = json.dumps(actions_list)
        return plan

    @patch.object(TwinService, "__init__", lambda self, db: None)
    def test_block_ip_removes_edges(self):
        """block_ip(192.0.2.10) 应移除源节点的所有边。"""
        svc = TwinService.__new__(TwinService)
        svc.db = MagicMock()
        svc.db.query.return_value.filter.return_value.first.return_value = _make_alert()
        svc.db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        svc.topology_service = MagicMock()
        svc.topology_service.build_graph.return_value = _make_simple_graph()
        svc.topology_service.compute_graph_hash.side_effect = ["hash_before", "hash_after"]

        plan = self._make_plan([{
            "action_type": "block_ip",
            "target": {"type": "ip", "value": "192.0.2.10"},
            "params": {},
        }])

        result = svc.dry_run(plan, _ts(0), _ts(300), "ip")
        assert isinstance(result, DryRunResultSchema)
        assert result.impact.impacted_edges_count >= 1
        assert result.impact.reachability_drop > 0
        assert "TCP/22" in result.impact.affected_services
        # v1.2 新增字段断言
        assert len(result.impact.removed_edge_ids) >= 1
        assert result.impact.reachability_detail is not None
        assert result.impact.service_risk_breakdown is not None

    @patch.object(TwinService, "__init__", lambda self, db: None)
    def test_isolate_host_removes_node(self):
        """isolate_host(198.51.100.20) 应移除节点和所有关联边。"""
        svc = TwinService.__new__(TwinService)
        svc.db = MagicMock()
        svc.db.query.return_value.filter.return_value.first.return_value = _make_alert()
        svc.db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        svc.topology_service = MagicMock()
        svc.topology_service.build_graph.return_value = _make_simple_graph()
        svc.topology_service.compute_graph_hash.side_effect = ["h1", "h2"]

        plan = self._make_plan([{
            "action_type": "isolate_host",
            "target": {"type": "ip", "value": "198.51.100.20"},
            "params": {},
        }])

        result = svc.dry_run(plan, _ts(0), _ts(300), "ip")
        assert result.impact.impacted_nodes_count >= 1
        assert result.impact.impacted_edges_count == 2  # both edges touch this node
        # v1.2 新增字段断言
        assert "ip:198.51.100.20" in result.impact.removed_node_ids
        assert len(result.impact.affected_node_ids) > 0  # 邻居节点受波及

    @patch.object(TwinService, "__init__", lambda self, db: None)
    def test_rate_limit_marks_affected_services(self):
        """rate_limit_service(tcp/22) 应标记 affected_services 但不删边。"""
        svc = TwinService.__new__(TwinService)
        svc.db = MagicMock()
        svc.db.query.return_value.filter.return_value.first.return_value = _make_alert()
        svc.db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        svc.topology_service = MagicMock()
        svc.topology_service.build_graph.return_value = _make_simple_graph()
        svc.topology_service.compute_graph_hash.side_effect = ["h1", "h2"]

        plan = self._make_plan([{
            "action_type": "rate_limit_service",
            "target": {"type": "service", "value": "tcp/22"},
            "params": {},
        }])

        result = svc.dry_run(plan, _ts(0), _ts(300), "ip")
        # rate limit doesn't remove edges
        assert result.impact.impacted_edges_count == 0
        assert "TCP/22" in result.impact.affected_services

    @patch.object(TwinService, "__init__", lambda self, db: None)
    def test_dryrun_result_structure(self):
        """DryRunResult 必须包含 DOC C C2.2 v1.2 所有字段。"""
        svc = TwinService.__new__(TwinService)
        svc.db = MagicMock()
        svc.db.query.return_value.filter.return_value.first.return_value = _make_alert()
        svc.db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        svc.topology_service = MagicMock()
        svc.topology_service.build_graph.return_value = _make_simple_graph()
        svc.topology_service.compute_graph_hash.side_effect = ["sha256:aaa", "sha256:bbb"]

        plan = self._make_plan([{
            "action_type": "block_ip",
            "target": {"type": "ip", "value": "192.0.2.10"},
            "params": {},
        }])

        result = svc.dry_run(plan, _ts(0), _ts(300), "ip")

        assert result.version == "1.2"
        assert result.plan_id == "plan-1"
        assert result.alert_id == "alert-1"
        assert result.before.graph_hash.startswith("sha256:")
        assert result.after.graph_hash.startswith("sha256:")
        # 兼容旧字段
        assert isinstance(result.impact.impacted_nodes_count, int)
        assert isinstance(result.impact.impacted_edges_count, int)
        assert 0.0 <= result.impact.reachability_drop <= 1.0
        assert 0.0 <= result.impact.service_disruption_risk <= 1.0
        assert isinstance(result.impact.affected_services, list)
        assert isinstance(result.impact.warnings, list)
        assert isinstance(result.alternative_paths, list)
        assert isinstance(result.explain, list)
        assert len(result.explain) >= 1
        # v1.2 新增字段
        assert isinstance(result.impact.removed_node_ids, list)
        assert isinstance(result.impact.removed_edge_ids, list)
        assert isinstance(result.impact.affected_node_ids, list)
        assert isinstance(result.impact.affected_edge_ids, list)
        assert result.impact.reachability_detail is not None
        assert isinstance(result.impact.reachability_detail, ReachabilityDetail)
        assert isinstance(result.impact.impacted_services, list)
        assert result.impact.service_risk_breakdown is not None
        assert isinstance(result.impact.service_risk_breakdown, ServiceRiskBreakdown)
        assert 0.0 <= result.impact.confidence <= 1.0
        assert isinstance(result.explain_sections, list)

    @patch.object(TwinService, "__init__", lambda self, db: None)
    def test_no_action_graph_unchanged(self):
        """无 action 时，before/after graph hash 相同，impact 为 0。"""
        svc = TwinService.__new__(TwinService)
        svc.db = MagicMock()
        svc.db.query.return_value.filter.return_value.first.return_value = _make_alert()
        svc.db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        svc.topology_service = MagicMock()
        svc.topology_service.build_graph.return_value = _make_simple_graph()
        svc.topology_service.compute_graph_hash.side_effect = ["same_hash", "same_hash"]

        plan = self._make_plan([])
        result = svc.dry_run(plan, _ts(0), _ts(300), "ip")

        assert result.impact.impacted_nodes_count == 0
        assert result.impact.impacted_edges_count == 0
        assert result.impact.reachability_drop == 0.0
        # v1.2 新增字段应为空/零
        assert result.impact.removed_node_ids == []
        assert result.impact.removed_edge_ids == []
        assert result.impact.reachability_detail is not None
        assert result.impact.reachability_detail.pair_reachability_drop == 0.0

    @patch.object(TwinService, "__init__", lambda self, db: None)
    def test_dryrun_saves_to_db(self):
        """Dry-run 结果应持久化到 DB。"""
        svc = TwinService.__new__(TwinService)
        svc.db = MagicMock()
        svc.db.query.return_value.filter.return_value.first.return_value = _make_alert()
        svc.db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        svc.topology_service = MagicMock()
        svc.topology_service.build_graph.return_value = _make_simple_graph()
        svc.topology_service.compute_graph_hash.side_effect = ["h1", "h2"]

        plan = self._make_plan([{
            "action_type": "block_ip",
            "target": {"type": "ip", "value": "192.0.2.10"},
            "params": {},
        }])

        svc.dry_run(plan, _ts(0), _ts(300), "ip")
        svc.db.add.assert_called_once()
        svc.db.commit.assert_called()

    @patch.object(TwinService, "__init__", lambda self, db: None)
    def test_warnings_when_high_impact(self):
        """当 reachability_drop > 20% 时应产生 warning。"""
        svc = TwinService.__new__(TwinService)
        svc.db = MagicMock()
        svc.db.query.return_value.filter.return_value.first.return_value = _make_alert()
        svc.db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        svc.topology_service = MagicMock()
        svc.topology_service.build_graph.return_value = _make_simple_graph()
        svc.topology_service.compute_graph_hash.side_effect = ["h1", "h2"]

        # Block the middle node → removes both edges → 100% drop
        plan = self._make_plan([{
            "action_type": "isolate_host",
            "target": {"type": "ip", "value": "198.51.100.20"},
            "params": {},
        }])

        result = svc.dry_run(plan, _ts(0), _ts(300), "ip")
        assert result.impact.reachability_drop > 0
        # 应触发可达性下降告警
        assert any("可达性" in w or "reachability" in w.lower() for w in result.impact.warnings)

    @patch.object(TwinService, "__init__", lambda self, db: None)
    def test_explain_sections_structure(self):
        """explain_sections 应包含 5 个结构化段落。"""
        svc = TwinService.__new__(TwinService)
        svc.db = MagicMock()
        svc.db.query.return_value.filter.return_value.first.return_value = _make_alert()
        svc.db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        svc.topology_service = MagicMock()
        svc.topology_service.build_graph.return_value = _make_simple_graph()
        svc.topology_service.compute_graph_hash.side_effect = ["h1", "h2"]

        plan = self._make_plan([{
            "action_type": "block_ip",
            "target": {"type": "ip", "value": "192.0.2.10"},
            "params": {},
        }])

        result = svc.dry_run(plan, _ts(0), _ts(300), "ip")

        assert len(result.explain_sections) == 5
        section_types = {s.section for s in result.explain_sections}
        assert section_types == {
            "affected_objects", "impact_reason", "metric_changes",
            "risk_judgment", "recommended_actions",
        }
        for s in result.explain_sections:
            assert isinstance(s, ExplainSection)
            assert s.title
            assert isinstance(s.content, list)

    @patch.object(TwinService, "__init__", lambda self, db: None)
    def test_confidence_range(self):
        """confidence 应在 [0, IMPACT_CONFIDENCE_CAP] 范围内。"""
        from app.core.scoring_policy import IMPACT_CONFIDENCE_CAP

        svc = TwinService.__new__(TwinService)
        svc.db = MagicMock()
        svc.db.query.return_value.filter.return_value.first.return_value = _make_alert()
        svc.db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        svc.topology_service = MagicMock()
        svc.topology_service.build_graph.return_value = _make_simple_graph()
        svc.topology_service.compute_graph_hash.side_effect = ["h1", "h2"]

        plan = self._make_plan([{
            "action_type": "block_ip",
            "target": {"type": "ip", "value": "192.0.2.10"},
            "params": {},
        }])

        result = svc.dry_run(plan, _ts(0), _ts(300), "ip")
        assert 0.0 <= result.impact.confidence <= IMPACT_CONFIDENCE_CAP

    @patch.object(TwinService, "__init__", lambda self, db: None)
    def test_impacted_services_detail(self):
        """impacted_services 应包含正确的服务分解。"""
        svc = TwinService.__new__(TwinService)
        svc.db = MagicMock()
        svc.db.query.return_value.filter.return_value.first.return_value = _make_alert()
        svc.db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        svc.topology_service = MagicMock()
        svc.topology_service.build_graph.return_value = _make_simple_graph()
        svc.topology_service.compute_graph_hash.side_effect = ["h1", "h2"]

        plan = self._make_plan([{
            "action_type": "block_ip",
            "target": {"type": "ip", "value": "192.0.2.10"},
            "params": {},
        }])

        result = svc.dry_run(plan, _ts(0), _ts(300), "ip")

        # block_ip 192.0.2.10 影响 tcp/22 服务
        services = result.impact.impacted_services
        assert len(services) >= 1
        svc_names = [s.service for s in services]
        assert "TCP/22" in svc_names
        for s in services:
            assert s.importance_weight > 0
            assert 0.0 <= s.traffic_proportion <= 1.0

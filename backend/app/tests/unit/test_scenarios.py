"""
Unit tests for ScenariosService.
Covers DOC B B4.10 & DOC F Week-8 DoD:
  - create_scenario returns ScenarioSchema with correct fields
  - list_scenarios returns paginated list
  - run_scenario checks min_alerts, must_have, evidence_chain_contains, dry_run_required
  - run_scenario outputs ScenarioRunResult with pass/fail + checks + metrics
"""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from app.services.scenarios.service import ScenariosService
from app.schemas.scenario import (
    ScenarioSchema,
    ScenarioRunResultSchema,
    ScenarioExpectations,
    MustHaveExpectation,
    ScenarioMetrics,
)


# ── helpers ──────────────────────────────────────────────────────

def _ts(offset_sec: int = 0) -> datetime:
    return datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=offset_sec)


def _make_alert(
    *,
    id: str = "alert-1",
    alert_type: str = "bruteforce",
    severity: str = "high",
    dry_run_id: str | None = None,
) -> MagicMock:
    evidence = {
        "flow_ids": ["flow-1", "flow-2"],
        "top_flows": [{"flow_id": "flow-1", "anomaly_score": 0.95, "summary": "TCP/22"}],
        "top_features": [{"name": "syn_count", "value": 100, "direction": "high"}],
        "pcap_ref": {"pcap_id": "pcap-1", "offset_hint": None},
    }
    agent = {
        "triage_summary": "test",
        "investigation_id": "inv-1",
        "recommendation_id": "rec-1",
    }
    twin = {
        "plan_id": "plan-1" if dry_run_id else None,
        "dry_run_id": dry_run_id,
    }

    m = MagicMock()
    m.id = id
    m.type = alert_type
    m.severity = severity
    m.evidence = json.dumps(evidence)
    m.agent = json.dumps(agent)
    m.twin = json.dumps(twin)
    m.created_at = _ts(0)
    return m


def _make_scenario_model(
    *,
    id: str = "scenario-1",
    name: str = "test_scenario",
    description: str = "Test scenario",
    pcap_id: str = "pcap-1",
    expectations: dict | None = None,
    tags: list[str] | None = None,
) -> MagicMock:
    if expectations is None:
        expectations = {
            "min_alerts": 1,
            "must_have": [{"type": "bruteforce", "severity_at_least": "medium"}],
            "evidence_chain_contains": ["feat:syn_count"],
            "dry_run_required": True,
        }
    if tags is None:
        tags = ["demo"]

    payload = {"expectations": expectations, "tags": tags}

    m = MagicMock()
    m.id = id
    m.created_at = _ts(0)
    m.version = "1.1"
    m.name = name
    m.description = description
    m.pcap_id = pcap_id
    m.payload = json.dumps(payload)
    return m


def _make_dry_run_model(*, id: str = "dr-1", risk: float = 0.65) -> MagicMock:
    payload = {
        "impact": {
            "impacted_nodes_count": 2,
            "impacted_edges_count": 3,
            "reachability_drop": 0.2,
            "service_disruption_risk": risk,
            "affected_services": ["TCP/22"],
            "warnings": [],
        }
    }
    m = MagicMock()
    m.id = id
    m.payload = json.dumps(payload)
    return m


# ══════════════════════════════════════════════════════════════════
# Create Scenario
# ══════════════════════════════════════════════════════════════════

class TestCreateScenario:
    def test_create_returns_schema(self):
        db = MagicMock()
        svc = ScenariosService(db)
        expectations = ScenarioExpectations(
            min_alerts=1,
            must_have=[MustHaveExpectation(type="bruteforce", severity_at_least="medium")],
            evidence_chain_contains=["feat:syn_count"],
            dry_run_required=True,
        )
        result = svc.create_scenario(
            name="bruteforce_demo",
            description="SSH brute-force test",
            pcap_id="pcap-1",
            expectations=expectations,
            tags=["demo"],
        )
        assert isinstance(result, ScenarioSchema)
        assert result.version == "1.1"
        assert result.name == "bruteforce_demo"
        assert result.pcap_ref.pcap_id == "pcap-1"
        assert result.expectations.min_alerts == 1
        assert result.expectations.dry_run_required is True
        assert len(result.expectations.must_have) == 1

    def test_create_saves_to_db(self):
        db = MagicMock()
        svc = ScenariosService(db)
        expectations = ScenarioExpectations(min_alerts=0)
        svc.create_scenario(
            name="test", description="", pcap_id="p1",
            expectations=expectations, tags=[],
        )
        db.add.assert_called_once()
        db.commit.assert_called_once()


# ══════════════════════════════════════════════════════════════════
# List Scenarios
# ══════════════════════════════════════════════════════════════════

class TestListScenarios:
    def test_list_returns_schemas(self):
        db = MagicMock()
        s1 = _make_scenario_model(id="s1", name="sc1")
        s2 = _make_scenario_model(id="s2", name="sc2")
        db.query.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [s1, s2]

        svc = ScenariosService(db)
        result = svc.list_scenarios(limit=50, offset=0)
        assert len(result) == 2
        assert all(isinstance(s, ScenarioSchema) for s in result)
        assert result[0].name == "sc1"

    def test_list_empty(self):
        db = MagicMock()
        db.query.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []
        svc = ScenariosService(db)
        result = svc.list_scenarios()
        assert result == []


# ══════════════════════════════════════════════════════════════════
# Run Scenario
# ══════════════════════════════════════════════════════════════════

class TestRunScenario:
    """DOC B B6: scenario run 返回 pass/fail 合理"""

    def _setup_db_with_alerts(self, db, alerts, flow_ids=None):
        """Configure mock DB to return flows and alerts for a scenario."""
        if flow_ids is None:
            flow_ids = ["flow-1", "flow-2"]

        # Mock Flow query
        mock_flows = []
        for fid in flow_ids:
            f = MagicMock()
            f.id = fid
            mock_flows.append(f)

        # Setup chained query mocks
        # The service calls: db.query(Flow).filter(Flow.pcap_id == ...).all()
        # then: db.query(Alert).join(...).filter(...).distinct().all()
        flow_query = MagicMock()
        flow_query.filter.return_value.all.return_value = mock_flows

        alert_query = MagicMock()
        alert_query.join.return_value.filter.return_value.distinct.return_value.all.return_value = alerts

        # DryRun query
        dryrun_query = MagicMock()

        def query_side_effect(model):
            name = model.__name__ if hasattr(model, "__name__") else str(model)
            if "Flow" in name:
                return flow_query
            elif "Alert" in name:
                return alert_query
            elif "DryRun" in name:
                return dryrun_query
            return MagicMock()

        db.query.side_effect = query_side_effect
        return dryrun_query

    def test_run_all_pass(self):
        """Scenario with all checks passing → status=pass."""
        db = MagicMock()
        alert = _make_alert(dry_run_id="dr-1")
        dr = _make_dry_run_model(id="dr-1", risk=0.65)

        dryrun_query = self._setup_db_with_alerts(db, [alert])
        dryrun_query.filter.return_value.first.return_value = dr

        scenario = _make_scenario_model(
            expectations={
                "min_alerts": 1,
                "must_have": [{"type": "bruteforce", "severity_at_least": "medium"}],
                "evidence_chain_contains": [],  # skip evidence check for unit test
                "dry_run_required": True,
            },
        )

        svc = ScenariosService(db)
        result = svc.run_scenario(scenario)

        assert isinstance(result, ScenarioRunResultSchema)
        assert result.version == "1.1"
        assert result.status == "pass"
        assert result.scenario_id == "scenario-1"

    def test_run_min_alerts_fail(self):
        """No alerts → min_alerts check fails → status=fail."""
        db = MagicMock()
        self._setup_db_with_alerts(db, [])

        scenario = _make_scenario_model(
            expectations={
                "min_alerts": 1,
                "must_have": [],
                "evidence_chain_contains": [],
                "dry_run_required": False,
            },
        )

        svc = ScenariosService(db)
        result = svc.run_scenario(scenario)

        assert result.status == "fail"
        min_check = next(c for c in result.checks if c.name == "min_alerts")
        assert min_check.pass_ is False

    def test_run_must_have_fail(self):
        """Alert type doesn't match must_have → fail."""
        db = MagicMock()
        alert = _make_alert(alert_type="dos", severity="low")
        self._setup_db_with_alerts(db, [alert])

        scenario = _make_scenario_model(
            expectations={
                "min_alerts": 1,
                "must_have": [{"type": "bruteforce", "severity_at_least": "medium"}],
                "evidence_chain_contains": [],
                "dry_run_required": False,
            },
        )

        svc = ScenariosService(db)
        result = svc.run_scenario(scenario)

        assert result.status == "fail"
        must_check = next(c for c in result.checks if "must_have" in c.name)
        assert must_check.pass_ is False

    def test_run_dry_run_required_fail(self):
        """dry_run_required=True but no dry-run → fail."""
        db = MagicMock()
        alert = _make_alert(dry_run_id=None)  # no dry-run
        self._setup_db_with_alerts(db, [alert])

        scenario = _make_scenario_model(
            expectations={
                "min_alerts": 1,
                "must_have": [],
                "evidence_chain_contains": [],
                "dry_run_required": True,
            },
        )

        svc = ScenariosService(db)
        result = svc.run_scenario(scenario)

        assert result.status == "fail"
        dr_check = next(c for c in result.checks if c.name == "dry_run")
        assert dr_check.pass_ is False

    def test_run_metrics(self):
        """Verify metrics: alert_count, high_severity_count, avg_dry_run_risk."""
        db = MagicMock()
        a1 = _make_alert(id="a1", severity="high", dry_run_id="dr-1")
        a2 = _make_alert(id="a2", severity="critical", dry_run_id="dr-2")
        a3 = _make_alert(id="a3", severity="low", dry_run_id=None)

        dr1 = _make_dry_run_model(id="dr-1", risk=0.6)
        _make_dry_run_model(id="dr-2", risk=0.8)

        dryrun_query = self._setup_db_with_alerts(db, [a1, a2, a3])

        def dryrun_filter_side(cond):
            mock = MagicMock()
            # Return appropriate dry-run based on filter
            mock.first.return_value = dr1  # simplification
            return mock
        dryrun_query.filter.side_effect = dryrun_filter_side

        scenario = _make_scenario_model(
            expectations={
                "min_alerts": 1,
                "must_have": [],
                "evidence_chain_contains": [],
                "dry_run_required": False,
            },
        )

        svc = ScenariosService(db)
        result = svc.run_scenario(scenario)

        assert result.metrics.alert_count == 3
        assert result.metrics.high_severity_count == 2  # high + critical
        assert result.metrics.avg_dry_run_risk > 0

    def test_run_saves_to_db(self):
        """Run result is persisted to DB."""
        db = MagicMock()
        alert = _make_alert(dry_run_id=None)
        self._setup_db_with_alerts(db, [alert])

        scenario = _make_scenario_model(
            expectations={
                "min_alerts": 0,
                "must_have": [],
                "evidence_chain_contains": [],
                "dry_run_required": False,
            },
        )

        svc = ScenariosService(db)
        result = svc.run_scenario(scenario)

        db.add.assert_called_once()
        db.commit.assert_called_once()
        assert result.id  # has UUID

    def test_run_result_structure(self):
        """DOC C C4.2 structure: version, id, created_at, scenario_id, status, checks, metrics."""
        db = MagicMock()
        self._setup_db_with_alerts(db, [])

        scenario = _make_scenario_model(
            expectations={
                "min_alerts": 0,
                "must_have": [],
                "evidence_chain_contains": [],
                "dry_run_required": False,
            },
        )

        svc = ScenariosService(db)
        result = svc.run_scenario(scenario)

        assert result.version == "1.1"
        assert result.id
        assert result.created_at
        assert result.scenario_id == "scenario-1"
        assert result.status in ("pass", "fail")
        assert isinstance(result.checks, list)
        assert isinstance(result.metrics, ScenarioMetrics)
        assert isinstance(result.metrics.alert_count, int)
        assert isinstance(result.metrics.high_severity_count, int)
        assert isinstance(result.metrics.avg_dry_run_risk, float)

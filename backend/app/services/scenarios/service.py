import json

from sqlalchemy.orm import Session

from fastapi import HTTPException

from app.core.logging import get_logger
from app.core.utils import generate_uuid, utc_now, datetime_to_iso
from app.models.scenario import Scenario, ScenarioRun
from app.models.alert import Alert
from app.schemas.scenario import (
    ScenarioSchema,
    ScenarioRunResultSchema,
    ScenarioExpectations,
    ScenarioCheck,
    ScenarioMetrics,
    ScenarioPcapRef,
    ScenarioRunTimeline,
    FailureAttribution,
)
from app.services.scenarios.tracker import ScenarioRunTracker
from app.services.scenarios.models import ScenarioStage
from app.schemas.decision import DecisionValidation

logger = get_logger(__name__)

_SEVERITY_ORDER = ["low", "medium", "high", "critical"]
_SEVERITY_WEIGHTS = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _check(name: str, passed: bool, details: dict) -> ScenarioCheck:
    return ScenarioCheck.model_validate({"name": name, "pass": passed, "details": details})


class ScenariosService:
    """场景管理与执行服务（DOC B B4.10）。"""

    def __init__(self, db: Session):
        self.db = db

    def create_scenario(
        self,
        name: str,
        description: str,
        pcap_id: str,
        expectations: ScenarioExpectations,
        tags: list[str],
    ) -> ScenarioSchema:
        scenario_id = generate_uuid()
        now = utc_now()

        payload = {
            "expectations": expectations.model_dump(),
            "tags": tags,
        }

        model = Scenario(
            id=scenario_id,
            created_at=now,
            name=name,
            description=description,
            pcap_id=pcap_id,
            payload=json.dumps(payload),
        )
        self.db.add(model)
        self.db.commit()

        scenario = ScenarioSchema(
            version="1.1",
            id=scenario_id,
            created_at=datetime_to_iso(now),
            name=name,
            description=description,
            pcap_ref=ScenarioPcapRef(pcap_id=pcap_id),
            expectations=expectations,
            tags=tags,
        )

        logger.info(f"已创建场景 {scenario_id}: {name}")
        return scenario

    def list_scenarios(
        self,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
    ) -> list[ScenarioSchema]:
        q = self.db.query(Scenario)
        if not include_archived:
            q = q.filter(Scenario.status == "active")
        scenarios = q.order_by(Scenario.created_at.desc()).offset(offset).limit(limit).all()
        return [self._to_schema(s) for s in scenarios]

    def get_scenario(self, scenario_id: str) -> Scenario | None:
        return self.db.query(Scenario).filter(Scenario.id == scenario_id).first()

    def run_scenario(self, scenario: Scenario) -> ScenarioRunResultSchema:
        logger.info(f"正在执行场景 {scenario.id}: {scenario.name}")

        if scenario.status == "archived":
            raise HTTPException(status_code=409, detail="无法执行已归档的场景")

        run_id = generate_uuid()
        tracker = ScenarioRunTracker(scenario.id, run_id, self.db)
        self._publish_run_started(scenario, run_id)

        try:
            with tracker.stage(ScenarioStage.LOAD_SCENARIO) as stg:
                expectations, _tags = self._load_scenario(scenario, stg)

            with tracker.stage(ScenarioStage.LOAD_ALERTS) as stg:
                alerts = self._load_alerts(scenario, stg)

            with tracker.stage(ScenarioStage.CHECK_ALERT_VOLUME) as stg:
                checks_vol = self._check_alert_volume(alerts, expectations, stg)

            with tracker.stage(ScenarioStage.CHECK_REQUIRED_PATTERNS) as stg:
                checks_pat = self._check_required_patterns(alerts, expectations, stg)

            with tracker.stage(ScenarioStage.CHECK_EVIDENCE_CHAIN) as stg:
                checks_ev = self._check_evidence_chain(alerts, expectations, stg)

            decision_validation = None
            with tracker.stage(ScenarioStage.CHECK_DRY_RUN) as stg:
                checks_dr, decision_validation = self._check_dry_run(alerts, expectations, stg)

            with tracker.stage(ScenarioStage.CHECK_ENTITIES_AND_FEATURES) as stg:
                checks_ef = self._check_entities_and_features(alerts, expectations, stg)

            with tracker.stage(ScenarioStage.CHECK_PIPELINE_CONSTRAINTS) as stg:
                checks_pc, pipeline_latency_ms = self._check_pipeline_constraints(
                    scenario, expectations, stg
                )
                tracker.set_pipeline_latency(pipeline_latency_ms)

            with tracker.stage(ScenarioStage.SUMMARIZE_RESULT) as stg:
                metrics = self._summarize_result(alerts, stg)

        except Exception as exc:
            tracker.fail(str(exc))
            raise

        timeline_model = tracker.finish()

        # 延迟指标必须在 tracker.finish() 之后填入 metrics
        metrics.validation_latency_ms = timeline_model.validation_latency_ms
        metrics.pipeline_latency_ms = timeline_model.pipeline_latency_ms

        all_checks = checks_vol + checks_pat + checks_ev + checks_dr + checks_ef + checks_pc
        status = "pass" if all(c.pass_ for c in all_checks) else "fail"
        now = utc_now()

        timeline_schema = ScenarioRunTimeline(**timeline_model.model_dump())

        result = ScenarioRunResultSchema(
            version="1.1",
            id=run_id,
            created_at=datetime_to_iso(now),
            scenario_id=scenario.id,
            status=status,
            checks=all_checks,
            metrics=metrics,
            timeline=timeline_schema,
            decision_validation=decision_validation,
        )

        run_model = ScenarioRun(
            id=run_id,
            created_at=now,
            scenario_id=scenario.id,
            status=status,
            payload=result.model_dump_json(),
            stages_log=json.dumps([s.model_dump() for s in timeline_model.stages]),
            validation_latency_ms=timeline_model.validation_latency_ms,
            pipeline_latency_ms=timeline_model.pipeline_latency_ms,
        )
        self.db.add(run_model)
        self.db.commit()

        logger.info(f"场景运行 {run_id} 已完成: {status}")
        return result

    def archive_scenario(self, scenario_id: str) -> ScenarioSchema:
        scenario = self.get_scenario(scenario_id)
        if not scenario:
            raise HTTPException(status_code=404, detail=f"场景 {scenario_id} 不存在")
        if scenario.status == "archived":
            raise HTTPException(status_code=409, detail="场景已经是归档状态")
        scenario.status = "archived"
        self.db.commit()
        logger.info(f"已归档场景 {scenario_id}")
        return self._to_schema(scenario)

    def unarchive_scenario(self, scenario_id: str) -> ScenarioSchema:
        scenario = self.get_scenario(scenario_id)
        if not scenario:
            raise HTTPException(status_code=404, detail=f"场景 {scenario_id} 不存在")
        if scenario.status == "active":
            raise HTTPException(status_code=409, detail="场景已经是激活状态")
        scenario.status = "active"
        self.db.commit()
        logger.info(f"已恢复场景 {scenario_id}")
        return self._to_schema(scenario)

    def delete_scenario(self, scenario_id: str) -> None:
        scenario = self.get_scenario(scenario_id)
        if not scenario:
            raise HTTPException(status_code=404, detail=f"场景 {scenario_id} 不存在")
        # ScenarioRun 有 ondelete="CASCADE"，但显式删除更安全
        self.db.query(ScenarioRun).filter(ScenarioRun.scenario_id == scenario_id).delete()
        self.db.delete(scenario)
        self.db.commit()
        logger.info(f"已物理删除场景 {scenario_id}")

    def _publish_run_started(self, scenario: Scenario, run_id: str) -> None:
        try:
            import asyncio
            from app.core.events import get_event_bus
            from app.core.events.models import make_event, SCENARIO_RUN_STARTED
            from app.core.loop import get_main_loop
            from app.services.scenarios.models import TOTAL_STAGES

            event = make_event(SCENARIO_RUN_STARTED, {
                "scenario_id": scenario.id,
                "run_id": run_id,
                "scenario_name": scenario.name,
                "total_stages": TOTAL_STAGES,
            })
            loop = get_main_loop()
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(get_event_bus().publish(event), loop)
        except Exception:
            pass

    def _load_scenario(self, scenario: Scenario, stg) -> tuple[dict, list[str]]:
        payload = json.loads(scenario.payload) if isinstance(scenario.payload, str) else scenario.payload
        expectations = payload.get("expectations", {})
        tags = payload.get("tags", [])
        stg.record_metrics({"tag_count": len(tags)})
        stg.record_output({"expectations_keys": list(expectations.keys())})
        return expectations, tags

    def _load_alerts(self, scenario: Scenario, stg) -> list[Alert]:
        from app.models.flow import Flow
        from app.models.alert import alert_flows

        flows = self.db.query(Flow).filter(Flow.pcap_id == scenario.pcap_id).all()
        flow_ids = [f.id for f in flows]
        stg.record_metrics({"flow_count": len(flow_ids)})

        alerts: list[Alert] = []
        if flow_ids:
            alerts = self.db.query(Alert).join(
                alert_flows, Alert.id == alert_flows.c.alert_id
            ).filter(alert_flows.c.flow_id.in_(flow_ids)).distinct().all()

        stg.record_metrics({"alert_count": len(alerts)})
        stg.record_output({"alert_ids": [a.id for a in alerts[:10]]})
        return alerts

    def _check_alert_volume(
        self, alerts: list[Alert], expectations: dict, stg
    ) -> list[ScenarioCheck]:
        checks: list[ScenarioCheck] = []
        actual = len(alerts)

        min_alerts = expectations.get("min_alerts", 0)
        if min_alerts > 0:
            passed = actual >= min_alerts
            checks.append(_check("min_alerts", passed, {"expected_min": min_alerts, "actual": actual}))
            if not passed:
                stg.record_failure_attribution(FailureAttribution(
                    check_name="min_alerts",
                    expected=min_alerts,
                    actual=actual,
                    category="assertion_failed",
                ))

        max_alerts = expectations.get("max_alerts")
        if max_alerts is not None:
            passed = actual <= max_alerts
            checks.append(_check("max_alerts", passed, {"expected_max": max_alerts, "actual": actual}))
            if not passed:
                stg.record_failure_attribution(FailureAttribution(
                    check_name="max_alerts",
                    expected=max_alerts,
                    actual=actual,
                    category="assertion_failed",
                ))

        exact = expectations.get("exact_alerts")
        if exact is not None:
            passed = actual == exact
            checks.append(_check("exact_alerts", passed, {"expected": exact, "actual": actual}))
            if not passed:
                stg.record_failure_attribution(FailureAttribution(
                    check_name="exact_alerts",
                    expected=exact,
                    actual=actual,
                    category="assertion_failed",
                ))

        min_high = expectations.get("min_high_severity_count", 0)
        high_count = sum(1 for a in alerts if a.severity in ("high", "critical"))
        if min_high > 0:
            passed = high_count >= min_high
            checks.append(_check(
                "min_high_severity_count", passed,
                {"expected_min": min_high, "actual": high_count},
            ))
            if not passed:
                stg.record_failure_attribution(FailureAttribution(
                    check_name="min_high_severity_count",
                    expected=min_high,
                    actual=high_count,
                    category="assertion_failed",
                ))

        stg.record_metrics({"checks_count": len(checks), "passed": sum(c.pass_ for c in checks)})
        return checks

    def _check_required_patterns(
        self, alerts: list[Alert], expectations: dict, stg
    ) -> list[ScenarioCheck]:
        checks: list[ScenarioCheck] = []

        for must in expectations.get("must_have", []):
            must_type = must.get("type", "")
            must_sev = must.get("severity_at_least", "low")
            min_idx = _SEVERITY_ORDER.index(must_sev) if must_sev in _SEVERITY_ORDER else 0

            matched_alert = None
            for alert in alerts:
                if alert.type != must_type:
                    continue
                idx = _SEVERITY_ORDER.index(alert.severity) if alert.severity in _SEVERITY_ORDER else 0
                if idx >= min_idx:
                    matched_alert = alert
                    break

            matched = matched_alert is not None
            checks.append(_check(
                f"must_have_{must_type}", matched,
                {
                    "type": must_type,
                    "severity_at_least": must_sev,
                    "matched": matched_alert.id if matched_alert else None,
                },
            ))
            if not matched:
                stg.record_failure_attribution(FailureAttribution(
                    check_name=f"must_have_{must_type}",
                    expected=f"{must_type} (severity >= {must_sev})",
                    actual="not found",
                    category="data_missing",
                ))

        for ftype in expectations.get("forbidden_types", []):
            found = any(a.type == ftype for a in alerts)
            checks.append(_check(
                f"forbidden_type_{ftype}", not found,
                {"type": ftype, "found": found},
            ))
            if found:
                stg.record_failure_attribution(FailureAttribution(
                    check_name=f"forbidden_type_{ftype}",
                    expected="not present",
                    actual="found",
                    category="assertion_failed",
                ))

        stg.record_metrics({"checks_count": len(checks), "passed": sum(c.pass_ for c in checks)})
        return checks

    def _check_evidence_chain(
        self, alerts: list[Alert], expectations: dict, stg
    ) -> list[ScenarioCheck]:
        checks: list[ScenarioCheck] = []
        required_nodes = expectations.get("evidence_chain_contains", [])

        if required_nodes and alerts:
            from app.services.evidence.service import EvidenceService
            evidence_service = EvidenceService(self.db)

            for required in required_nodes:
                found = False
                for alert in alerts:
                    chain = evidence_service.build_evidence_chain(alert)
                    if any(n.id == required or required in n.id for n in chain.nodes):
                        found = True
                        break

                checks.append(_check(
                    f"evidence_contains_{required}", found,
                    {"node": required, "found": found},
                ))
                if not found:
                    stg.record_failure_attribution(FailureAttribution(
                        check_name=f"evidence_contains_{required}",
                        expected=required,
                        actual="not found in evidence chain",
                        category="data_missing",
                    ))

        stg.record_metrics({"checks_count": len(checks), "passed": sum(c.pass_ for c in checks)})
        return checks

    def _check_dry_run(
        self, alerts: list[Alert], expectations: dict, stg
    ) -> tuple[list[ScenarioCheck], DecisionValidation | None]:
        checks: list[ScenarioCheck] = []
        decision_validation: DecisionValidation | None = None

        if not expectations.get("dry_run_required", False):
            stg.record_metrics({"checks_count": 0, "passed": 0})
            return checks, decision_validation

        has_dry_run = False
        dry_run_risk = 0.0
        has_decision = False
        rollback_validated = False
        notes: list[str] = []

        for alert in alerts:
            twin_data = json.loads(alert.twin) if isinstance(alert.twin, str) else alert.twin
            if not twin_data.get("dry_run_id"):
                continue
            has_dry_run = True

            from app.models.twin import DryRun
            dry_run = self.db.query(DryRun).filter(DryRun.id == twin_data["dry_run_id"]).first()
            if dry_run:
                dr_payload = json.loads(dry_run.payload) if isinstance(dry_run.payload, str) else dry_run.payload
                dry_run_risk = dr_payload.get("impact", {}).get("service_disruption_risk", 0)

                decision_data = dr_payload.get("decision")
                if not decision_data:
                    notes.append("dry-run 未包含决策结果（旧版本）")
                else:
                    has_decision = True
                    notes.append("dry-run 包含三段式决策结果")

                    rollback = decision_data.get("rollback_plan", {})
                    if rollback.get("rollback_supported"):
                        rollback_validated = bool(rollback.get("rollback_steps"))
                        if rollback_validated:
                            notes.append(
                                f"回退计划已就绪，包含 {len(rollback['rollback_steps'])} 个步骤"
                            )
                        else:
                            notes.append("回退计划标记为可回退但缺少步骤")
                    else:
                        reason = rollback.get("not_supported_reason", "未知原因")
                        notes.append(f"动作不可逆: {reason}")

                    if decision_data.get("safer_alternative"):
                        notes.append("包含更安全替代方案")
            break

        checks.append(_check(
            "dry_run", has_dry_run,
            {"required": True, "found": has_dry_run, "risk": dry_run_risk},
        ))
        if not has_dry_run:
            stg.record_failure_attribution(FailureAttribution(
                check_name="dry_run",
                expected="dry-run present",
                actual="no dry-run found",
                category="data_missing",
            ))

        decision_validation = DecisionValidation(
            has_decision=has_decision,
            rollback_validated=rollback_validated,
            validation_notes=notes,
        )

        stg.record_metrics({"checks_count": len(checks), "passed": sum(c.pass_ for c in checks)})
        return checks, decision_validation

    def _check_entities_and_features(
        self, alerts: list[Alert], expectations: dict, stg
    ) -> list[ScenarioCheck]:
        checks: list[ScenarioCheck] = []

        for entity in expectations.get("required_entities", []):
            found = False
            for alert in alerts:
                if entity in (alert.primary_src_ip, alert.primary_dst_ip):
                    found = True
                    break
                evidence = json.loads(alert.evidence) if isinstance(alert.evidence, str) else alert.evidence
                if entity in str(evidence):
                    found = True
                    break
            checks.append(_check(
                f"required_entity_{entity}", found,
                {"entity": entity, "found": found},
            ))
            if not found:
                stg.record_failure_attribution(FailureAttribution(
                    check_name=f"required_entity_{entity}",
                    expected=entity,
                    actual="not found",
                    category="data_missing",
                ))

        for feature in expectations.get("required_feature_names", []):
            found = False
            for alert in alerts:
                for flow in alert.flows:
                    features = json.loads(flow.features) if isinstance(flow.features, str) else flow.features
                    if feature in features:
                        found = True
                        break
                if found:
                    break
            checks.append(_check(
                f"required_feature_{feature}", found,
                {"feature": feature, "found": found},
            ))
            if not found:
                stg.record_failure_attribution(FailureAttribution(
                    check_name=f"required_feature_{feature}",
                    expected=feature,
                    actual="not found",
                    category="data_missing",
                ))

        stg.record_metrics({"checks_count": len(checks), "passed": sum(c.pass_ for c in checks)})
        return checks

    def _check_pipeline_constraints(
        self, scenario: Scenario, expectations: dict, stg
    ) -> tuple[list[ScenarioCheck], float | None]:
        checks: list[ScenarioCheck] = []

        from app.models.pipeline import PipelineRunModel
        pipeline_run = self.db.query(PipelineRunModel).filter(
            PipelineRunModel.pcap_id == scenario.pcap_id
        ).order_by(PipelineRunModel.created_at.desc()).first()

        if pipeline_run is None:
            stg.record_metrics({"checks_count": 0, "passed": 0})
            return checks, None

        pipeline_latency_ms = pipeline_run.total_latency_ms
        stg.record_metrics({"pipeline_latency_ms": pipeline_latency_ms})

        max_latency = expectations.get("max_pipeline_latency_ms")
        if max_latency is not None:
            actual = pipeline_run.total_latency_ms or 0
            passed = actual <= max_latency
            checks.append(_check(
                "max_pipeline_latency_ms", passed,
                {"expected_max": max_latency, "actual": actual},
            ))
            if not passed:
                stg.record_failure_attribution(FailureAttribution(
                    check_name="max_pipeline_latency_ms",
                    expected=max_latency,
                    actual=actual,
                    category="assertion_failed",
                ))

        stages_log = (
            json.loads(pipeline_run.stages_log)
            if isinstance(pipeline_run.stages_log, str)
            else pipeline_run.stages_log
        )
        stage_names = [s["stage_name"] for s in stages_log] if stages_log else []

        for req_stage in expectations.get("required_pipeline_stages", []):
            found = req_stage in stage_names
            checks.append(_check(
                f"required_stage_{req_stage}", found,
                {"stage": req_stage, "found": found, "available": stage_names},
            ))
            if not found:
                stg.record_failure_attribution(FailureAttribution(
                    check_name=f"required_stage_{req_stage}",
                    expected=req_stage,
                    actual=f"missing (available: {stage_names})",
                    category="data_missing",
                ))

        if expectations.get("no_failed_stages", False):
            failed = [s["stage_name"] for s in stages_log if s.get("status") == "failed"] if stages_log else []
            passed = len(failed) == 0
            checks.append(_check(
                "no_failed_stages", passed, {"failed_stages": failed},
            ))
            if not passed:
                stg.record_failure_attribution(FailureAttribution(
                    check_name="no_failed_stages",
                    expected="no failures",
                    actual=f"failed: {failed}",
                    category="assertion_failed",
                ))

        stg.record_metrics({"checks_count": len(checks), "passed": sum(c.pass_ for c in checks)})
        return checks, pipeline_latency_ms

    def _summarize_result(self, alerts: list[Alert], stg) -> ScenarioMetrics:
        """延迟指标（validation_latency_ms / pipeline_latency_ms）在 tracker.finish() 后由调用方填入。"""
        high_count = sum(1 for a in alerts if a.severity in ("high", "critical"))

        # 加权平均 dry-run 风险：批量查询避免 N+1，按严重度加权
        dry_run_ids: list[str] = []
        weights: dict[str, int] = {}

        for alert in alerts:
            twin_data = json.loads(alert.twin) if isinstance(alert.twin, str) else alert.twin
            dr_id = twin_data.get("dry_run_id") if twin_data else None
            if dr_id:
                dry_run_ids.append(dr_id)
                weights[dr_id] = _SEVERITY_WEIGHTS.get(alert.severity, 1)

        weighted_risks: list[float] = []
        total_weight = 0
        if dry_run_ids:
            from app.models.twin import DryRun
            dry_runs = self.db.query(DryRun).filter(DryRun.id.in_(dry_run_ids)).all()

            for dry_run in dry_runs:
                dr_payload = json.loads(dry_run.payload) if isinstance(dry_run.payload, str) else dry_run.payload
                impact = dr_payload.get("impact", {})

                # 综合风险 = disruption_risk*0.7 + reachability_drop*0.3
                disruption = impact.get("service_disruption_risk", 0)
                reachability = impact.get("reachability_drop", 0)
                composite = disruption * 0.7 + reachability * 0.3

                w = weights.get(dry_run.id, 1)
                weighted_risks.append(composite * w)
                total_weight += w

        avg_risk = sum(weighted_risks) / total_weight if total_weight > 0 else 0.0

        metrics = ScenarioMetrics(
            alert_count=len(alerts),
            high_severity_count=high_count,
            avg_dry_run_risk=round(avg_risk, 3),
            validation_latency_ms=None,
            pipeline_latency_ms=None,
        )
        stg.record_metrics(metrics.model_dump())
        return metrics

    def _to_schema(self, model: Scenario) -> ScenarioSchema:
        payload = json.loads(model.payload) if isinstance(model.payload, str) else model.payload

        return ScenarioSchema(
            version=model.version,
            id=model.id,
            created_at=datetime_to_iso(model.created_at),
            name=model.name,
            description=model.description,
            status=model.status or "active",
            pcap_ref=ScenarioPcapRef(pcap_id=model.pcap_id),
            expectations=ScenarioExpectations(**payload.get("expectations", {})),
            tags=payload.get("tags", []),
        )

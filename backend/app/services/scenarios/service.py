"""
场景服务。
负责 Scenario 的增删改查与执行。
"""

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


class ScenariosService:
    """
用于场景管理与执行的服务。

遵循 DOC B B4.10 规范。
"""

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
        """
        创建新场景。

        参数：
            name: 场景名称（唯一）
            description: 场景描述
            pcap_id: 关联的 PCAP ID
            expectations: 期望结果
            tags: 分类标签

        返回：
            场景 Schema
        """
        scenario_id = generate_uuid()
        now = utc_now()
        
        # 构建包含 expectations 与 tags 的 payload
        payload = {
            "expectations": expectations.model_dump(),
            "tags": tags,
        }
        
        # 创建数据库记录
        scenario_model = Scenario(
            id=scenario_id,
            created_at=now,
            name=name,
            description=description,
            pcap_id=pcap_id,
            payload=json.dumps(payload),
        )
        self.db.add(scenario_model)
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
        
        logger.info(f"Created scenario {scenario_id}: {name}")
        return scenario

    def list_scenarios(
        self,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
    ) -> list[ScenarioSchema]:
        """列出场景。默认只返回 active 场景。"""
        q = self.db.query(Scenario)
        if not include_archived:
            q = q.filter(Scenario.status == "active")
        scenarios = q.order_by(Scenario.created_at.desc()).offset(offset).limit(limit).all()
        return [self._model_to_schema(s) for s in scenarios]

    def get_scenario(self, scenario_id: str) -> Scenario | None:
        """根据 ID 获取场景。"""
        return self.db.query(Scenario).filter(Scenario.id == scenario_id).first()

    def run_scenario(self, scenario: Scenario) -> ScenarioRunResultSchema:
        """
        执行场景并校验期望结果（重构为 9 阶段实时流）。

        参数：
            scenario: 场景模型

        返回：
            ScenarioRunResult Schema（含 timeline）
        """
        logger.info(f"Running scenario {scenario.id}: {scenario.name}")

        if scenario.status == "archived":
            raise HTTPException(status_code=409, detail="Cannot run an archived scenario")

        run_id = generate_uuid()
        tracker = ScenarioRunTracker(scenario.id, run_id, self.db)
        self._publish_run_started(scenario, run_id)

        try:
            # 阶段 1: 加载场景配置
            with tracker.stage(ScenarioStage.LOAD_SCENARIO) as stg:
                expectations, tags = self._stage_load_scenario(scenario, stg)

            # 阶段 2: 加载告警数据
            with tracker.stage(ScenarioStage.LOAD_ALERTS) as stg:
                alerts = self._stage_load_alerts(scenario, stg)

            # 阶段 3: 检查告警数量
            checks_vol = []
            with tracker.stage(ScenarioStage.CHECK_ALERT_VOLUME) as stg:
                checks_vol = self._stage_check_alert_volume(alerts, expectations, stg)

            # 阶段 4: 检查必需模式
            checks_pat = []
            with tracker.stage(ScenarioStage.CHECK_REQUIRED_PATTERNS) as stg:
                checks_pat = self._stage_check_required_patterns(alerts, expectations, stg)

            # 阶段 5: 检查证据链
            checks_ev = []
            with tracker.stage(ScenarioStage.CHECK_EVIDENCE_CHAIN) as stg:
                checks_ev = self._stage_check_evidence_chain(alerts, expectations, stg)

            # 阶段 6: 检查 dry-run（含决策校验）
            checks_dr = []
            decision_validation = None
            with tracker.stage(ScenarioStage.CHECK_DRY_RUN) as stg:
                checks_dr, decision_validation = self._stage_check_dry_run(alerts, expectations, stg)

            # 阶段 7: 检查实体和特征
            checks_ef = []
            with tracker.stage(ScenarioStage.CHECK_ENTITIES_AND_FEATURES) as stg:
                checks_ef = self._stage_check_entities_and_features(alerts, expectations, stg)

            # 阶段 8: 检查 pipeline 约束
            checks_pc = []
            with tracker.stage(ScenarioStage.CHECK_PIPELINE_CONSTRAINTS) as stg:
                checks_pc, pipeline_latency_ms = self._stage_check_pipeline_constraints(
                    scenario, expectations, stg
                )
                tracker.set_pipeline_latency(pipeline_latency_ms)

            # 阶段 9: 汇总结果
            with tracker.stage(ScenarioStage.SUMMARIZE_RESULT) as stg:
                all_checks = checks_vol + checks_pat + checks_ev + checks_dr + checks_ef + checks_pc
                metrics = self._stage_summarize_result(alerts, stg)

        except Exception as exc:
            tracker.fail(str(exc))
            raise

        # 完成跟踪，获取时间线
        timeline_model = tracker.finish()

        # 更新 metrics 中的延迟指标（必须在 tracker.finish() 之后）
        metrics.validation_latency_ms = timeline_model.validation_latency_ms
        metrics.pipeline_latency_ms = timeline_model.pipeline_latency_ms

        # 构建最终结果
        all_checks = checks_vol + checks_pat + checks_ev + checks_dr + checks_ef + checks_pc
        all_pass = all(c.pass_ for c in all_checks)
        status = "pass" if all_pass else "fail"
        now = utc_now()

        # 将 models.ScenarioRunTimeline 转换为 schemas.ScenarioRunTimeline
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

        # 持久化到数据库
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

        logger.info(f"Scenario run {run_id} completed: {status}")
        return result

    # ── 私有阶段方法 ──────────────────────────────────────────────

    def _publish_run_started(self, scenario: Scenario, run_id: str) -> None:
        """发布 scenario.run.started 事件（fire-and-forget）。"""
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

    def _stage_load_scenario(self, scenario: Scenario, stg) -> tuple[dict, list[str]]:
        """阶段 1: 加载场景配置（expectations + tags）。"""
        payload = json.loads(scenario.payload) if isinstance(scenario.payload, str) else scenario.payload
        expectations = payload.get("expectations", {})
        tags = payload.get("tags", [])
        stg.record_metrics({"tag_count": len(tags)})
        stg.record_output({"expectations_keys": list(expectations.keys())})
        return expectations, tags

    def _stage_load_alerts(self, scenario: Scenario, stg) -> list[Alert]:
        """阶段 2: 加载该 PCAP 对应的所有告警。"""
        from app.models.flow import Flow
        from app.models.alert import alert_flows

        flows = self.db.query(Flow).filter(Flow.pcap_id == scenario.pcap_id).all()
        flow_ids = [f.id for f in flows]
        stg.record_metrics({"flow_count": len(flow_ids)})

        alerts = []
        if flow_ids:
            alerts = self.db.query(Alert).join(
                alert_flows,
                Alert.id == alert_flows.c.alert_id
            ).filter(
                alert_flows.c.flow_id.in_(flow_ids)
            ).distinct().all()

        stg.record_metrics({"alert_count": len(alerts)})
        stg.record_output({"alert_ids": [a.id for a in alerts[:10]]})  # 只记录前 10 个
        return alerts

    def _stage_check_alert_volume(
        self, alerts: list[Alert], expectations: dict, stg
    ) -> list[ScenarioCheck]:
        """阶段 3: 检查告警数量（min/max/exact + min_high_severity）。"""
        checks = []
        actual_alerts = len(alerts)

        # min_alerts
        min_alerts = expectations.get("min_alerts", 0)
        if min_alerts > 0:
            min_pass = actual_alerts >= min_alerts
            checks.append(ScenarioCheck.model_validate({
                "name": "min_alerts",
                "pass": min_pass,
                "details": {"expected_min": min_alerts, "actual": actual_alerts},
            }))
            if not min_pass:
                stg.record_failure_attribution(FailureAttribution(
                    check_name="min_alerts",
                    expected=min_alerts,
                    actual=actual_alerts,
                    category="assertion_failed",
                ))

        # max_alerts
        max_alerts = expectations.get("max_alerts")
        if max_alerts is not None:
            max_pass = actual_alerts <= max_alerts
            checks.append(ScenarioCheck.model_validate({
                "name": "max_alerts",
                "pass": max_pass,
                "details": {"expected_max": max_alerts, "actual": actual_alerts},
            }))
            if not max_pass:
                stg.record_failure_attribution(FailureAttribution(
                    check_name="max_alerts",
                    expected=max_alerts,
                    actual=actual_alerts,
                    category="assertion_failed",
                ))

        # exact_alerts
        exact_alerts = expectations.get("exact_alerts")
        if exact_alerts is not None:
            exact_pass = actual_alerts == exact_alerts
            checks.append(ScenarioCheck.model_validate({
                "name": "exact_alerts",
                "pass": exact_pass,
                "details": {"expected": exact_alerts, "actual": actual_alerts},
            }))
            if not exact_pass:
                stg.record_failure_attribution(FailureAttribution(
                    check_name="exact_alerts",
                    expected=exact_alerts,
                    actual=actual_alerts,
                    category="assertion_failed",
                ))

        # min_high_severity_count
        min_high = expectations.get("min_high_severity_count", 0)
        high_severity_count = sum(1 for a in alerts if a.severity in ["high", "critical"])
        if min_high > 0:
            high_pass = high_severity_count >= min_high
            checks.append(ScenarioCheck.model_validate({
                "name": "min_high_severity_count",
                "pass": high_pass,
                "details": {"expected_min": min_high, "actual": high_severity_count},
            }))
            if not high_pass:
                stg.record_failure_attribution(FailureAttribution(
                    check_name="min_high_severity_count",
                    expected=min_high,
                    actual=high_severity_count,
                    category="assertion_failed",
                ))

        stg.record_metrics({"checks_count": len(checks), "passed": sum(c.pass_ for c in checks)})
        return checks

    def _model_to_schema(self, model: Scenario) -> ScenarioSchema:
        """将 Scenario 模型转换为 Schema。"""
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

    def archive_scenario(self, scenario_id: str) -> ScenarioSchema:
        """将场景归档。已归档场景返回 409。"""
        scenario = self.get_scenario(scenario_id)
        if not scenario:
            raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")
        if scenario.status == "archived":
            raise HTTPException(status_code=409, detail="Scenario is already archived")
        scenario.status = "archived"
        self.db.commit()
        logger.info(f"Archived scenario {scenario_id}")
        return self._model_to_schema(scenario)

    def unarchive_scenario(self, scenario_id: str) -> ScenarioSchema:
        """恢复已归档场景。已激活场景返回 409。"""
        scenario = self.get_scenario(scenario_id)
        if not scenario:
            raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")
        if scenario.status == "active":
            raise HTTPException(status_code=409, detail="Scenario is already active")
        scenario.status = "active"
        self.db.commit()
        logger.info(f"Unarchived scenario {scenario_id}")
        return self._model_to_schema(scenario)

    def delete_scenario(self, scenario_id: str) -> None:
        """物理删除场景及其所有运行记录。"""
        scenario = self.get_scenario(scenario_id)
        if not scenario:
            raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")
        # ScenarioRun 有 ondelete="CASCADE"，但显式删除更安全
        self.db.query(ScenarioRun).filter(ScenarioRun.scenario_id == scenario_id).delete()
        self.db.delete(scenario)
        self.db.commit()
        logger.info(f"Hard-deleted scenario {scenario_id}")
    def _stage_check_required_patterns(
        self, alerts: list[Alert], expectations: dict, stg
    ) -> list[ScenarioCheck]:
        """阶段 4: 检查必需模式（must_have + forbidden_types）。"""
        checks = []
        severity_order = ["low", "medium", "high", "critical"]

        # must_have
        must_have = expectations.get("must_have", [])
        for must in must_have:
            must_type = must.get("type", "")
            must_severity = must.get("severity_at_least", "low")
            min_sev_idx = severity_order.index(must_severity) if must_severity in severity_order else 0

            matched = False
            matched_alert = None
            for alert in alerts:
                if alert.type == must_type:
                    alert_sev_idx = severity_order.index(alert.severity) if alert.severity in severity_order else 0
                    if alert_sev_idx >= min_sev_idx:
                        matched = True
                        matched_alert = alert
                        break

            checks.append(ScenarioCheck.model_validate({
                "name": f"must_have_{must_type}",
                "pass": matched,
                "details": {
                    "type": must_type,
                    "severity_at_least": must_severity,
                    "matched": matched_alert.id if matched_alert else None,
                },
            }))
            if not matched:
                stg.record_failure_attribution(FailureAttribution(
                    check_name=f"must_have_{must_type}",
                    expected=f"{must_type} (severity >= {must_severity})",
                    actual="not found",
                    category="data_missing",
                ))

        # forbidden_types
        forbidden = expectations.get("forbidden_types", [])
        for ftype in forbidden:
            found_forbidden = any(a.type == ftype for a in alerts)
            checks.append(ScenarioCheck.model_validate({
                "name": f"forbidden_type_{ftype}",
                "pass": not found_forbidden,
                "details": {"type": ftype, "found": found_forbidden},
            }))
            if found_forbidden:
                stg.record_failure_attribution(FailureAttribution(
                    check_name=f"forbidden_type_{ftype}",
                    expected="not present",
                    actual="found",
                    category="assertion_failed",
                ))

        stg.record_metrics({"checks_count": len(checks), "passed": sum(c.pass_ for c in checks)})
        return checks

    def _stage_check_evidence_chain(
        self, alerts: list[Alert], expectations: dict, stg
    ) -> list[ScenarioCheck]:
        """阶段 5: 检查证据链（evidence_chain_contains）。"""
        checks = []
        evidence_contains = expectations.get("evidence_chain_contains", [])

        if evidence_contains and alerts:
            from app.services.evidence.service import EvidenceService
            evidence_service = EvidenceService(self.db)

            for required_node in evidence_contains:
                found = False
                for alert in alerts:
                    chain = evidence_service.build_evidence_chain(alert)
                    if any(n.id == required_node or required_node in n.id for n in chain.nodes):
                        found = True
                        break

                checks.append(ScenarioCheck.model_validate({
                    "name": f"evidence_contains_{required_node}",
                    "pass": found,
                    "details": {"node": required_node, "found": found},
                }))
                if not found:
                    stg.record_failure_attribution(FailureAttribution(
                        check_name=f"evidence_contains_{required_node}",
                        expected=required_node,
                        actual="not found in evidence chain",
                        category="data_missing",
                    ))

        stg.record_metrics({"checks_count": len(checks), "passed": sum(c.pass_ for c in checks)})
        return checks

    def _stage_check_dry_run(
        self, alerts: list[Alert], expectations: dict, stg
    ) -> tuple[list[ScenarioCheck], DecisionValidation | None]:
        """阶段 6: 检查 dry-run 要求 + 决策校验。"""
        checks = []
        decision_validation = None
        dry_run_required = expectations.get("dry_run_required", False)

        if dry_run_required:
            has_dry_run = False
            dry_run_risk = 0.0
            has_decision = False
            rollback_validated = False
            validation_notes = []

            for alert in alerts:
                twin_data = json.loads(alert.twin) if isinstance(alert.twin, str) else alert.twin
                if twin_data.get("dry_run_id"):
                    has_dry_run = True

                    from app.models.twin import DryRun
                    dry_run = self.db.query(DryRun).filter(
                        DryRun.id == twin_data["dry_run_id"]
                    ).first()
                    if dry_run:
                        dr_payload = json.loads(dry_run.payload) if isinstance(dry_run.payload, str) else dry_run.payload
                        dry_run_risk = dr_payload.get("impact", {}).get("service_disruption_risk", 0)

                        # 校验决策结果
                        decision_data = dr_payload.get("decision")
                        if decision_data:
                            has_decision = True
                            validation_notes.append("dry-run 包含三段式决策结果")

                            # 校验回退计划
                            rollback = decision_data.get("rollback_plan", {})
                            if rollback.get("rollback_supported"):
                                rollback_validated = bool(rollback.get("rollback_steps"))
                                if rollback_validated:
                                    validation_notes.append(
                                        f"回退计划已就绪，包含 {len(rollback['rollback_steps'])} 个步骤"
                                    )
                                else:
                                    validation_notes.append("回退计划标记为可回退但缺少步骤")
                            else:
                                reason = rollback.get("not_supported_reason", "未知原因")
                                validation_notes.append(f"动作不可逆: {reason}")

                            # 校验替代方案
                            if decision_data.get("safer_alternative"):
                                validation_notes.append("包含更安全替代方案")
                        else:
                            validation_notes.append("dry-run 未包含决策结果（旧版本）")
                    break

            checks.append(ScenarioCheck.model_validate({
                "name": "dry_run",
                "pass": has_dry_run,
                "details": {"required": True, "found": has_dry_run, "risk": dry_run_risk},
            }))
            if not has_dry_run:
                stg.record_failure_attribution(FailureAttribution(
                    check_name="dry_run",
                    expected="dry-run present",
                    actual="no dry-run found",
                    category="data_missing",
                ))

            # 构建决策校验结果
            decision_validation = DecisionValidation(
                has_decision=has_decision,
                rollback_validated=rollback_validated,
                validation_notes=validation_notes,
            )

        stg.record_metrics({"checks_count": len(checks), "passed": sum(c.pass_ for c in checks)})
        return checks, decision_validation

    def _stage_check_entities_and_features(
        self, alerts: list[Alert], expectations: dict, stg
    ) -> list[ScenarioCheck]:
        """阶段 7: 检查实体和特征（required_entities + required_feature_names）。"""
        checks = []

        # required_entities
        required_entities = expectations.get("required_entities", [])
        for entity in required_entities:
            found = False
            for alert in alerts:
                if entity in [alert.primary_src_ip, alert.primary_dst_ip]:
                    found = True
                    break
                evidence = json.loads(alert.evidence) if isinstance(alert.evidence, str) else alert.evidence
                if entity in str(evidence):
                    found = True
                    break
            checks.append(ScenarioCheck.model_validate({
                "name": f"required_entity_{entity}",
                "pass": found,
                "details": {"entity": entity, "found": found},
            }))
            if not found:
                stg.record_failure_attribution(FailureAttribution(
                    check_name=f"required_entity_{entity}",
                    expected=entity,
                    actual="not found",
                    category="data_missing",
                ))

        # required_feature_names
        required_features = expectations.get("required_feature_names", [])
        for feature_name in required_features:
            found = False
            for alert in alerts:
                for flow in alert.flows:
                    features = json.loads(flow.features) if isinstance(flow.features, str) else flow.features
                    if feature_name in features:
                        found = True
                        break
                if found:
                    break
            checks.append(ScenarioCheck.model_validate({
                "name": f"required_feature_{feature_name}",
                "pass": found,
                "details": {"feature": feature_name, "found": found},
            }))
            if not found:
                stg.record_failure_attribution(FailureAttribution(
                    check_name=f"required_feature_{feature_name}",
                    expected=feature_name,
                    actual="not found",
                    category="data_missing",
                ))

        stg.record_metrics({"checks_count": len(checks), "passed": sum(c.pass_ for c in checks)})
        return checks

    def _stage_check_pipeline_constraints(
        self, scenario: Scenario, expectations: dict, stg
    ) -> tuple[list[ScenarioCheck], float | None]:
        """阶段 8: 检查 pipeline 约束（max_latency + required_stages + no_failed_stages）。"""
        checks = []
        pipeline_latency_ms = None

        from app.models.pipeline import PipelineRunModel
        pipeline_run = self.db.query(PipelineRunModel).filter(
            PipelineRunModel.pcap_id == scenario.pcap_id
        ).order_by(PipelineRunModel.created_at.desc()).first()

        if pipeline_run:
            pipeline_latency_ms = pipeline_run.total_latency_ms
            stg.record_metrics({"pipeline_latency_ms": pipeline_latency_ms})

            # max_pipeline_latency_ms
            max_latency = expectations.get("max_pipeline_latency_ms")
            if max_latency is not None:
                actual_latency = pipeline_run.total_latency_ms or 0
                latency_pass = actual_latency <= max_latency
                checks.append(ScenarioCheck.model_validate({
                    "name": "max_pipeline_latency_ms",
                    "pass": latency_pass,
                    "details": {"expected_max": max_latency, "actual": actual_latency},
                }))
                if not latency_pass:
                    stg.record_failure_attribution(FailureAttribution(
                        check_name="max_pipeline_latency_ms",
                        expected=max_latency,
                        actual=actual_latency,
                        category="assertion_failed",
                    ))

            # required_pipeline_stages
            required_stages = expectations.get("required_pipeline_stages", [])
            stages_log = json.loads(pipeline_run.stages_log) if isinstance(pipeline_run.stages_log, str) else pipeline_run.stages_log
            stage_names = [s["stage_name"] for s in stages_log] if stages_log else []
            for req_stage in required_stages:
                found = req_stage in stage_names
                checks.append(ScenarioCheck.model_validate({
                    "name": f"required_stage_{req_stage}",
                    "pass": found,
                    "details": {"stage": req_stage, "found": found, "available": stage_names},
                }))
                if not found:
                    stg.record_failure_attribution(FailureAttribution(
                        check_name=f"required_stage_{req_stage}",
                        expected=req_stage,
                        actual=f"missing (available: {stage_names})",
                        category="data_missing",
                    ))

            # no_failed_stages
            if expectations.get("no_failed_stages", False):
                failed_stages = [s["stage_name"] for s in stages_log if s.get("status") == "failed"] if stages_log else []
                no_fail_pass = len(failed_stages) == 0
                checks.append(ScenarioCheck.model_validate({
                    "name": "no_failed_stages",
                    "pass": no_fail_pass,
                    "details": {"failed_stages": failed_stages},
                }))
                if not no_fail_pass:
                    stg.record_failure_attribution(FailureAttribution(
                        check_name="no_failed_stages",
                        expected="no failures",
                        actual=f"failed: {failed_stages}",
                        category="assertion_failed",
                    ))

        stg.record_metrics({"checks_count": len(checks), "passed": sum(c.pass_ for c in checks)})
        return checks, pipeline_latency_ms

    def _stage_summarize_result(self, alerts: list[Alert], stg) -> ScenarioMetrics:
        """阶段 9: 汇总指标（alert_count + high_severity_count + avg_dry_run_risk）。

        注意：延迟指标（validation_latency_ms 和 pipeline_latency_ms）在此阶段尚未计算，
        将在 tracker.finish() 后由调用方更新到 metrics 中。
        """
        high_severity_count = sum(1 for a in alerts if a.severity in ["high", "critical"])

        # 计算加权平均 dry-run 风险（优化：批量查询 + 严重度加权）
        dry_run_ids = []
        alert_severities = {}  # dry_run_id -> severity_weight

        # 严重度权重映射
        severity_weights = {"critical": 4, "high": 3, "medium": 2, "low": 1}

        for alert in alerts:
            twin_data = json.loads(alert.twin) if isinstance(alert.twin, str) else alert.twin
            dry_run_id = twin_data.get("dry_run_id") if twin_data else None
            if dry_run_id:
                dry_run_ids.append(dry_run_id)
                alert_severities[dry_run_id] = severity_weights.get(alert.severity, 1)

        # 批量查询 DryRun（优化：避免 N+1 查询）
        weighted_risks = []
        total_weight = 0
        if dry_run_ids:
            from app.models.twin import DryRun
            dry_runs = self.db.query(DryRun).filter(DryRun.id.in_(dry_run_ids)).all()

            for dry_run in dry_runs:
                dr_payload = json.loads(dry_run.payload) if isinstance(dry_run.payload, str) else dry_run.payload
                impact = dr_payload.get("impact", {})

                # 综合风险评分：service_disruption_risk + reachability_drop（归一化）
                disruption_risk = impact.get("service_disruption_risk", 0)
                reachability_drop = impact.get("reachability_drop", 0)
                composite_risk = disruption_risk * 0.7 + reachability_drop * 0.3

                # 应用严重度权重
                weight = alert_severities.get(dry_run.id, 1)
                weighted_risks.append(composite_risk * weight)
                total_weight += weight

        avg_risk = sum(weighted_risks) / total_weight if total_weight > 0 else 0.0

        metrics = ScenarioMetrics(
            alert_count=len(alerts),
            high_severity_count=high_severity_count,
            avg_dry_run_risk=round(avg_risk, 3),
            # 延迟指标将在 tracker.finish() 后更新
            validation_latency_ms=None,
            pipeline_latency_ms=None,
        )
        stg.record_metrics(metrics.model_dump())
        return metrics

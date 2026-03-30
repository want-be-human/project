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
)

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
        执行场景并校验期望结果。

        参数：
            scenario: 场景模型

        返回：
            ScenarioRunResult Schema
        """
        logger.info(f"Running scenario {scenario.id}: {scenario.name}")

        if scenario.status == "archived":
            raise HTTPException(status_code=409, detail="Cannot run an archived scenario")
        
        # 解析 expectations
        payload = json.loads(scenario.payload) if isinstance(scenario.payload, str) else scenario.payload
        expectations = payload.get("expectations", {})
        
        # 查询该 PCAP 对应的 alerts
        from app.models.flow import Flow
        from app.models.alert import alert_flows
        
        # 获取该 PCAP 的 flow ID 列表
        flows = self.db.query(Flow).filter(Flow.pcap_id == scenario.pcap_id).all()
        flow_ids = [f.id for f in flows]
        
        # 获取关联这些 flow 的 alerts
        alerts = []
        if flow_ids:
            alerts = self.db.query(Alert).join(
                alert_flows,
                Alert.id == alert_flows.c.alert_id
            ).filter(
                alert_flows.c.flow_id.in_(flow_ids)
            ).distinct().all()
        
        # 执行检查项
        checks = []
        all_pass = True
        actual_alerts = len(alerts)
        severity_order = ["low", "medium", "high", "critical"]

        # === 第一层：基础结果类检查 ===

        # 检查项：min_alerts
        min_alerts = expectations.get("min_alerts", 0)
        if min_alerts > 0:
            min_pass = actual_alerts >= min_alerts
            checks.append(ScenarioCheck.model_validate({
                "name": "min_alerts",
                "pass": min_pass,
                "details": {"expected_min": min_alerts, "actual": actual_alerts},
            }))
            all_pass = all_pass and min_pass

        # 检查项：max_alerts
        max_alerts = expectations.get("max_alerts")
        if max_alerts is not None:
            max_pass = actual_alerts <= max_alerts
            checks.append(ScenarioCheck.model_validate({
                "name": "max_alerts",
                "pass": max_pass,
                "details": {"expected_max": max_alerts, "actual": actual_alerts},
            }))
            all_pass = all_pass and max_pass

        # 检查项：exact_alerts（优先级高于 min/max）
        exact_alerts = expectations.get("exact_alerts")
        if exact_alerts is not None:
            exact_pass = actual_alerts == exact_alerts
            checks.append(ScenarioCheck.model_validate({
                "name": "exact_alerts",
                "pass": exact_pass,
                "details": {"expected": exact_alerts, "actual": actual_alerts},
            }))
            all_pass = all_pass and exact_pass

        # 检查项：min_high_severity_count
        min_high = expectations.get("min_high_severity_count", 0)
        high_severity_count = sum(1 for a in alerts if a.severity in ["high", "critical"])
        if min_high > 0:
            high_pass = high_severity_count >= min_high
            checks.append(ScenarioCheck.model_validate({
                "name": "min_high_severity_count",
                "pass": high_pass,
                "details": {"expected_min": min_high, "actual": high_severity_count},
            }))
            all_pass = all_pass and high_pass

        # === 第二层：模式匹配类检查 ===

        # 检查项：must_have
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
            all_pass = all_pass and matched

        # 检查项：forbidden_types
        forbidden = expectations.get("forbidden_types", [])
        for ftype in forbidden:
            found_forbidden = any(a.type == ftype for a in alerts)
            checks.append(ScenarioCheck.model_validate({
                "name": f"forbidden_type_{ftype}",
                "pass": not found_forbidden,
                "details": {"type": ftype, "found": found_forbidden},
            }))
            all_pass = all_pass and not found_forbidden

        # === 第三层：解释链与证据类检查 ===
        
        # === 第三层：解释链与证据类检查 ===

        # 检查项：evidence_chain_contains
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
                all_pass = all_pass and found

        # 检查项：required_entities（从 alert 的 primary_src_ip/dst_ip 或 evidence JSON 中提取）
        required_entities = expectations.get("required_entities", [])
        for entity in required_entities:
            found = False
            for alert in alerts:
                # 检查 IP 字段
                if entity in [alert.primary_src_ip, alert.primary_dst_ip]:
                    found = True
                    break
                # 检查 evidence JSON
                evidence = json.loads(alert.evidence) if isinstance(alert.evidence, str) else alert.evidence
                if entity in str(evidence):
                    found = True
                    break
            checks.append(ScenarioCheck.model_validate({
                "name": f"required_entity_{entity}",
                "pass": found,
                "details": {"entity": entity, "found": found},
            }))
            all_pass = all_pass and found

        # 检查项：required_feature_names（从 flow.features JSON 中提取）
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
            all_pass = all_pass and found

        # === 第四层：性能与稳定性类检查 ===
        
        # === 第四层：性能与稳定性类检查 ===

        # 查询 pipeline run 数据
        from app.models.pipeline import PipelineRunModel
        pipeline_run = self.db.query(PipelineRunModel).filter(
            PipelineRunModel.pcap_id == scenario.pcap_id
        ).order_by(PipelineRunModel.created_at.desc()).first()

        if pipeline_run:
            # 检查项：max_pipeline_latency_ms
            max_latency = expectations.get("max_pipeline_latency_ms")
            if max_latency is not None:
                actual_latency = pipeline_run.total_latency_ms or 0
                latency_pass = actual_latency <= max_latency
                checks.append(ScenarioCheck.model_validate({
                    "name": "max_pipeline_latency_ms",
                    "pass": latency_pass,
                    "details": {"expected_max": max_latency, "actual": actual_latency},
                }))
                all_pass = all_pass and latency_pass

            # 检查项：required_pipeline_stages
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
                all_pass = all_pass and found

            # 检查项：no_failed_stages
            if expectations.get("no_failed_stages", False):
                failed_stages = [s["stage_name"] for s in stages_log if s.get("status") == "failed"] if stages_log else []
                no_fail_pass = len(failed_stages) == 0
                checks.append(ScenarioCheck.model_validate({
                    "name": "no_failed_stages",
                    "pass": no_fail_pass,
                    "details": {"failed_stages": failed_stages},
                }))
                all_pass = all_pass and no_fail_pass

        # === 其他检查 ===

        # 检查项：dry_run_required
        dry_run_required = expectations.get("dry_run_required", False)
        if dry_run_required:
            # 检查是否存在带 dry-run 的 alert
            has_dry_run = False
            dry_run_risk = 0.0
            
            for alert in alerts:
                twin_data = json.loads(alert.twin) if isinstance(alert.twin, str) else alert.twin
                if twin_data.get("dry_run_id"):
                    has_dry_run = True
                    
                    # 获取 dry-run 风险
                    from app.models.twin import DryRun
                    dry_run = self.db.query(DryRun).filter(
                        DryRun.id == twin_data["dry_run_id"]
                    ).first()
                    if dry_run:
                        dr_payload = json.loads(dry_run.payload) if isinstance(dry_run.payload, str) else dry_run.payload
                        dry_run_risk = dr_payload.get("impact", {}).get("service_disruption_risk", 0)
                    break
            
            checks.append(ScenarioCheck.model_validate({
                "name": "dry_run",
                "pass": has_dry_run,
                "details": {"required": True, "found": has_dry_run, "risk": dry_run_risk},
            }))
            all_pass = all_pass and has_dry_run
        
        # 计算指标
        high_severity_count = sum(1 for a in alerts if a.severity in ["high", "critical"])
        
        # 计算平均 dry-run 风险
        dry_run_risks = []
        for alert in alerts:
            twin_data = json.loads(alert.twin) if isinstance(alert.twin, str) else alert.twin
            if twin_data.get("dry_run_id"):
                from app.models.twin import DryRun
                dry_run = self.db.query(DryRun).filter(DryRun.id == twin_data["dry_run_id"]).first()
                if dry_run:
                    dr_payload = json.loads(dry_run.payload) if isinstance(dry_run.payload, str) else dry_run.payload
                    dry_run_risks.append(dr_payload.get("impact", {}).get("service_disruption_risk", 0))
        
        avg_risk = sum(dry_run_risks) / len(dry_run_risks) if dry_run_risks else 0.0
        
        metrics = ScenarioMetrics(
            alert_count=actual_alerts,
            high_severity_count=high_severity_count,
            avg_dry_run_risk=round(avg_risk, 3),
        )
        
        # 创建运行结果
        run_id = generate_uuid()
        now = utc_now()
        status = "pass" if all_pass else "fail"
        
        result = ScenarioRunResultSchema(
            version="1.1",
            id=run_id,
            created_at=datetime_to_iso(now),
            scenario_id=scenario.id,
            status=status,
            checks=checks,
            metrics=metrics,
        )
        
        # 保存到数据库
        run_model = ScenarioRun(
            id=run_id,
            created_at=now,
            scenario_id=scenario.id,
            status=status,
            payload=result.model_dump_json(),
        )
        self.db.add(run_model)
        self.db.commit()
        
        logger.info(f"Scenario run {run_id} completed: {status}")
        return result

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

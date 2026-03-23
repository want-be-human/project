"""
场景服务。
负责 Scenario 的增删改查与执行。
"""

import json

from sqlalchemy.orm import Session

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
    ) -> list[ScenarioSchema]:
        """列出所有场景。"""
        scenarios = self.db.query(Scenario).order_by(
            Scenario.created_at.desc()
        ).offset(offset).limit(limit).all()
        
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
        
        # 检查项：min_alerts
        min_alerts = expectations.get("min_alerts", 0)
        actual_alerts = len(alerts)
        min_alerts_pass = actual_alerts >= min_alerts
        checks.append(ScenarioCheck.model_validate({
            "name": "min_alerts",
            "pass": min_alerts_pass,
            "details": {"expected": min_alerts, "actual": actual_alerts},
        }))
        all_pass = all_pass and min_alerts_pass
        
        # 检查项：must_have
        must_have = expectations.get("must_have", [])
        for must in must_have:
            must_type = must.get("type", "")
            must_severity = must.get("severity_at_least", "low")
            
            # 查找匹配告警
            severity_order = ["low", "medium", "high", "critical"]
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
            pcap_ref=ScenarioPcapRef(pcap_id=model.pcap_id),
            expectations=ScenarioExpectations(**payload.get("expectations", {})),
            tags=payload.get("tags", []),
        )

"""
Scenarios service.
Scenario CRUD and execution.
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
    Service for scenario management and execution.
    
    Follows DOC B B4.10 specification.
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
        Create a new scenario.
        
        Args:
            name: Scenario name (unique)
            description: Scenario description
            pcap_id: Reference PCAP ID
            expectations: Expected outcomes
            tags: Tags for categorization
            
        Returns:
            Scenario schema
        """
        scenario_id = generate_uuid()
        now = utc_now()
        
        # Build payload with expectations and tags
        payload = {
            "expectations": expectations.model_dump(),
            "tags": tags,
        }
        
        # Create database record
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
        """List all scenarios."""
        scenarios = self.db.query(Scenario).order_by(
            Scenario.created_at.desc()
        ).offset(offset).limit(limit).all()
        
        return [self._model_to_schema(s) for s in scenarios]

    def get_scenario(self, scenario_id: str) -> Scenario | None:
        """Get scenario by ID."""
        return self.db.query(Scenario).filter(Scenario.id == scenario_id).first()

    def run_scenario(self, scenario: Scenario) -> ScenarioRunResultSchema:
        """
        Execute a scenario and check expectations.
        
        Args:
            scenario: Scenario model
            
        Returns:
            ScenarioRunResult schema
        """
        logger.info(f"Running scenario {scenario.id}: {scenario.name}")
        
        # Parse expectations
        payload = json.loads(scenario.payload) if isinstance(scenario.payload, str) else scenario.payload
        expectations = payload.get("expectations", {})
        
        # Query alerts for this PCAP
        from app.models.flow import Flow
        from app.models.alert import alert_flows
        
        # Get flow IDs for this PCAP
        flows = self.db.query(Flow).filter(Flow.pcap_id == scenario.pcap_id).all()
        flow_ids = [f.id for f in flows]
        
        # Get alerts that have these flows
        alerts = []
        if flow_ids:
            alerts = self.db.query(Alert).join(
                alert_flows,
                Alert.id == alert_flows.c.alert_id
            ).filter(
                alert_flows.c.flow_id.in_(flow_ids)
            ).distinct().all()
        
        # Run checks
        checks = []
        all_pass = True
        
        # Check: min_alerts
        min_alerts = expectations.get("min_alerts", 0)
        actual_alerts = len(alerts)
        min_alerts_pass = actual_alerts >= min_alerts
        checks.append(ScenarioCheck.model_validate({
            "name": "min_alerts",
            "pass": min_alerts_pass,
            "details": {"expected": min_alerts, "actual": actual_alerts},
        }))
        all_pass = all_pass and min_alerts_pass
        
        # Check: must_have
        must_have = expectations.get("must_have", [])
        for must in must_have:
            must_type = must.get("type", "")
            must_severity = must.get("severity_at_least", "low")
            
            # Find matching alert
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
        
        # Check: evidence_chain_contains
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
        
        # Check: dry_run_required
        dry_run_required = expectations.get("dry_run_required", False)
        if dry_run_required:
            # Check if any alert has a dry-run
            has_dry_run = False
            dry_run_risk = 0.0
            
            for alert in alerts:
                twin_data = json.loads(alert.twin) if isinstance(alert.twin, str) else alert.twin
                if twin_data.get("dry_run_id"):
                    has_dry_run = True
                    
                    # Get dry-run risk
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
        
        # Calculate metrics
        high_severity_count = sum(1 for a in alerts if a.severity in ["high", "critical"])
        
        # Calculate average dry-run risk
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
        
        # Create run result
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
        
        # Save to database
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
        """Convert Scenario model to schema."""
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

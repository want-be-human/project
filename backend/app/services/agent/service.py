"""
Agent service.
Structured output for triage, investigation, and recommendation.
"""

import json

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.utils import generate_uuid, utc_now, datetime_to_iso
from app.models.alert import Alert
from app.models.investigation import Investigation
from app.models.recommendation import Recommendation
from app.schemas.agent import (
    InvestigationSchema,
    InvestigationImpact,
    RecommendationSchema,
    RecommendedAction,
)

logger = get_logger(__name__)


class AgentService:
    """
    Service for agent-based analysis.
    
    Follows DOC B B4.7 specification.
    Generates structured outputs without executing actions.
    """

    def __init__(self, db: Session):
        self.db = db

    def triage(self, alert: Alert, language: str = "en") -> str:
        """
        Generate short triage summary for alert.
        
        Args:
            alert: Alert model instance
            language: 'zh' for Chinese, 'en' for English
            
        Returns:
            Triage summary string
        """
        aggregation = json.loads(alert.aggregation) if isinstance(alert.aggregation, str) else alert.aggregation
        
        flow_count = aggregation.get("count_flows", 0)
        
        if language == "zh":
            summary = (
                f"检测到{alert.severity}级{self._type_to_zh(alert.type)}异常。"
                f"来源IP {alert.primary_src_ip} 在时间窗口内产生了 {flow_count} 条异常流量，"
                f"目标服务为 {alert.primary_proto}/{alert.primary_dst_port}。"
                f"建议进一步调查并考虑临时封禁措施。"
            )
        else:
            summary = (
                f"Detected {alert.severity} severity {alert.type} anomaly. "
                f"Source IP {alert.primary_src_ip} generated {flow_count} anomalous flows "
                f"targeting {alert.primary_proto}/{alert.primary_dst_port}. "
                f"Recommend investigation and consider temporary blocking."
            )
        
        # Update alert's triage summary
        agent_data = json.loads(alert.agent) if isinstance(alert.agent, str) else alert.agent
        agent_data["triage_summary"] = summary
        alert.agent = json.dumps(agent_data)
        self.db.commit()
        
        logger.info(f"Generated triage for alert {alert.id}")
        return summary

    def investigate(self, alert: Alert) -> InvestigationSchema:
        """
        Generate structured investigation for alert.
        
        Args:
            alert: Alert model instance
            
        Returns:
            Investigation schema
        """
        evidence = json.loads(alert.evidence) if isinstance(alert.evidence, str) else alert.evidence
        aggregation = json.loads(alert.aggregation) if isinstance(alert.aggregation, str) else alert.aggregation
        
        # Build hypothesis based on alert type
        hypothesis = self._build_hypothesis(alert)
        
        # Build reasoning
        why = self._build_why(alert, evidence, aggregation)
        
        # Assess impact
        impact = self._assess_impact(alert, evidence)
        
        # Suggest next steps
        next_steps = self._suggest_next_steps(alert)
        
        # Create investigation record
        inv_id = generate_uuid()
        now = utc_now()
        
        investigation = InvestigationSchema(
            version="1.1",
            id=inv_id,
            created_at=datetime_to_iso(now),
            alert_id=alert.id,
            hypothesis=hypothesis,
            why=why,
            impact=InvestigationImpact(
                scope=impact["scope"],
                confidence=impact["confidence"],
            ),
            next_steps=next_steps,
            safety_note="Advisory only; no actions executed.",
        )
        
        # Save to database
        inv_model = Investigation(
            id=inv_id,
            created_at=now,
            alert_id=alert.id,
            payload=investigation.model_dump_json(),
        )
        self.db.add(inv_model)
        
        # Update alert's agent field
        agent_data = json.loads(alert.agent) if isinstance(alert.agent, str) else alert.agent
        agent_data["investigation_id"] = inv_id
        alert.agent = json.dumps(agent_data)
        
        self.db.commit()
        
        logger.info(f"Generated investigation {inv_id} for alert {alert.id}")
        return investigation

    def recommend(self, alert: Alert) -> RecommendationSchema:
        """
        Generate action recommendations for alert.
        
        Args:
            alert: Alert model instance
            
        Returns:
            Recommendation schema
        """
        # Build actions based on alert type and severity
        actions = self._build_actions(alert)
        
        # Create recommendation record
        rec_id = generate_uuid()
        now = utc_now()
        
        recommendation = RecommendationSchema(
            version="1.1",
            id=rec_id,
            created_at=datetime_to_iso(now),
            alert_id=alert.id,
            actions=actions,
        )
        
        # Save to database
        rec_model = Recommendation(
            id=rec_id,
            created_at=now,
            alert_id=alert.id,
            payload=recommendation.model_dump_json(),
        )
        self.db.add(rec_model)
        
        # Update alert's agent field
        agent_data = json.loads(alert.agent) if isinstance(alert.agent, str) else alert.agent
        agent_data["recommendation_id"] = rec_id
        alert.agent = json.dumps(agent_data)
        
        self.db.commit()
        
        logger.info(f"Generated recommendation {rec_id} for alert {alert.id}")
        return recommendation

    def _type_to_zh(self, alert_type: str) -> str:
        """Translate alert type to Chinese."""
        mapping = {
            "anomaly": "异常",
            "scan": "扫描",
            "dos": "拒绝服务",
            "bruteforce": "暴力破解",
            "exfil": "数据外泄",
            "unknown": "未知",
        }
        return mapping.get(alert_type, alert_type)

    def _build_hypothesis(self, alert: Alert) -> str:
        """Build investigation hypothesis."""
        hypotheses = {
            "scan": f"Possible port scanning or network reconnaissance from {alert.primary_src_ip}",
            "bruteforce": f"Possible brute-force attack targeting {alert.primary_proto}/{alert.primary_dst_port}",
            "dos": f"Possible denial-of-service attack against {alert.primary_dst_ip}",
            "exfil": f"Possible data exfiltration from {alert.primary_src_ip}",
            "anomaly": f"Anomalous network behavior detected from {alert.primary_src_ip}",
        }
        return hypotheses.get(alert.type, hypotheses["anomaly"])

    def _build_why(self, alert: Alert, evidence: dict, aggregation: dict) -> list[str]:
        """Build reasoning for hypothesis."""
        reasons = []
        
        flow_count = aggregation.get("count_flows", 0)
        reasons.append(f"Detected {flow_count} anomalous flows in aggregation window")
        
        top_features = evidence.get("top_features", [])
        for feature in top_features[:3]:
            reasons.append(
                f"Feature '{feature['name']}' shows {feature['direction']} value: {feature['value']}"
            )
        
        reasons.append(f"Alert severity assessed as {alert.severity} based on anomaly scores")
        
        return reasons

    def _assess_impact(self, alert: Alert, evidence: dict) -> dict:
        """Assess impact scope and confidence."""
        scope = [
            f"dst_ip:{alert.primary_dst_ip}",
            f"service:{alert.primary_proto}/{alert.primary_dst_port}",
        ]
        
        # Confidence based on flow count and severity
        flow_count = len(evidence.get("flow_ids", []))
        
        if alert.severity == "critical":
            base_confidence = 0.9
        elif alert.severity == "high":
            base_confidence = 0.8
        elif alert.severity == "medium":
            base_confidence = 0.65
        else:
            base_confidence = 0.5
        
        # Adjust for flow count
        confidence = min(base_confidence + (flow_count * 0.01), 0.95)
        
        return {"scope": scope, "confidence": round(confidence, 2)}

    def _suggest_next_steps(self, alert: Alert) -> list[str]:
        """Suggest investigation next steps."""
        steps = [
            f"Review detailed flow records for {alert.primary_src_ip}",
            "Check if source IP is known/internal or external",
            "Verify if target service requires this traffic pattern",
        ]
        
        if alert.type in ["scan", "bruteforce"]:
            steps.append("Consider temporary blocking of source IP")
            steps.append("Review firewall logs for similar patterns")
        
        if alert.type == "dos":
            steps.append("Check target service availability")
            steps.append("Consider rate limiting")
        
        return steps

    def _build_actions(self, alert: Alert) -> list[RecommendedAction]:
        """Build recommended actions based on alert."""
        actions = []
        
        # Primary action based on type
        if alert.type in ["scan", "bruteforce"]:
            actions.append(RecommendedAction(
                title=f"Temporary block source IP {alert.primary_src_ip}",
                priority="high" if alert.severity in ["critical", "high"] else "medium",
                steps=[
                    f"Add firewall rule to block {alert.primary_src_ip}",
                    "Set expiration time (recommended: 24 hours)",
                    "Monitor for continued attempts from related IPs",
                ],
                rollback=[
                    f"Remove firewall rule blocking {alert.primary_src_ip}",
                    "Verify legitimate traffic is restored",
                ],
                risk="May block legitimate traffic if IP is shared/NAT",
            ))
        
        if alert.type == "dos":
            actions.append(RecommendedAction(
                title=f"Rate limit traffic to {alert.primary_proto}/{alert.primary_dst_port}",
                priority="high",
                steps=[
                    "Configure rate limiting for the target service",
                    "Set threshold based on normal traffic patterns",
                    "Enable alerting for threshold breaches",
                ],
                rollback=[
                    "Remove rate limiting rules",
                    "Restore normal service limits",
                ],
                risk="May impact legitimate high-volume users",
            ))
        
        # General monitoring action
        actions.append(RecommendedAction(
            title="Enhance monitoring for related entities",
            priority="medium",
            steps=[
                f"Add {alert.primary_src_ip} to watchlist",
                "Enable detailed logging for affected services",
                "Set up alerts for similar patterns",
            ],
            rollback=[
                "Remove from watchlist after investigation",
                "Reset logging to normal levels",
            ],
            risk="Increased log storage and processing",
        ))
        
        return actions

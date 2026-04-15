import json

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.scoring_policy import (
    SERVICE_IMPORTANCE,
    SERVICE_IMPORTANCE_DEFAULT,
    DISRUPTION_RISK_WEIGHTS,
    ALERT_SEVERITY_RISK,
    IMPACT_CONFIDENCE_BASE,
    IMPACT_CONFIDENCE_CAP,
)
from app.models.alert import Alert
from app.models.twin import DryRun
from app.schemas.topology import GraphResponseSchema
from app.schemas.twin import (
    ImpactedServiceDetail,
    ServiceRiskBreakdown,
)

logger = get_logger(__name__)


class RiskScorer:
    def __init__(self, db: Session):
        self.db = db

    def score(
        self,
        graph_before: GraphResponseSchema,
        graph_after: GraphResponseSchema,
        impact_data: dict,
        alert_id: str,
    ) -> tuple[ServiceRiskBreakdown, list[ImpactedServiceDetail], float]:
        removed_nodes = impact_data.get("removed_nodes", set())
        removed_edges = impact_data.get("removed_edges", set())
        affected = impact_data.get("affected_services", set())

        nodes_before = len(graph_before.nodes)
        edges_before = len(graph_before.edges)

        all_services = {
            f"{edge.proto}/{edge.dst_port}".lower() for edge in graph_before.edges
        }

        ws = self._svc_score(affected, all_services)
        ni = self._ratio_score(len(removed_nodes), nodes_before)
        ei = self._ratio_score(len(removed_edges), edges_before)
        als = self._severity_score(alert_id)
        tp = self._traffic_score(removed_edges, graph_before.edges)
        hs = self._historical_score(alert_id)

        w = DISRUPTION_RISK_WEIGHTS
        composite = (
            w["weighted_service"] * ws
            + w["node_impact"] * ni
            + w["edge_impact"] * ei
            + w["alert_severity"] * als
            + w["traffic_proportion"] * tp
            + w["historical"] * hs
        )
        composite = round(min(composite, 1.0), 4)

        breakdown = ServiceRiskBreakdown(
            weighted_service_score=round(ws, 4),
            node_impact_score=round(ni, 4),
            edge_impact_score=round(ei, 4),
            alert_severity_score=round(als, 4),
            traffic_proportion_score=round(tp, 4),
            historical_score=round(hs, 4),
            composite_risk=composite,
        )

        impacted = self._svc_details(
            affected,
            removed_edges,
            graph_before,
            alert_id,
        )

        confidence = self._estimate_confidence(
            has_historical=(hs > 0),
            edge_count=edges_before,
        )

        return breakdown, impacted, confidence

    def _svc_score(
        self,
        affected: set[str],
        all_services: set[str],
    ) -> float:
        if not affected:
            return 0.0

        total = sum(
            SERVICE_IMPORTANCE.get(s.lower(), SERVICE_IMPORTANCE_DEFAULT)
            for s in affected
        )

        all_weight = sum(
            SERVICE_IMPORTANCE.get(s.lower(), SERVICE_IMPORTANCE_DEFAULT)
            for s in all_services
        ) if all_services else 1.0

        if all_weight == 0:
            return 0.0

        return min(total / all_weight, 1.0)

    @staticmethod
    def _ratio_score(removed: int, total: int) -> float:
        if total == 0:
            return 0.0
        return min(removed / total, 1.0)

    def _severity_score(self, alert_id: str) -> float:
        try:
            alert = self.db.query(Alert).filter(Alert.id == alert_id).first()
            if alert and hasattr(alert, "severity"):
                severity = getattr(alert, "severity", "medium")
                return ALERT_SEVERITY_RISK.get(severity, 0.5)
        except Exception:
            logger.debug(f"无法查询告警 {alert_id} 的严重等级，使用默认值")
        return 0.5

    @staticmethod
    def _traffic_score(
        removed_ids: set[str],
        all_edges: list,
    ) -> float:
        if not all_edges:
            return 0.0

        total = sum(getattr(e, "weight", 1) for e in all_edges)
        if total == 0:
            return 0.0

        affected = sum(
            getattr(e, "weight", 1)
            for e in all_edges
            if e.id in removed_ids
        )

        return min(affected / total, 1.0)

    def _historical_score(self, alert_id: str) -> float:
        try:
            runs = (
                self.db.query(DryRun)
                .filter(DryRun.alert_id == alert_id)
                .order_by(DryRun.created_at.desc())
                .limit(10)
                .all()
            )
            if not runs:
                return 0.0

            risks = []
            for run in runs:
                payload = json.loads(run.payload) if isinstance(run.payload, str) else run.payload
                impact = payload.get("impact", {})
                risks.append(impact.get("service_disruption_risk", 0.0))

            if not risks:
                return 0.0

            return min(sum(risks) / len(risks), 1.0)
        except Exception:
            logger.debug(f"无法查询告警 {alert_id} 的历史 dry-run 数据")
            return 0.0

    def _svc_details(
        self,
        affected: set[str],
        removed_ids: set[str],
        graph_before: GraphResponseSchema,
        alert_id: str,
    ) -> list[ImpactedServiceDetail]:
        if not affected:
            return []

        total_weight = sum(getattr(e, "weight", 1) for e in graph_before.edges) or 1

        severity = "medium"
        try:
            alert = self.db.query(Alert).filter(Alert.id == alert_id).first()
            if alert and hasattr(alert, "severity"):
                severity = getattr(alert, "severity", "medium")
        except Exception:
            pass

        details = []
        for svc in sorted(affected):
            svc_lower = svc.lower()
            importance = SERVICE_IMPORTANCE.get(svc_lower, SERVICE_IMPORTANCE_DEFAULT)

            svc_edges = []
            svc_nodes: set[str] = set()
            svc_weight = 0
            for edge in graph_before.edges:
                if f"{edge.proto}/{edge.dst_port}".lower() != svc_lower:
                    continue
                svc_weight += getattr(edge, "weight", 1)
                if edge.id not in removed_ids:
                    continue
                svc_edges.append(edge)
                svc_nodes.add(edge.source)
                svc_nodes.add(edge.target)

            traffic_prop = svc_weight / total_weight if total_weight > 0 else 0.0

            sev_stats: dict[str, int] = {}
            for edge in svc_edges:
                if edge.alert_ids:
                    sev_stats[severity] = sev_stats.get(severity, 0) + len(edge.alert_ids)

            details.append(ImpactedServiceDetail(
                service=svc,
                importance_weight=importance,
                affected_edge_count=len(svc_edges),
                affected_node_count=len(svc_nodes),
                traffic_proportion=round(traffic_prop, 4),
                alert_severity_stats=sev_stats,
                risk_contribution=round(importance * traffic_prop, 4),
            ))

        return details

    @staticmethod
    def _estimate_confidence(
        has_historical: bool,
        edge_count: int,
    ) -> float:
        confidence = IMPACT_CONFIDENCE_BASE

        if has_historical:
            confidence += 0.10

        if edge_count >= 50:
            confidence += 0.10
        elif edge_count >= 10:
            confidence += 0.05

        return round(min(confidence, IMPACT_CONFIDENCE_CAP), 2)

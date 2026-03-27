"""
数据驱动的服务中断风险评分器。
综合服务重要性、节点/边影响、告警严重度、流量占比、历史数据计算风险。

可扩展接口：
- 后续可引入 HistoricalStatsModel 替换 _calc_historical_score 的简单查询
- 可接入外部威胁情报源调整服务重要性权重
"""

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
    """
    数据驱动的服务中断风险评分器。

    每个子分数为 [0, 1] 浮点数，综合风险为按 DISRUPTION_RISK_WEIGHTS 加权求和。
    """

    def __init__(self, db: Session):
        self.db = db

    def score(
        self,
        graph_before: GraphResponseSchema,
        graph_after: GraphResponseSchema,
        impact_data: dict,
        alert_id: str,
    ) -> tuple[ServiceRiskBreakdown, list[ImpactedServiceDetail], float]:
        """
        计算综合风险。

        返回:
            (risk_breakdown, impacted_services_list, confidence)
        """
        removed_nodes = impact_data.get("removed_nodes", set())
        removed_edges = impact_data.get("removed_edges", set())
        affected_services = impact_data.get("affected_services", set())

        nodes_before = len(graph_before.nodes)
        edges_before = len(graph_before.edges)

        # 收集图中所有服务
        all_services = set()
        for edge in graph_before.edges:
            all_services.add(f"{edge.proto}/{edge.dst_port}".lower())

        # 计算各子分数
        ws = self._calc_weighted_service_score(affected_services, all_services)
        ni = self._calc_node_impact_score(len(removed_nodes), nodes_before)
        ei = self._calc_edge_impact_score(len(removed_edges), edges_before)
        als = self._calc_alert_severity_score(alert_id)
        tp = self._calc_traffic_proportion_score(
            removed_edges, graph_before.edges,
        )
        hs = self._calc_historical_score(alert_id)

        # 加权求和
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

        # 构建逐服务影响明细
        impacted_services = self._build_impacted_service_details(
            affected_services,
            removed_edges,
            graph_before,
            alert_id,
        )

        # 估算置信度
        confidence = self._estimate_confidence(
            has_historical=(hs > 0),
            edge_count=edges_before,
        )

        return breakdown, impacted_services, confidence

    # ── 子分数计算 ────────────────────────────────────────────

    def _calc_weighted_service_score(
        self,
        affected_services: set[str],
        all_services: set[str],
    ) -> float:
        """基于 SERVICE_IMPORTANCE 配置计算加权服务得分。"""
        if not affected_services:
            return 0.0

        # 受影响服务的加权重要性
        total_weight = 0.0
        for svc in affected_services:
            svc_lower = svc.lower()
            total_weight += SERVICE_IMPORTANCE.get(
                svc_lower, SERVICE_IMPORTANCE_DEFAULT,
            )

        # 归一化：除以所有服务的总权重
        all_weight = sum(
            SERVICE_IMPORTANCE.get(s.lower(), SERVICE_IMPORTANCE_DEFAULT)
            for s in all_services
        ) if all_services else 1.0

        if all_weight == 0:
            return 0.0

        return min(total_weight / all_weight, 1.0)

    def _calc_node_impact_score(
        self, removed_count: int, total_count: int,
    ) -> float:
        """节点影响得分 = 被移除节点数 / 总节点数。"""
        if total_count == 0:
            return 0.0
        return min(removed_count / total_count, 1.0)

    def _calc_edge_impact_score(
        self, removed_count: int, total_count: int,
    ) -> float:
        """边影响得分 = 被移除边数 / 总边数。"""
        if total_count == 0:
            return 0.0
        return min(removed_count / total_count, 1.0)

    def _calc_alert_severity_score(self, alert_id: str) -> float:
        """查询关联告警的严重等级，基于 ALERT_SEVERITY_RISK 加权。"""
        try:
            alert = self.db.query(Alert).filter(Alert.id == alert_id).first()
            if alert and hasattr(alert, "severity"):
                severity = getattr(alert, "severity", "medium")
                return ALERT_SEVERITY_RISK.get(severity, 0.5)
        except Exception:
            logger.debug(f"无法查询告警 {alert_id} 的严重等级，使用默认值")
        return 0.5

    def _calc_traffic_proportion_score(
        self,
        removed_edge_ids: set[str],
        all_edges: list,
    ) -> float:
        """基于边权重（流数量）计算受影响流量占比。"""
        if not all_edges:
            return 0.0

        total_weight = sum(getattr(e, "weight", 1) for e in all_edges)
        if total_weight == 0:
            return 0.0

        affected_weight = sum(
            getattr(e, "weight", 1)
            for e in all_edges
            if e.id in removed_edge_ids
        )

        return min(affected_weight / total_weight, 1.0)

    def _calc_historical_score(self, alert_id: str) -> float:
        """
        查询同 alert 的历史 dry-run 结果，计算历史风险趋势得分。
        如果有历史记录，取历史平均 service_disruption_risk 作为参考。
        """
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
                risk = impact.get("service_disruption_risk", 0.0)
                risks.append(risk)

            if not risks:
                return 0.0

            return min(sum(risks) / len(risks), 1.0)
        except Exception:
            logger.debug(f"无法查询告警 {alert_id} 的历史 dry-run 数据")
            return 0.0

    # ── 逐服务影响明细 ────────────────────────────────────────

    def _build_impacted_service_details(
        self,
        affected_services: set[str],
        removed_edge_ids: set[str],
        graph_before: GraphResponseSchema,
        alert_id: str,
    ) -> list[ImpactedServiceDetail]:
        """为每个受影响服务构建详细分解。"""
        if not affected_services:
            return []

        # 总流量权重
        total_weight = sum(getattr(e, "weight", 1) for e in graph_before.edges)
        if total_weight == 0:
            total_weight = 1

        # 查询告警严重等级
        alert_severity = "medium"
        try:
            alert = self.db.query(Alert).filter(Alert.id == alert_id).first()
            if alert and hasattr(alert, "severity"):
                alert_severity = getattr(alert, "severity", "medium")
        except Exception:
            pass

        details = []
        for svc in sorted(affected_services):
            svc_lower = svc.lower()
            importance = SERVICE_IMPORTANCE.get(svc_lower, SERVICE_IMPORTANCE_DEFAULT)

            # 统计该服务的受影响边和节点
            svc_edges = []
            svc_nodes = set()
            svc_weight = 0
            for edge in graph_before.edges:
                edge_svc = f"{edge.proto}/{edge.dst_port}".lower()
                if edge_svc == svc_lower:
                    svc_weight += getattr(edge, "weight", 1)
                    if edge.id in removed_edge_ids:
                        svc_edges.append(edge)
                        svc_nodes.add(edge.source)
                        svc_nodes.add(edge.target)

            traffic_prop = svc_weight / total_weight if total_weight > 0 else 0.0

            # 告警严重度统计（简化：关联到该服务的告警）
            severity_stats: dict[str, int] = {}
            for edge in svc_edges:
                if edge.alert_ids:
                    severity_stats[alert_severity] = severity_stats.get(
                        alert_severity, 0,
                    ) + len(edge.alert_ids)

            # 风险贡献 = 重要性 × 流量占比
            risk_contribution = round(importance * traffic_prop, 4)

            details.append(ImpactedServiceDetail(
                service=svc,
                importance_weight=importance,
                affected_edge_count=len(svc_edges),
                affected_node_count=len(svc_nodes),
                traffic_proportion=round(traffic_prop, 4),
                alert_severity_stats=severity_stats,
                risk_contribution=risk_contribution,
            ))

        return details

    # ── 置信度估算 ────────────────────────────────────────────

    def _estimate_confidence(
        self,
        has_historical: bool,
        edge_count: int,
    ) -> float:
        """
        基于数据充分度估算置信度。
        更多历史数据和更多边 → 更高置信度。
        """
        confidence = IMPACT_CONFIDENCE_BASE

        # 有历史数据加成
        if has_historical:
            confidence += 0.10

        # 边数量加成（更多边 = 更充分的拓扑信息）
        if edge_count >= 50:
            confidence += 0.10
        elif edge_count >= 10:
            confidence += 0.05

        return round(min(confidence, IMPACT_CONFIDENCE_CAP), 2)

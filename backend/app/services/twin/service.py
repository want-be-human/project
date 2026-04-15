import json
from collections import deque
from datetime import datetime
from typing import Literal

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.scoring_policy import SERVICE_IMPORTANCE, SERVICE_IMPORTANCE_DEFAULT
from app.core.utils import generate_uuid, utc_now, datetime_to_iso
from app.models.alert import Alert
from app.models.twin import TwinPlan, DryRun
from app.schemas.twin import (
    ActionPlanSchema,
    DryRunResultSchema,
    PlanAction,
    GraphHash,
    DryRunImpact,
    AlternativePath,
    ExplainSection,
)
from app.schemas.topology import GraphResponseSchema
from app.services.topology.service import TopologyService
from app.services.twin.reachability import ReachabilityAnalyzer
from app.services.twin.risk_scorer import RiskScorer
from app.services.decision.recommender import DecisionRecommender

logger = get_logger(__name__)

_ACTION_DESC = {
    "block_ip": "封锁 IP {target} 移除了该节点的所有出入边",
    "isolate_host": "隔离主机 {target} 移除了该节点及所有关联连接",
    "segment_subnet": "分段子网 {target} 阻断了跨网段边界流量",
    "rate_limit_service": "限流服务 {target} 可能影响高流量连接",
}


class TwinService:
    def __init__(self, db: Session):
        self.db = db
        self.topology_service = TopologyService(db)

    def create_plan(
        self,
        alert_id: str,
        actions: list[PlanAction],
        source: Literal["agent", "manual"],
        notes: str = "",
    ) -> ActionPlanSchema:
        plan_id = generate_uuid()
        now = utc_now()

        actions_json = json.dumps([a.model_dump() for a in actions])

        plan_model = TwinPlan(
            id=plan_id,
            created_at=now,
            alert_id=alert_id,
            source=source,
            actions=actions_json,
            notes=notes,
        )
        self.db.add(plan_model)

        alert = self.db.query(Alert).filter(Alert.id == alert_id).first()
        if alert:
            twin_data = json.loads(alert.twin) if isinstance(alert.twin, str) else alert.twin
            twin_data["plan_id"] = plan_id
            alert.twin = json.dumps(twin_data)

        self.db.commit()

        plan = ActionPlanSchema(
            version="1.1",
            id=plan_id,
            created_at=datetime_to_iso(now),
            alert_id=alert_id,
            source=source,
            actions=actions,
            notes=notes,
        )

        logger.info(f"Created plan {plan_id} for alert {alert_id}")
        return plan

    def dry_run(
        self,
        plan: TwinPlan,
        start: datetime,
        end: datetime,
        mode: Literal["ip", "subnet"] = "ip",
    ) -> DryRunResultSchema:
        logger.info(f"Running dry-run for plan {plan.id}")

        graph_before = self.topology_service.build_graph(start, end, mode)
        hash_before = self.topology_service.compute_graph_hash(graph_before)

        actions = json.loads(plan.actions) if isinstance(plan.actions, str) else plan.actions

        graph_after, impact_data = self._simulate(graph_before, actions)
        hash_after = self.topology_service.compute_graph_hash(graph_after)

        impact = self._calc_impact(
            graph_before, graph_after, impact_data, plan.alert_id,
        )

        alt_paths = self._find_alt_paths(
            graph_after,
            impact_data.get("blocked_sources", []),
        )

        explain, explain_sections = self._build_explain(actions, impact)

        dry_run_id = generate_uuid()
        now = utc_now()

        result = DryRunResultSchema(
            version="1.2",
            id=dry_run_id,
            created_at=datetime_to_iso(now),
            alert_id=plan.alert_id,
            plan_id=plan.id,
            before=GraphHash(graph_hash=hash_before),
            after=GraphHash(graph_hash=hash_after),
            graph_before=graph_before,
            graph_after=graph_after,
            dry_run_start=datetime_to_iso(start),
            dry_run_end=datetime_to_iso(end),
            dry_run_mode=mode,
            impact=DryRunImpact(
                impacted_nodes_count=impact["impacted_nodes"],
                impacted_edges_count=impact["impacted_edges"],
                reachability_drop=impact["reachability_drop"],
                service_disruption_risk=impact["service_risk"],
                affected_services=impact["affected_services"],
                warnings=impact["warnings"],
                removed_node_ids=impact["removed_node_ids"],
                removed_edge_ids=impact["removed_edge_ids"],
                affected_node_ids=impact["affected_node_ids"],
                affected_edge_ids=impact["affected_edge_ids"],
                reachability_detail=impact["reachability_detail"],
                impacted_services=impact["impacted_services"],
                service_risk_breakdown=impact["service_risk_breakdown"],
                confidence=impact["confidence"],
                node_risk_deltas=impact["node_risk_deltas"],
                edge_weight_deltas=impact["edge_weight_deltas"],
            ),
            alternative_paths=alt_paths,
            explain=explain,
            explain_sections=explain_sections,
        )

        # 决策推荐失败不影响主流程，result.decision 保持 None
        try:
            alert = self.db.query(Alert).filter(Alert.id == plan.alert_id).first()
            severity = getattr(alert, "severity", "medium") if alert else "medium"
            alert_type = getattr(alert, "type", "unknown") if alert else "unknown"

            decision = DecisionRecommender().recommend(
                alert_severity=severity,
                alert_type=alert_type,
                dry_run_result=result,
                plan_actions=actions,
            )
            result.decision = decision
        except Exception as e:
            logger.warning(f"决策推荐生成失败，跳过: {e}")

        dry_run_model = DryRun(
            id=dry_run_id,
            created_at=now,
            alert_id=plan.alert_id,
            plan_id=plan.id,
            payload=result.model_dump_json(),
        )
        self.db.add(dry_run_model)

        alert = self.db.query(Alert).filter(Alert.id == plan.alert_id).first()
        if alert:
            twin_data = json.loads(alert.twin) if isinstance(alert.twin, str) else alert.twin
            twin_data["dry_run_id"] = dry_run_id
            alert.twin = json.dumps(twin_data)

        self.db.commit()

        logger.info(f"Completed dry-run {dry_run_id}")
        return result

    def _simulate(
        self,
        graph: GraphResponseSchema,
        actions: list[dict],
    ) -> tuple[GraphResponseSchema, dict]:
        nodes = {n.id: n for n in graph.nodes}
        edges = list(graph.edges)

        impact_data = {
            "removed_nodes": set(),
            "removed_edges": set(),
            "blocked_sources": [],
            "affected_services": set(),
            "affected_nodes": set(),
            "affected_edges": set(),
        }

        for action in actions:
            action_type = action.get("action_type", "")
            target = action.get("target", {})
            target_value = target.get("value", "")

            if action_type == "block_ip":
                node_id = f"ip:{target_value}"
                impact_data["blocked_sources"].append(node_id)

                new_edges = []
                for edge in edges:
                    if edge.source == node_id or edge.target == node_id:
                        impact_data["removed_edges"].add(edge.id)
                        impact_data["affected_services"].add(
                            f"{edge.proto}/{edge.dst_port}",
                        )
                    else:
                        new_edges.append(edge)
                edges = new_edges

            elif action_type == "isolate_host":
                node_id = f"ip:{target_value}"
                impact_data["removed_nodes"].add(node_id)

                new_edges = []
                for edge in edges:
                    if edge.source == node_id or edge.target == node_id:
                        impact_data["removed_edges"].add(edge.id)
                    else:
                        new_edges.append(edge)
                edges = new_edges

                if node_id in nodes:
                    del nodes[node_id]

            elif action_type == "segment_subnet":
                subnet = target_value

                new_edges = []
                for edge in edges:
                    src_sub = self._ip_to_subnet(edge.source)
                    dst_sub = self._ip_to_subnet(edge.target)

                    if (src_sub == subnet and dst_sub != subnet) or \
                       (src_sub != subnet and dst_sub == subnet):
                        impact_data["removed_edges"].add(edge.id)
                    else:
                        new_edges.append(edge)
                edges = new_edges

            elif action_type == "rate_limit_service":
                parts = target_value.split("/")
                if len(parts) == 2:
                    proto, port = parts[0].upper(), int(parts[1])
                    for edge in edges:
                        if edge.proto == proto and edge.dst_port == port:
                            impact_data["affected_services"].add(f"{proto}/{port}")

        removed_nodes = impact_data["removed_nodes"]
        removed_edges = impact_data["removed_edges"]

        for edge in graph.edges:
            if edge.id in removed_edges:
                continue
            if edge.source not in removed_nodes and edge.target not in removed_nodes:
                continue
            impact_data["affected_edges"].add(edge.id)
            if edge.source not in removed_nodes:
                impact_data["affected_nodes"].add(edge.source)
            if edge.target not in removed_nodes:
                impact_data["affected_nodes"].add(edge.target)

        for edge in graph.edges:
            if edge.id not in removed_edges:
                continue
            if edge.source not in removed_nodes:
                impact_data["affected_nodes"].add(edge.source)
            if edge.target not in removed_nodes:
                impact_data["affected_nodes"].add(edge.target)

        modified = GraphResponseSchema(
            version=graph.version,
            nodes=list(nodes.values()),
            edges=edges,
            meta=graph.meta,
        )

        return modified, impact_data

    def _calc_impact(
        self,
        before: GraphResponseSchema,
        after: GraphResponseSchema,
        impact_data: dict,
        alert_id: str,
    ) -> dict:
        impacted_nodes = len(before.nodes) - len(after.nodes)
        impacted_edges = len(before.edges) - len(after.edges)

        reachability = ReachabilityAnalyzer(before, after).build_reachability_detail()

        breakdown, impacted_services, confidence = RiskScorer(self.db).score(
            before, after, impact_data, alert_id,
        )

        warnings = self._warnings(
            reachability, breakdown, impact_data, impacted_nodes,
        )

        return {
            "impacted_nodes": impacted_nodes,
            "impacted_edges": impacted_edges,
            "reachability_drop": reachability.pair_reachability_drop,
            "service_risk": breakdown.composite_risk,
            "affected_services": sorted(impact_data.get("affected_services", set())),
            "warnings": warnings,
            "removed_node_ids": sorted(impact_data.get("removed_nodes", set())),
            "removed_edge_ids": sorted(impact_data.get("removed_edges", set())),
            "affected_node_ids": sorted(impact_data.get("affected_nodes", set())),
            "affected_edge_ids": sorted(impact_data.get("affected_edges", set())),
            "reachability_detail": reachability,
            "impacted_services": impacted_services,
            "service_risk_breakdown": breakdown,
            "confidence": confidence,
            "node_risk_deltas": self._node_risk_deltas(before, after),
            "edge_weight_deltas": self._edge_weight_deltas(before, after),
        }

    @staticmethod
    def _node_risk_deltas(
        before: GraphResponseSchema, after: GraphResponseSchema,
    ) -> dict[str, float]:
        prev = {n.id: n.risk for n in before.nodes}
        deltas = {}
        for node in after.nodes:
            old = prev.get(node.id)
            if old is not None and node.risk != old:
                deltas[node.id] = node.risk
        return deltas

    @staticmethod
    def _edge_weight_deltas(
        before: GraphResponseSchema, after: GraphResponseSchema,
    ) -> dict[str, int]:
        prev = {e.id: e.weight for e in before.edges}
        deltas = {}
        for edge in after.edges:
            old = prev.get(edge.id)
            if old is not None and edge.weight != old:
                deltas[edge.id] = edge.weight
        return deltas

    def _warnings(
        self,
        reachability,
        breakdown,
        impact_data: dict,
        impacted_nodes: int,
    ) -> list[str]:
        warnings = []

        if impacted_nodes > 5:
            warnings.append(f"高影响: {impacted_nodes} 个节点将被隔离")

        affected = impact_data.get("affected_services", set())
        critical = sum(
            1 for s in affected
            if SERVICE_IMPORTANCE.get(s.lower(), 0) >= 0.8
        )
        if critical > 0:
            warnings.append(f"关键服务受影响: {critical} 个")

        if reachability.pair_reachability_drop > 0.2:
            warnings.append(
                f"源-目标对可达性显著下降: {reachability.pair_reachability_drop:.0%}",
            )

        if reachability.subnet_reachability_drop > 0.3:
            warnings.append(
                f"子网可达性显著下降: {reachability.subnet_reachability_drop:.0%}",
            )

        if breakdown.composite_risk > 0.7:
            warnings.append(
                f"综合风险评分较高: {breakdown.composite_risk:.2f}，建议谨慎执行",
            )

        return warnings

    def _find_alt_paths(
        self,
        graph: GraphResponseSchema,
        blocked_sources: list[str],
    ) -> list[AlternativePath]:
        if not blocked_sources or len(graph.nodes) < 3:
            return []

        adj: dict[str, list[str]] = {n.id: [] for n in graph.nodes}
        for edge in graph.edges:
            if edge.source in adj:
                adj[edge.source].append(edge.target)

        alt_paths = []
        for blocked in blocked_sources[:2]:
            targets = [n.id for n in graph.nodes if n.id != blocked]
            if not targets:
                continue

            path = self._bfs_path(adj, blocked, targets[0], set(blocked_sources))

            if path and len(path) > 2:
                alt_paths.append(AlternativePath.model_validate({
                    "from": blocked,
                    "to": targets[0],
                    "path": path,
                }))

        return alt_paths

    @staticmethod
    def _bfs_path(
        adj: dict,
        start: str,
        end: str,
        blocked: set,
    ) -> list[str]:
        if start not in adj or end not in adj:
            return []

        queue = deque([(start, [start])])
        visited = {start}

        while queue:
            current, path = queue.popleft()

            if current == end:
                return path

            for neighbor in adj.get(current, []):
                if neighbor in visited or neighbor in blocked:
                    continue
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))

        return []

    def _build_explain(
        self,
        actions: list[dict],
        impact: dict,
    ) -> tuple[list[str], list[ExplainSection]]:
        sections = [
            ExplainSection(
                section="affected_objects",
                title="受影响对象",
                content=self._explain_affected(impact),
            ),
            ExplainSection(
                section="impact_reason",
                title="影响原因",
                content=self._explain_reasons(actions),
            ),
            ExplainSection(
                section="metric_changes",
                title="指标变化",
                content=self._explain_metrics(impact),
            ),
            ExplainSection(
                section="risk_judgment",
                title="风险判断",
                content=self._explain_risk(impact),
            ),
            ExplainSection(
                section="recommended_actions",
                title="建议措施",
                content=self._explain_recommend(impact),
            ),
        ]

        legacy = []
        for s in sections:
            legacy.extend(s.content)

        return legacy, sections

    @staticmethod
    def _explain_affected(impact: dict) -> list[str]:
        lines = []

        removed_nodes = impact.get("removed_node_ids", [])
        removed_edges = impact.get("removed_edge_ids", [])
        affected_nodes = impact.get("affected_node_ids", [])
        affected_services = impact.get("affected_services", [])

        if removed_nodes:
            lines.append(f"被移除节点: {', '.join(removed_nodes)}")
        if removed_edges:
            svc_str = f"（涉及 {', '.join(affected_services)}）" if affected_services else ""
            lines.append(f"被移除边: {', '.join(removed_edges)}{svc_str}")
        if affected_nodes:
            lines.append(f"受波及邻居节点: {', '.join(affected_nodes)}")

        return lines

    @staticmethod
    def _explain_reasons(actions: list[dict]) -> list[str]:
        lines = []
        for action in actions:
            template = _ACTION_DESC.get(action.get("action_type", ""))
            if not template:
                continue
            lines.append(template.format(target=action.get("target", {}).get("value", "")))
        return lines

    @staticmethod
    def _explain_metrics(impact: dict) -> list[str]:
        rd = impact.get("reachability_detail")
        if not rd:
            return []

        lines = []
        if rd.pair_reachability_drop > 0:
            after_pct = (1 - rd.pair_reachability_drop) * 100
            lines.append(
                f"源-目标对可达性: 100% → {after_pct:.1f}%"
                f"（下降 {rd.pair_reachability_drop:.1%}）",
            )
        if rd.service_reachability_drop > 0:
            lines.append(f"服务可达性下降: {rd.service_reachability_drop:.1%}")
        if rd.subnet_reachability_drop > 0:
            lines.append(f"子网可达性下降: {rd.subnet_reachability_drop:.1%}")

        return lines

    @staticmethod
    def _explain_risk(impact: dict) -> list[str]:
        breakdown = impact.get("service_risk_breakdown")
        if not breakdown:
            return []

        confidence = impact.get("confidence", 0.5)
        risk = breakdown.composite_risk
        level = "低" if risk < 0.3 else "中" if risk < 0.7 else "高"

        lines = [f"综合风险评分 {risk:.2f}（{level}风险），置信度 {confidence:.2f}"]

        factors = []
        if breakdown.weighted_service_score > 0.5:
            factors.append(f"关键服务权重 ({breakdown.weighted_service_score:.2f})")
        if breakdown.alert_severity_score > 0.5:
            factors.append(f"告警严重度 ({breakdown.alert_severity_score:.2f})")
        if breakdown.edge_impact_score > 0.5:
            factors.append(f"边影响占比 ({breakdown.edge_impact_score:.2f})")
        if breakdown.traffic_proportion_score > 0.5:
            factors.append(f"流量占比 ({breakdown.traffic_proportion_score:.2f})")

        if factors:
            lines.append(f"主要风险因素: {', '.join(factors)}")

        if breakdown.historical_score == 0:
            lines.append("历史数据不足，置信度受限")

        return lines

    @staticmethod
    def _explain_recommend(impact: dict) -> list[str]:
        breakdown = impact.get("service_risk_breakdown")
        if not breakdown or breakdown.composite_risk <= 0.5:
            return []

        lines = ["建议在执行前验证替代访问路径可用性"]

        for svc in impact.get("affected_services", []):
            importance = SERVICE_IMPORTANCE.get(svc.lower(), SERVICE_IMPORTANCE_DEFAULT)
            if importance >= 0.8:
                lines.append(f"考虑对 {svc} 服务配置临时访问白名单")

        if breakdown.traffic_proportion_score > 0.5:
            lines.append("建议在低流量时段执行该操作以降低影响")

        return lines

    @staticmethod
    def _ip_to_subnet(node_id: str) -> str:
        if node_id.startswith("ip:"):
            parts = node_id[3:].split(".")
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
        elif node_id.startswith("subnet:"):
            return node_id[7:]
        return ""

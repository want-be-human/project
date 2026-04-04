"""
Twin service.
ActionPlan 与 DryRun 仿真。
v1.2: 数据驱动影响评估 — 多维可达性、风险分解、结构化解释。
"""

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


class TwinService:
    """
    数字孪生仿真服务（dry-run）。

    主线流程：构建图 → 模拟动作 → 计算影响 → 输出结果。
    v1.2 升级为数据驱动影响评估器。
    """

    def __init__(self, db: Session):
        self.db = db
        self.topology_service = TopologyService(db)

    # ══════════════════════════════════════════════════════════
    # ActionPlan
    # ══════════════════════════════════════════════════════════

    def create_plan(
        self,
        alert_id: str,
        actions: list[PlanAction],
        source: Literal["agent", "manual"],
        notes: str = "",
    ) -> ActionPlanSchema:
        """
        创建动作方案。

        Args:
            alert_id: 关联告警 ID
            actions: 动作列表
            source: 'agent' 或 'manual'
            notes: 备注
        """
        plan_id = generate_uuid()
        now = utc_now()

        # 序列化 actions
        actions_json = json.dumps([a.model_dump() for a in actions])

        # 创建数据库记录
        plan_model = TwinPlan(
            id=plan_id,
            created_at=now,
            alert_id=alert_id,
            source=source,
            actions=actions_json,
            notes=notes,
        )
        self.db.add(plan_model)

        # 更新 alert 的 twin 字段
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

    # ══════════════════════════════════════════════════════════
    # DryRun
    # ══════════════════════════════════════════════════════════

    def dry_run(
        self,
        plan: TwinPlan,
        start: datetime,
        end: datetime,
        mode: Literal["ip", "subnet"] = "ip",
    ) -> DryRunResultSchema:
        """
        执行 dry-run 仿真。

        Args:
            plan: TwinPlan 模型
            start: 时间窗口起始
            end: 时间窗口结束
            mode: 图模式 ('ip' 或 'subnet')
        """
        logger.info(f"Running dry-run for plan {plan.id}")

        # 1. 构建原始图
        graph_before = self.topology_service.build_graph(start, end, mode)
        hash_before = self.topology_service.compute_graph_hash(graph_before)

        # 2. 解析 actions
        actions = json.loads(plan.actions) if isinstance(plan.actions, str) else plan.actions

        # 3. 在图上模拟执行 actions
        graph_after, impact_data = self._simulate_actions(graph_before, actions)
        hash_after = self.topology_service.compute_graph_hash(graph_after)

        # 4. 数据驱动影响评估
        impact = self._calculate_impact(
            graph_before, graph_after, impact_data, plan.alert_id,
        )

        # 5. 查找可能绕行路径
        alt_paths = self._find_alternative_paths(
            graph_after,
            impact_data.get("blocked_sources", []),
        )

        # 6. 构建解释文本（兼容旧版 + 结构化）
        explain, explain_sections = self._build_explanation(actions, impact)

        # 7. 创建 dry-run 记录
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
                # 兼容旧字段
                impacted_nodes_count=impact["impacted_nodes"],
                impacted_edges_count=impact["impacted_edges"],
                reachability_drop=impact["reachability_drop"],
                service_disruption_risk=impact["service_risk"],
                affected_services=impact["affected_services"],
                warnings=impact["warnings"],
                # 新增字段
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

        # 8. 三段式决策推荐
        try:
            alert = self.db.query(Alert).filter(Alert.id == plan.alert_id).first()
            alert_severity = getattr(alert, "severity", "medium") if alert else "medium"
            alert_type = getattr(alert, "type", "unknown") if alert else "unknown"

            recommender = DecisionRecommender()
            decision = recommender.recommend(
                alert_severity=alert_severity,
                alert_type=alert_type,
                dry_run_result=result,
                plan_actions=actions,
            )
            result.decision = decision
        except Exception as e:
            logger.warning(f"决策推荐生成失败，跳过: {e}")
            # 决策推荐失败不影响主流程，result.decision 保持 None

        # 写入数据库
        dry_run_model = DryRun(
            id=dry_run_id,
            created_at=now,
            alert_id=plan.alert_id,
            plan_id=plan.id,
            payload=result.model_dump_json(),
        )
        self.db.add(dry_run_model)

        # 更新 alert 的 twin 字段
        alert = self.db.query(Alert).filter(Alert.id == plan.alert_id).first()
        if alert:
            twin_data = json.loads(alert.twin) if isinstance(alert.twin, str) else alert.twin
            twin_data["dry_run_id"] = dry_run_id
            alert.twin = json.dumps(twin_data)

        self.db.commit()

        logger.info(f"Completed dry-run {dry_run_id}")
        return result

    # ══════════════════════════════════════════════════════════
    # 动作模拟
    # ══════════════════════════════════════════════════════════

    def _simulate_actions(
        self,
        graph: GraphResponseSchema,
        actions: list[dict],
    ) -> tuple[GraphResponseSchema, dict]:
        """
        在图上模拟执行动作。

        返回修改后的图和影响数据。
        impact_data 包含：
        - removed_nodes: 被移除的节点 ID 集合
        - removed_edges: 被移除的边 ID 集合
        - blocked_sources: 被阻断的源节点列表
        - affected_services: 受影响的服务集合
        - affected_nodes: 受波及的邻居节点（未被移除但受影响）
        - affected_edges: 受波及的邻居边（未被移除但受影响）
        """
        # 复制图数据
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
                # 移除涉及该 IP 的边
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
                # 移除该主机相关的所有边和节点
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
                # 移除跨网段边界的边
                subnet = target_value

                new_edges = []
                for edge in edges:
                    src_subnet = self._ip_to_subnet_from_id(edge.source)
                    dst_subnet = self._ip_to_subnet_from_id(edge.target)

                    if (src_subnet == subnet and dst_subnet != subnet) or \
                       (src_subnet != subnet and dst_subnet == subnet):
                        impact_data["removed_edges"].add(edge.id)
                    else:
                        new_edges.append(edge)
                edges = new_edges

            elif action_type == "rate_limit_service":
                # 标记受影响的边（不删除，仅标记）
                proto_port = target_value.split("/")
                if len(proto_port) == 2:
                    proto, port = proto_port[0].upper(), int(proto_port[1])
                    for edge in edges:
                        if edge.proto == proto and edge.dst_port == port:
                            impact_data["affected_services"].add(f"{proto}/{port}")

        # 计算受波及的邻居节点和边（未被移除但与被移除对象相邻）
        removed_node_ids = impact_data["removed_nodes"]
        removed_edge_ids = impact_data["removed_edges"]

        for edge in graph.edges:
            if edge.id not in removed_edge_ids:
                # 边未被移除，但端点之一被移除或关联到被移除边的节点
                if edge.source in removed_node_ids or edge.target in removed_node_ids:
                    impact_data["affected_edges"].add(edge.id)
                    if edge.source not in removed_node_ids:
                        impact_data["affected_nodes"].add(edge.source)
                    if edge.target not in removed_node_ids:
                        impact_data["affected_nodes"].add(edge.target)

        # 被移除边的另一端节点也是受波及节点
        for edge in graph.edges:
            if edge.id in removed_edge_ids:
                if edge.source not in removed_node_ids:
                    impact_data["affected_nodes"].add(edge.source)
                if edge.target not in removed_node_ids:
                    impact_data["affected_nodes"].add(edge.target)

        # 创建修改后的图
        modified = GraphResponseSchema(
            version=graph.version,
            nodes=list(nodes.values()),
            edges=edges,
            meta=graph.meta,
        )

        return modified, impact_data

    # ══════════════════════════════════════════════════════════
    # 数据驱动影响评估
    # ══════════════════════════════════════════════════════════

    def _calculate_impact(
        self,
        before: GraphResponseSchema,
        after: GraphResponseSchema,
        impact_data: dict,
        alert_id: str,
    ) -> dict:
        """
        数据驱动影响评估（替代原有启发式计算）。

        编排 ReachabilityAnalyzer 和 RiskScorer 完成多维分析。
        """
        impacted_nodes = len(before.nodes) - len(after.nodes)
        impacted_edges = len(before.edges) - len(after.edges)

        # 1. 多维可达性分析
        analyzer = ReachabilityAnalyzer(before, after)
        reachability_detail = analyzer.build_reachability_detail()

        # 2. 数据驱动风险评分
        scorer = RiskScorer(self.db)
        risk_breakdown, impacted_services, confidence = scorer.score(
            before, after, impact_data, alert_id,
        )

        # 3. 生成告警提示
        warnings = self._generate_warnings(
            reachability_detail, risk_breakdown, impact_data, impacted_nodes,
        )

        return {
            # 兼容旧字段
            "impacted_nodes": impacted_nodes,
            "impacted_edges": impacted_edges,
            "reachability_drop": reachability_detail.pair_reachability_drop,
            "service_risk": risk_breakdown.composite_risk,
            "affected_services": sorted(impact_data.get("affected_services", set())),
            "warnings": warnings,
            # 新增字段
            "removed_node_ids": sorted(impact_data.get("removed_nodes", set())),
            "removed_edge_ids": sorted(impact_data.get("removed_edges", set())),
            "affected_node_ids": sorted(impact_data.get("affected_nodes", set())),
            "affected_edge_ids": sorted(impact_data.get("affected_edges", set())),
            "reachability_detail": reachability_detail,
            "impacted_services": impacted_services,
            "service_risk_breakdown": risk_breakdown,
            "confidence": confidence,
            # 节点/边级增量（供前端 diff 视图使用）
            "node_risk_deltas": self._compute_node_risk_deltas(before, after),
            "edge_weight_deltas": self._compute_edge_weight_deltas(before, after),
        }

    @staticmethod
    def _compute_node_risk_deltas(
        before: GraphResponseSchema, after: GraphResponseSchema,
    ) -> dict[str, float]:
        """计算节点级风险增量：仅包含风险值发生变化的节点。"""
        before_nodes = {n.id: n.risk for n in before.nodes}
        deltas = {}
        for node in after.nodes:
            prev = before_nodes.get(node.id)
            if prev is not None and node.risk != prev:
                deltas[node.id] = node.risk
        return deltas

    @staticmethod
    def _compute_edge_weight_deltas(
        before: GraphResponseSchema, after: GraphResponseSchema,
    ) -> dict[str, int]:
        """计算边级权重增量：仅包含权重发生变化的边。"""
        before_edges = {e.id: e.weight for e in before.edges}
        deltas = {}
        for edge in after.edges:
            prev = before_edges.get(edge.id)
            if prev is not None and edge.weight != prev:
                deltas[edge.id] = edge.weight
        return deltas

    def _generate_warnings(
        self,
        reachability_detail,
        risk_breakdown,
        impact_data: dict,
        impacted_nodes: int,
    ) -> list[str]:
        """根据评估结果生成告警提示。"""
        warnings = []

        if impacted_nodes > 5:
            warnings.append(f"高影响: {impacted_nodes} 个节点将被隔离")

        # 关键服务检查
        affected_services = impact_data.get("affected_services", set())
        critical_count = sum(
            1 for s in affected_services
            if SERVICE_IMPORTANCE.get(s.lower(), 0) >= 0.8
        )
        if critical_count > 0:
            warnings.append(f"关键服务受影响: {critical_count} 个")

        if reachability_detail.pair_reachability_drop > 0.2:
            pct = reachability_detail.pair_reachability_drop
            warnings.append(f"源-目标对可达性显著下降: {pct:.0%}")

        if reachability_detail.subnet_reachability_drop > 0.3:
            pct = reachability_detail.subnet_reachability_drop
            warnings.append(f"子网可达性显著下降: {pct:.0%}")

        if risk_breakdown.composite_risk > 0.7:
            warnings.append(
                f"综合风险评分较高: {risk_breakdown.composite_risk:.2f}，建议谨慎执行",
            )

        return warnings

    # ══════════════════════════════════════════════════════════
    # 可能绕行路径
    # ══════════════════════════════════════════════════════════

    def _find_alternative_paths(
        self,
        graph: GraphResponseSchema,
        blocked_sources: list[str],
    ) -> list[AlternativePath]:
        """
        为被阻断源查找可能绕行路径。

        语义：这些路径表示"如果需要恢复连通性，可能的绕行方案"，
        不作为受影响节点集合的来源。
        """
        alt_paths = []

        if not blocked_sources or len(graph.nodes) < 3:
            return alt_paths

        # 构建邻接表
        adj = {}
        for node in graph.nodes:
            adj[node.id] = []

        for edge in graph.edges:
            if edge.source in adj:
                adj[edge.source].append(edge.target)

        # 为被阻断源查找路径（限制 2 个）
        for blocked in blocked_sources[:2]:
            targets = [n.id for n in graph.nodes if n.id != blocked]
            if not targets:
                continue

            target = targets[0]

            # BFS 查找避开阻断节点的路径
            path = self._bfs_path(adj, blocked, target, set(blocked_sources))

            if path and len(path) > 2:
                alt_paths.append(AlternativePath.model_validate({
                    "from": blocked,
                    "to": target,
                    "path": path,
                }))

        return alt_paths

    def _bfs_path(
        self,
        adj: dict,
        start: str,
        end: str,
        blocked: set,
    ) -> list[str]:
        """使用 BFS 查找避开阻断节点的路径。"""
        if start not in adj or end not in adj:
            return []

        queue = deque([(start, [start])])
        visited = {start}

        while queue:
            current, path = queue.popleft()

            if current == end:
                return path

            for neighbor in adj.get(current, []):
                if neighbor not in visited and neighbor not in blocked:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))

        return []

    # ══════════════════════════════════════════════════════════
    # 结构化解释（面向研究报告）
    # ══════════════════════════════════════════════════════════

    def _build_explanation(
        self,
        actions: list[dict],
        impact: dict,
    ) -> tuple[list[str], list[ExplainSection]]:
        """
        构建解释文本。

        返回:
            (legacy_explain, explain_sections)
            - legacy_explain: 兼容旧版的扁平字符串列表
            - explain_sections: 结构化解释段落
        """
        sections = []

        # 1. 受影响对象
        sections.append(ExplainSection(
            section="affected_objects",
            title="受影响对象",
            content=self._explain_affected_objects(impact),
        ))

        # 2. 影响原因
        sections.append(ExplainSection(
            section="impact_reason",
            title="影响原因",
            content=self._explain_impact_reasons(actions),
        ))

        # 3. 指标变化
        sections.append(ExplainSection(
            section="metric_changes",
            title="指标变化",
            content=self._explain_metric_changes(impact),
        ))

        # 4. 风险判断
        sections.append(ExplainSection(
            section="risk_judgment",
            title="风险判断",
            content=self._explain_risk_judgment(impact),
        ))

        # 5. 建议措施
        sections.append(ExplainSection(
            section="recommended_actions",
            title="建议措施",
            content=self._explain_recommendations(impact),
        ))

        # 兼容旧版：将所有 section content 扁平化
        legacy_explain = []
        for s in sections:
            legacy_explain.extend(s.content)

        return legacy_explain, sections

    def _explain_affected_objects(self, impact: dict) -> list[str]:
        """构建受影响对象说明。"""
        lines = []

        removed_nodes = impact.get("removed_node_ids", [])
        removed_edges = impact.get("removed_edge_ids", [])
        affected_nodes = impact.get("affected_node_ids", [])
        affected_services = impact.get("affected_services", [])

        if removed_nodes:
            lines.append(f"被移除节点: {', '.join(removed_nodes)}")
        if removed_edges:
            svc_str = ""
            if affected_services:
                svc_str = f"（涉及 {', '.join(affected_services)}）"
            lines.append(f"被移除边: {', '.join(removed_edges)}{svc_str}")
        if affected_nodes:
            lines.append(f"受波及邻居节点: {', '.join(affected_nodes)}")

        return lines

    def _explain_impact_reasons(self, actions: list[dict]) -> list[str]:
        """构建影响原因说明。"""
        lines = []

        action_desc = {
            "block_ip": "封锁 IP {target} 移除了该节点的所有出入边",
            "isolate_host": "隔离主机 {target} 移除了该节点及所有关联连接",
            "segment_subnet": "分段子网 {target} 阻断了跨网段边界流量",
            "rate_limit_service": "限流服务 {target} 可能影响高流量连接",
        }

        for action in actions:
            action_type = action.get("action_type", "")
            target_value = action.get("target", {}).get("value", "")
            template = action_desc.get(action_type)
            if template:
                lines.append(template.format(target=target_value))

        return lines

    def _explain_metric_changes(self, impact: dict) -> list[str]:
        """构建指标变化说明。"""
        lines = []

        rd = impact.get("reachability_detail")
        if rd:
            if rd.pair_reachability_drop > 0:
                before_pct = 100.0
                after_pct = (1 - rd.pair_reachability_drop) * 100
                lines.append(
                    f"源-目标对可达性: {before_pct:.0f}% → {after_pct:.1f}%"
                    f"（下降 {rd.pair_reachability_drop:.1%}）",
                )
            if rd.service_reachability_drop > 0:
                lines.append(
                    f"服务可达性下降: {rd.service_reachability_drop:.1%}",
                )
            if rd.subnet_reachability_drop > 0:
                lines.append(
                    f"子网可达性下降: {rd.subnet_reachability_drop:.1%}",
                )

        return lines

    def _explain_risk_judgment(self, impact: dict) -> list[str]:
        """构建风险判断说明。"""
        lines = []

        breakdown = impact.get("service_risk_breakdown")
        confidence = impact.get("confidence", 0.5)

        if breakdown:
            risk = breakdown.composite_risk
            level = "低" if risk < 0.3 else "中" if risk < 0.7 else "高"
            lines.append(
                f"综合风险评分 {risk:.2f}（{level}风险），置信度 {confidence:.2f}",
            )

            # 找出主要风险因素（得分 > 0.5 的子项）
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

    def _explain_recommendations(self, impact: dict) -> list[str]:
        """构建建议措施说明。"""
        lines = []

        breakdown = impact.get("service_risk_breakdown")
        affected_services = impact.get("affected_services", [])

        if breakdown and breakdown.composite_risk > 0.5:
            lines.append("建议在执行前验证替代访问路径可用性")

            # 针对关键服务的建议
            for svc in affected_services:
                importance = SERVICE_IMPORTANCE.get(
                    svc.lower(), SERVICE_IMPORTANCE_DEFAULT,
                )
                if importance >= 0.8:
                    lines.append(f"考虑对 {svc} 服务配置临时访问白名单")

            if breakdown.traffic_proportion_score > 0.5:
                lines.append("建议在低流量时段执行该操作以降低影响")

        return lines

    # ══════════════════════════════════════════════════════════
    # 工具方法
    # ══════════════════════════════════════════════════════════

    def _ip_to_subnet_from_id(self, node_id: str) -> str:
        """从节点 ID 中提取子网。"""
        if node_id.startswith("ip:"):
            ip = node_id[3:]
            parts = ip.split(".")
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
        elif node_id.startswith("subnet:"):
            return node_id[7:]
        return ""

"""
Twin service.
ActionPlan and DryRun simulation.
"""

import json
from collections import deque
from datetime import datetime
from typing import Literal

from sqlalchemy.orm import Session

from app.core.logging import get_logger
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
)
from app.schemas.topology import GraphResponseSchema
from app.services.topology.service import TopologyService

logger = get_logger(__name__)


class TwinService:
    """
    Service for twin simulation (dry-run).
    
    Follows DOC B B4.9 specification.
    """

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
        """
        Create an action plan.
        
        Args:
            alert_id: Related alert ID
            actions: List of planned actions
            source: 'agent' or 'manual'
            notes: Optional notes
            
        Returns:
            ActionPlan schema
        """
        plan_id = generate_uuid()
        now = utc_now()
        
        # Serialize actions
        actions_json = json.dumps([a.model_dump() for a in actions])
        
        # Create database record
        plan_model = TwinPlan(
            id=plan_id,
            created_at=now,
            alert_id=alert_id,
            source=source,
            actions=actions_json,
            notes=notes,
        )
        self.db.add(plan_model)
        
        # Update alert's twin field
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
        """
        Execute dry-run simulation.
        
        Args:
            plan: TwinPlan model
            start: Time window start
            end: Time window end
            mode: Graph mode ('ip' or 'subnet')
            
        Returns:
            DryRunResult schema
        """
        logger.info(f"Running dry-run for plan {plan.id}")
        
        # Build original graph
        graph_before = self.topology_service.build_graph(start, end, mode)
        hash_before = self.topology_service.compute_graph_hash(graph_before)
        
        # Parse actions
        actions = json.loads(plan.actions) if isinstance(plan.actions, str) else plan.actions
        
        # Simulate actions on graph
        graph_after, impact_data = self._simulate_actions(graph_before, actions)
        hash_after = self.topology_service.compute_graph_hash(graph_after)
        
        # Calculate impact metrics
        impact = self._calculate_impact(
            graph_before,
            graph_after,
            impact_data,
        )
        
        # Find alternative paths
        alt_paths = self._find_alternative_paths(
            graph_after,
            impact_data.get("blocked_sources", []),
        )
        
        # Build explanation
        explain = self._build_explanation(actions, impact)
        
        # Create dry-run record
        dry_run_id = generate_uuid()
        now = utc_now()
        
        result = DryRunResultSchema(
            version="1.1",
            id=dry_run_id,
            created_at=datetime_to_iso(now),
            alert_id=plan.alert_id,
            plan_id=plan.id,
            before=GraphHash(graph_hash=hash_before),
            after=GraphHash(graph_hash=hash_after),
            impact=DryRunImpact(
                impacted_nodes_count=impact["impacted_nodes"],
                impacted_edges_count=impact["impacted_edges"],
                reachability_drop=impact["reachability_drop"],
                service_disruption_risk=impact["service_risk"],
                affected_services=impact["affected_services"],
                warnings=impact["warnings"],
            ),
            alternative_paths=alt_paths,
            explain=explain,
        )
        
        # Save to database
        dry_run_model = DryRun(
            id=dry_run_id,
            created_at=now,
            alert_id=plan.alert_id,
            plan_id=plan.id,
            payload=result.model_dump_json(),
        )
        self.db.add(dry_run_model)
        
        # Update alert's twin field
        alert = self.db.query(Alert).filter(Alert.id == plan.alert_id).first()
        if alert:
            twin_data = json.loads(alert.twin) if isinstance(alert.twin, str) else alert.twin
            twin_data["dry_run_id"] = dry_run_id
            alert.twin = json.dumps(twin_data)
        
        self.db.commit()
        
        logger.info(f"Completed dry-run {dry_run_id}")
        return result

    def _simulate_actions(
        self,
        graph: GraphResponseSchema,
        actions: list[dict],
    ) -> tuple[GraphResponseSchema, dict]:
        """
        Simulate actions on graph.
        
        Returns modified graph and impact data.
        """
        
        # Copy graph data
        nodes = {n.id: n for n in graph.nodes}
        edges = list(graph.edges)
        
        impact_data = {
            "removed_nodes": set(),
            "removed_edges": set(),
            "blocked_sources": [],
            "affected_services": set(),
        }
        
        for action in actions:
            action_type = action.get("action_type", "")
            target = action.get("target", {})
            target_value = target.get("value", "")
            
            if action_type == "block_ip":
                # Remove edges involving this IP
                node_id = f"ip:{target_value}"
                impact_data["blocked_sources"].append(node_id)
                
                new_edges = []
                for edge in edges:
                    if edge.source == node_id or edge.target == node_id:
                        impact_data["removed_edges"].add(edge.id)
                        impact_data["affected_services"].add(f"{edge.proto}/{edge.dst_port}")
                    else:
                        new_edges.append(edge)
                edges = new_edges
                
            elif action_type == "isolate_host":
                # Remove all edges for this host
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
                # Remove edges crossing subnet boundary
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
                # Mark affected edges (don't remove, just flag)
                proto_port = target_value.split("/")
                if len(proto_port) == 2:
                    proto, port = proto_port[0].upper(), int(proto_port[1])
                    for edge in edges:
                        if edge.proto == proto and edge.dst_port == port:
                            impact_data["affected_services"].add(f"{proto}/{port}")
        
        # Create modified graph
        modified = GraphResponseSchema(
            version=graph.version,
            nodes=list(nodes.values()),
            edges=edges,
            meta=graph.meta,
        )
        
        return modified, impact_data

    def _calculate_impact(
        self,
        before,
        after,
        impact_data: dict,
    ) -> dict:
        """Calculate impact metrics from graph comparison."""
        nodes_before = len(before.nodes)
        nodes_after = len(after.nodes)
        edges_before = len(before.edges)
        edges_after = len(after.edges)
        
        impacted_nodes = nodes_before - nodes_after
        impacted_edges = edges_before - edges_after
        
        # Calculate reachability drop (simplified: ratio of removed edges)
        if edges_before > 0:
            reachability_drop = impacted_edges / edges_before
        else:
            reachability_drop = 0
        
        # Calculate service disruption risk
        affected_services = list(impact_data.get("affected_services", []))
        critical_services = ["tcp/22", "tcp/443", "tcp/80", "tcp/3389"]
        
        critical_count = sum(1 for s in affected_services if s.lower() in critical_services)
        
        if len(affected_services) > 0:
            service_risk = 0.3 + (critical_count * 0.2) + (len(affected_services) * 0.05)
        else:
            service_risk = 0.1
        
        service_risk = min(service_risk, 1.0)
        
        # Generate warnings
        warnings = []
        if impacted_nodes > 5:
            warnings.append(f"High impact: {impacted_nodes} nodes will be isolated")
        if critical_count > 0:
            warnings.append(f"Critical services affected: {critical_count}")
        if reachability_drop > 0.2:
            warnings.append(f"Significant reachability reduction: {reachability_drop:.0%}")
        
        return {
            "impacted_nodes": impacted_nodes,
            "impacted_edges": impacted_edges,
            "reachability_drop": round(reachability_drop, 3),
            "service_risk": round(service_risk, 3),
            "affected_services": affected_services,
            "warnings": warnings,
        }

    def _find_alternative_paths(
        self,
        graph,
        blocked_sources: list[str],
    ) -> list[AlternativePath]:
        """Find alternative paths avoiding blocked sources."""
        alt_paths = []
        
        if not blocked_sources or len(graph.nodes) < 3:
            return alt_paths
        
        # Build adjacency list
        adj = {}
        for node in graph.nodes:
            adj[node.id] = []
        
        for edge in graph.edges:
            if edge.source in adj:
                adj[edge.source].append(edge.target)
        
        # Find paths for blocked sources
        for blocked in blocked_sources[:2]:  # Limit to 2
            # Pick a random target
            targets = [n.id for n in graph.nodes if n.id != blocked]
            if not targets:
                continue
            
            target = targets[0]
            
            # BFS to find path avoiding blocked node
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
        """BFS to find path avoiding blocked nodes."""
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

    def _build_explanation(self, actions: list[dict], impact: dict) -> list[str]:
        """Build explanation text for dry-run results."""
        explain = []
        
        for action in actions:
            action_type = action.get("action_type", "")
            target = action.get("target", {})
            target_value = target.get("value", "")
            
            if action_type == "block_ip":
                explain.append(f"Blocking IP {target_value} removes associated edges within window")
            elif action_type == "isolate_host":
                explain.append(f"Isolating host {target_value} removes all its connections")
            elif action_type == "segment_subnet":
                explain.append(f"Segmenting subnet {target_value} blocks cross-boundary traffic")
            elif action_type == "rate_limit_service":
                explain.append(f"Rate limiting {target_value} may affect high-volume connections")
        
        if impact["reachability_drop"] > 0:
            explain.append(f"Reachability reduced by {impact['reachability_drop']:.1%} of nodes")
        
        return explain

    def _ip_to_subnet_from_id(self, node_id: str) -> str:
        """Extract subnet from node ID."""
        if node_id.startswith("ip:"):
            ip = node_id[3:]
            parts = ip.split(".")
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
        elif node_id.startswith("subnet:"):
            return node_id[7:]
        return ""

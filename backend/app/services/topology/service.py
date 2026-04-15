import hashlib
import json
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.utils import datetime_to_iso
from app.schemas.topology import GraphResponseSchema, GraphNode, GraphEdge, GraphMeta

logger = get_logger(__name__)


class TopologyService:
    def __init__(self, db: Session):
        self.db = db

    def build_graph(
        self,
        start: datetime,
        end: datetime,
        mode: Literal["ip", "subnet"] = "ip",
    ) -> GraphResponseSchema:
        from app.models.flow import Flow
        from app.models.alert import Alert

        logger.info(f"构建拓扑图: {start} 至 {end}, 模式={mode}")

        _start = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
        _end = end if end.tzinfo else end.replace(tzinfo=timezone.utc)

        flows = self.db.query(Flow).filter(
            Flow.ts_start <= _end,
            Flow.ts_end >= _start,
        ).all()

        logger.info(f"时间窗口内找到 {len(flows)} 条流")

        nodes: dict[str, GraphNode] = {}
        edges: dict[str, dict] = {}

        alerts = self.db.query(Alert).filter(
            Alert.time_window_start <= _end,
            Alert.time_window_end >= _start,
        ).all()

        alert_by_flow: dict[str, list] = {}
        for alert in alerts:
            evidence = json.loads(alert.evidence) if isinstance(alert.evidence, str) else alert.evidence
            for flow_id in evidence.get("flow_ids", []):
                alert_by_flow.setdefault(flow_id, []).append(alert)

        for flow in flows:
            if mode == "subnet":
                src_id = f"subnet:{self._ip_to_subnet(flow.src_ip)}"
                dst_id = f"subnet:{self._ip_to_subnet(flow.dst_ip)}"
            else:
                src_id = f"ip:{flow.src_ip}"
                dst_id = f"ip:{flow.dst_ip}"

            if src_id not in nodes:
                nodes[src_id] = GraphNode(
                    id=src_id,
                    label=flow.src_ip if mode == "ip" else self._ip_to_subnet(flow.src_ip),
                    type="host" if mode == "ip" else "subnet",
                    risk=0.0,
                )

            if dst_id not in nodes:
                nodes[dst_id] = GraphNode(
                    id=dst_id,
                    label=flow.dst_ip if mode == "ip" else self._ip_to_subnet(flow.dst_ip),
                    type="host" if mode == "ip" else "subnet",
                    risk=0.0,
                )

            edge_key = f"{src_id}>{dst_id}:{flow.proto}:{flow.dst_port}"

            if edge_key not in edges:
                edges[edge_key] = {
                    "id": f"e{len(edges)+1}",
                    "source": src_id,
                    "target": dst_id,
                    "proto": flow.proto,
                    "dst_port": flow.dst_port,
                    "weight": 0,
                    "risk": 0.0,
                    "activeIntervals": [],
                    "alert_ids": set(),
                }

            edge = edges[edge_key]
            edge["weight"] += 1

            flow_start = flow.ts_start if flow.ts_start.tzinfo else flow.ts_start.replace(tzinfo=timezone.utc)
            flow_end = flow.ts_end if flow.ts_end.tzinfo else flow.ts_end.replace(tzinfo=timezone.utc)
            iv_start = max(flow_start, _start)
            iv_end = min(flow_end, _end)
            edge["activeIntervals"].append([datetime_to_iso(iv_start), datetime_to_iso(iv_end)])

            if flow.anomaly_score:
                edge["risk"] = max(edge["risk"], flow.anomaly_score)
                nodes[src_id].risk = max(nodes[src_id].risk, flow.anomaly_score)
                nodes[dst_id].risk = max(nodes[dst_id].risk, flow.anomaly_score * 0.5)

            if flow.id in alert_by_flow:
                for alert in alert_by_flow[flow.id]:
                    edge["alert_ids"].add(alert.id)

        edge_list = []
        for edge_data in edges.values():
            merged = self._merge_intervals(edge_data["activeIntervals"])
            edge_list.append(GraphEdge(
                id=edge_data["id"],
                source=edge_data["source"],
                target=edge_data["target"],
                proto=edge_data["proto"],
                dst_port=edge_data["dst_port"],
                weight=edge_data["weight"],
                risk=round(min(edge_data["risk"], 1.0), 4),
                activeIntervals=merged,
                alert_ids=sorted(edge_data["alert_ids"]),
            ))

        graph = GraphResponseSchema(
            version="1.1",
            nodes=list(nodes.values()),
            edges=edge_list,
            meta=GraphMeta(
                start=datetime_to_iso(start),
                end=datetime_to_iso(end),
                mode=mode,
            ),
        )

        logger.info(f"已构建拓扑图：{len(nodes)} 个节点，{len(edge_list)} 条边")
        return graph

    @staticmethod
    def _merge_intervals(intervals: list[list[str]]) -> list[list[str]]:
        if not intervals:
            return []
        sorted_iv = sorted(intervals, key=lambda iv: iv[0])
        merged: list[list[str]] = [sorted_iv[0]]
        for iv in sorted_iv[1:]:
            if iv[0] <= merged[-1][1]:
                if iv[1] > merged[-1][1]:
                    merged[-1][1] = iv[1]
            else:
                merged.append(iv)
        return merged

    def compute_graph_hash(self, graph: GraphResponseSchema) -> str:
        data = {
            "nodes": sorted([n.model_dump() for n in graph.nodes], key=lambda x: x["id"]),
            "edges": sorted([e.model_dump() for e in graph.edges], key=lambda x: x["id"]),
        }
        json_str = json.dumps(data, sort_keys=True)
        return f"sha256:{hashlib.sha256(json_str.encode()).hexdigest()}"

    @staticmethod
    def _ip_to_subnet(ip: str) -> str:
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
        return ip  

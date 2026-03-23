"""
拓扑服务。
为孪生仿真构建 GraphResponse。
"""

import hashlib
import json
from datetime import datetime
from typing import Literal

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.utils import datetime_to_iso
from app.schemas.topology import GraphResponseSchema, GraphNode, GraphEdge, GraphMeta

logger = get_logger(__name__)


class TopologyService:
    """
用于构建拓扑图的服务。

遵循 DOC B B4.6 规范。
"""

    def __init__(self, db: Session):
        self.db = db

    def build_graph(
        self,
        start: datetime,
        end: datetime,
        mode: Literal["ip", "subnet"] = "ip",
    ) -> GraphResponseSchema:
        """
        Build topology graph for time window.
        
        Args:
            start: Start timestamp
            end: End timestamp
            mode: 'ip' for host-level, 'subnet' for subnet grouping
            
        Returns:
            GraphResponse with nodes, edges, and metadata
        """
        from app.models.flow import Flow
        from app.models.alert import Alert
        
        logger.info(f"Building graph: {start} to {end}, mode={mode}")
        
        # 规范化为 naive UTC，便于与 SQLite 存储的时间比较
        _start = start.replace(tzinfo=None) if start.tzinfo else start
        _end = end.replace(tzinfo=None) if end.tzinfo else end
        
        # 查询与时间窗“重叠”的 flow（而非仅完全包含）
        # 重叠条件：flow.ts_start <= end 且 flow.ts_end >= start
        flows = self.db.query(Flow).filter(
            Flow.ts_start <= _end,
            Flow.ts_end >= _start,
        ).all()
        
        logger.info(f"Found {len(flows)} flows in window")
        
        # 构建节点与边的字典
        nodes: dict[str, GraphNode] = {}
        edges: dict[str, dict] = {}  # edge_key -> edge_data
        
        # 获取与时间窗重叠的所有 alert
        alerts = self.db.query(Alert).filter(
            Alert.time_window_start <= _end,
            Alert.time_window_end >= _start,
        ).all()
        
        # 构建按 flow 映射的 alert 索引
        alert_by_flow: dict[str, list] = {}
        for alert in alerts:
            evidence = json.loads(alert.evidence) if isinstance(alert.evidence, str) else alert.evidence
            for flow_id in evidence.get("flow_ids", []):
                if flow_id not in alert_by_flow:
                    alert_by_flow[flow_id] = []
                alert_by_flow[flow_id].append(alert)
        
        for flow in flows:
            # 按模式计算节点 ID
            if mode == "subnet":
                src_id = f"subnet:{self._ip_to_subnet(flow.src_ip)}"
                dst_id = f"subnet:{self._ip_to_subnet(flow.dst_ip)}"
            else:
                src_id = f"ip:{flow.src_ip}"
                dst_id = f"ip:{flow.dst_ip}"
            
            # 创建/更新节点
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
            
            # 生成边键
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
            
            # 将区间裁剪到查询窗口，确保时间滑块行为精确
            flow_start = flow.ts_start.replace(tzinfo=None) if flow.ts_start.tzinfo else flow.ts_start
            flow_end = flow.ts_end.replace(tzinfo=None) if flow.ts_end.tzinfo else flow.ts_end
            iv_start = max(flow_start, _start)
            iv_end = min(flow_end, _end)
            interval = [datetime_to_iso(iv_start), datetime_to_iso(iv_end)]
            edge["activeIntervals"].append(interval)
            
            # 根据异常分更新风险值
            if flow.anomaly_score:
                edge["risk"] = max(edge["risk"], flow.anomaly_score)
                nodes[src_id].risk = max(nodes[src_id].risk, flow.anomaly_score)
                nodes[dst_id].risk = max(nodes[dst_id].risk, flow.anomaly_score * 0.5)
            
            # 添加 alert 关联
            if flow.id in alert_by_flow:
                for alert in alert_by_flow[flow.id]:
                    edge["alert_ids"].add(alert.id)

        # 转换为 GraphEdge 对象
        edge_list = []
        for edge_data in edges.values():
            # 排序并合并重叠区间，保证时间滑块展示清晰
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
        
        # 构建响应
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
        
        logger.info(f"Built graph with {len(nodes)} nodes and {len(edge_list)} edges")
        return graph

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_intervals(intervals: list[list[str]]) -> list[list[str]]:
        """Sort intervals chronologically and merge overlapping ones."""
        if not intervals:
            return []
        # 按开始时间排序（ISO8601 字符串可按字典序排序）
        sorted_iv = sorted(intervals, key=lambda iv: iv[0])
        merged: list[list[str]] = [sorted_iv[0]]
        for iv in sorted_iv[1:]:
            if iv[0] <= merged[-1][1]:
                # 重叠或相邻 -> 延展
                if iv[1] > merged[-1][1]:
                    merged[-1][1] = iv[1]
            else:
                merged.append(iv)
        return merged

    def compute_graph_hash(self, graph: GraphResponseSchema) -> str:
        """Compute SHA256 hash of graph state."""
        # 构建确定性表示
        data = {
            "nodes": sorted([n.model_dump() for n in graph.nodes], key=lambda x: x["id"]),
            "edges": sorted([e.model_dump() for e in graph.edges], key=lambda x: x["id"]),
        }
        
        json_str = json.dumps(data, sort_keys=True)
        return f"sha256:{hashlib.sha256(json_str.encode()).hexdigest()}"

    @staticmethod
    def _ip_to_subnet(ip: str) -> str:
        """Convert IP to /24 subnet."""
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
        return ip  # IPv6 或非法输入保持原样

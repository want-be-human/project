"""
多维可达性分析器。
纯函数类，接收 before/after 两张图，输出 ReachabilityDetail。
不依赖数据库，仅基于图结构进行分析。

可扩展接口：
- 后续可引入 BusinessDependencyGraph 作为额外输入
- pair_metrics 可扩展为完整的 reachability matrix
"""

import random
from collections import deque

from app.core.scoring_policy import REACHABILITY_PAIR_SAMPLE_LIMIT
from app.schemas.topology import GraphResponseSchema
from app.schemas.twin import (
    PairReachabilityMetric,
    ReachabilityDetail,
)


class ReachabilityAnalyzer:
    """
    多维可达性分析器。

    分析维度：
    - pair: 源-目标节点对可达性损失率
    - service: 按协议/端口分组的可达性损失率
    - subnet: 按子网对分组的跨子网可达性损失率
    """

    def __init__(
        self,
        graph_before: GraphResponseSchema,
        graph_after: GraphResponseSchema,
    ):
        self._before = graph_before
        self._after = graph_after
        # 构建邻接表（有向）
        self._adj_before = self._build_adjacency(graph_before)
        self._adj_after = self._build_adjacency(graph_after)
        # 节点集合
        self._nodes_before = {n.id for n in graph_before.nodes}
        self._nodes_after = {n.id for n in graph_after.nodes}

    # ── 公开方法 ──────────────────────────────────────────────

    def build_reachability_detail(self) -> ReachabilityDetail:
        """组装完整的多维可达性结果。"""
        pair_drop, pair_metrics = self.compute_pair_reachability()
        service_drop = self.compute_service_reachability()
        subnet_drop = self.compute_subnet_reachability()

        return ReachabilityDetail(
            pair_reachability_drop=round(pair_drop, 4),
            service_reachability_drop=round(service_drop, 4),
            subnet_reachability_drop=round(subnet_drop, 4),
            pair_metrics=pair_metrics,
        )

    def compute_pair_reachability(
        self,
    ) -> tuple[float, list[PairReachabilityMetric]]:
        """
        计算源-目标对可达性下降。
        采样 REACHABILITY_PAIR_SAMPLE_LIMIT 对节点，
        BFS 判断 before/after 可达性，返回 (drop_ratio, metrics_list)。
        """
        nodes = sorted(self._nodes_before)
        if len(nodes) < 2:
            return 0.0, []

        # 生成所有有向节点对
        all_pairs = [(a, b) for a in nodes for b in nodes if a != b]

        # 采样控制
        if len(all_pairs) > REACHABILITY_PAIR_SAMPLE_LIMIT:
            rng = random.Random(42)  # 固定种子保证可复现
            all_pairs = rng.sample(all_pairs, REACHABILITY_PAIR_SAMPLE_LIMIT)

        # 构建边的协议映射：(src, dst) → set[proto/port]
        edge_protocols = self._build_edge_protocols(self._before)

        metrics: list[PairReachabilityMetric] = []
        reachable_before_count = 0
        lost_count = 0

        for src, dst in all_pairs:
            rb = self._is_reachable(self._adj_before, src, dst)
            ra = self._is_reachable(self._adj_after, src, dst)

            if rb:
                reachable_before_count += 1
                if not ra:
                    lost_count += 1

            # 仅记录发生变化的对（减少输出体积）
            if rb != ra:
                protos = list(edge_protocols.get((src, dst), set()))
                metrics.append(PairReachabilityMetric(
                    source=src,
                    target=dst,
                    reachable_before=rb,
                    reachable_after=ra,
                    protocols=protos,
                ))

        if reachable_before_count == 0:
            return 0.0, metrics

        drop = lost_count / reachable_before_count
        return drop, metrics

    def compute_service_reachability(self) -> float:
        """
        按协议/端口分组，计算每种服务的可达对数下降比例的加权平均。
        """
        # 按服务分组边
        service_edges_before: dict[str, list[tuple[str, str]]] = {}
        for edge in self._before.edges:
            svc = f"{edge.proto}/{edge.dst_port}".lower()
            service_edges_before.setdefault(svc, []).append((edge.source, edge.target))

        service_edges_after: dict[str, set[tuple[str, str]]] = {}
        for edge in self._after.edges:
            svc = f"{edge.proto}/{edge.dst_port}".lower()
            service_edges_after.setdefault(svc, set()).add((edge.source, edge.target))

        if not service_edges_before:
            return 0.0

        total_pairs_before = 0
        total_lost = 0

        for svc, pairs in service_edges_before.items():
            after_set = service_edges_after.get(svc, set())
            for pair in pairs:
                total_pairs_before += 1
                if pair not in after_set:
                    total_lost += 1

        if total_pairs_before == 0:
            return 0.0

        return round(total_lost / total_pairs_before, 4)

    def compute_subnet_reachability(self) -> float:
        """
        按子网对分组，计算跨子网可达性下降比例。
        """
        # 收集跨子网边
        cross_before = set()
        for edge in self._before.edges:
            src_sub = self._ip_to_subnet(edge.source)
            dst_sub = self._ip_to_subnet(edge.target)
            if src_sub and dst_sub and src_sub != dst_sub:
                cross_before.add((edge.source, edge.target))

        if not cross_before:
            return 0.0

        cross_after = set()
        for edge in self._after.edges:
            src_sub = self._ip_to_subnet(edge.source)
            dst_sub = self._ip_to_subnet(edge.target)
            if src_sub and dst_sub and src_sub != dst_sub:
                cross_after.add((edge.source, edge.target))

        lost = len(cross_before - cross_after)
        return round(lost / len(cross_before), 4)

    # ── 内部工具方法 ──────────────────────────────────────────

    @staticmethod
    def _build_adjacency(graph: GraphResponseSchema) -> dict[str, list[str]]:
        """构建有向邻接表。"""
        adj: dict[str, list[str]] = {n.id: [] for n in graph.nodes}
        for edge in graph.edges:
            if edge.source in adj:
                adj[edge.source].append(edge.target)
        return adj

    @staticmethod
    def _build_edge_protocols(
        graph: GraphResponseSchema,
    ) -> dict[tuple[str, str], set[str]]:
        """构建边的协议映射：(src, dst) → set[proto/port]。"""
        mapping: dict[tuple[str, str], set[str]] = {}
        for edge in graph.edges:
            key = (edge.source, edge.target)
            proto = f"{edge.proto}/{edge.dst_port}".lower()
            mapping.setdefault(key, set()).add(proto)
        return mapping

    @staticmethod
    def _is_reachable(adj: dict[str, list[str]], start: str, end: str) -> bool:
        """BFS 判断 start 是否可达 end。"""
        if start not in adj or end not in adj:
            return False
        if start == end:
            return True

        visited = {start}
        queue = deque([start])

        while queue:
            current = queue.popleft()
            for neighbor in adj.get(current, []):
                if neighbor == end:
                    return True
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        return False

    @staticmethod
    def _ip_to_subnet(node_id: str) -> str:
        """从节点 ID 中提取子网（/24）。"""
        if node_id.startswith("ip:"):
            ip = node_id[3:]
            parts = ip.split(".")
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
        elif node_id.startswith("subnet:"):
            return node_id[7:]
        return ""

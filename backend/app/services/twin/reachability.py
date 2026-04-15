import random
from collections import deque

from app.core.scoring_policy import REACHABILITY_PAIR_SAMPLE_LIMIT
from app.schemas.topology import GraphResponseSchema
from app.schemas.twin import (
    PairReachabilityMetric,
    ReachabilityDetail,
)


class ReachabilityAnalyzer:
    def __init__(
        self,
        graph_before: GraphResponseSchema,
        graph_after: GraphResponseSchema,
    ):
        self._before = graph_before
        self._after = graph_after
        self._adj_before = self._build_adj(graph_before)
        self._adj_after = self._build_adj(graph_after)
        self._nodes_before = {n.id for n in graph_before.nodes}
        self._nodes_after = {n.id for n in graph_after.nodes}

    def build_reachability_detail(self) -> ReachabilityDetail:
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
        nodes = sorted(self._nodes_before)
        if len(nodes) < 2:
            return 0.0, []

        pairs = [(a, b) for a in nodes for b in nodes if a != b]

        if len(pairs) > REACHABILITY_PAIR_SAMPLE_LIMIT:
            # 固定种子保证可复现
            rng = random.Random(42)
            pairs = rng.sample(pairs, REACHABILITY_PAIR_SAMPLE_LIMIT)

        edge_protos = self._build_edge_protos(self._before)

        metrics: list[PairReachabilityMetric] = []
        reach_before = 0
        lost = 0

        for src, dst in pairs:
            rb = self._is_reachable(self._adj_before, src, dst)
            ra = self._is_reachable(self._adj_after, src, dst)

            if rb:
                reach_before += 1
                if not ra:
                    lost += 1

            if rb == ra:
                continue
            protos = list(edge_protos.get((src, dst), set()))
            metrics.append(PairReachabilityMetric(
                source=src,
                target=dst,
                reachable_before=rb,
                reachable_after=ra,
                protocols=protos,
            ))

        if reach_before == 0:
            return 0.0, metrics

        return lost / reach_before, metrics

    def compute_service_reachability(self) -> float:
        svc_before: dict[str, list[tuple[str, str]]] = {}
        for edge in self._before.edges:
            svc = f"{edge.proto}/{edge.dst_port}".lower()
            svc_before.setdefault(svc, []).append((edge.source, edge.target))

        svc_after: dict[str, set[tuple[str, str]]] = {}
        for edge in self._after.edges:
            svc = f"{edge.proto}/{edge.dst_port}".lower()
            svc_after.setdefault(svc, set()).add((edge.source, edge.target))

        if not svc_before:
            return 0.0

        total = 0
        lost = 0
        for svc, pairs in svc_before.items():
            after_set = svc_after.get(svc, set())
            for pair in pairs:
                total += 1
                if pair not in after_set:
                    lost += 1

        if total == 0:
            return 0.0
        return round(lost / total, 4)

    def compute_subnet_reachability(self) -> float:
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

    @staticmethod
    def _build_adj(graph: GraphResponseSchema) -> dict[str, list[str]]:
        adj: dict[str, list[str]] = {n.id: [] for n in graph.nodes}
        for edge in graph.edges:
            if edge.source in adj:
                adj[edge.source].append(edge.target)
        return adj

    @staticmethod
    def _build_edge_protos(
        graph: GraphResponseSchema,
    ) -> dict[tuple[str, str], set[str]]:
        mapping: dict[tuple[str, str], set[str]] = {}
        for edge in graph.edges:
            key = (edge.source, edge.target)
            proto = f"{edge.proto}/{edge.dst_port}".lower()
            mapping.setdefault(key, set()).add(proto)
        return mapping

    @staticmethod
    def _is_reachable(adj: dict[str, list[str]], start: str, end: str) -> bool:
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
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                queue.append(neighbor)

        return False

    @staticmethod
    def _ip_to_subnet(node_id: str) -> str:
        if node_id.startswith("ip:"):
            parts = node_id[3:].split(".")
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
        elif node_id.startswith("subnet:"):
            return node_id[7:]
        return ""

import random
from collections import defaultdict, deque

from app.core.logging import get_logger

logger = get_logger(__name__)


class GraphFeatureBuilder:
    GRAPH_FEATURE_NAMES: list[str] = [
        "node_degree",
        "node_in_degree",
        "node_out_degree",
        "node_degree_ratio",
        "neighbor_max_baseline",
        "neighbor_mean_baseline",
        "edge_density_local",
        "subnet_peer_count",
        "subnet_anomaly_ratio",
        "is_hub_node",
        "betweenness_centrality",
        "clustering_coefficient",
    ]

    def __init__(self):
        self._last_graph: dict | None = None

    @property
    def last_graph(self) -> dict | None:
       
        return self._last_graph

    def build_and_extract(self, flows: list[dict]) -> list[dict]:
        if not flows:
            return flows

        graph = self._build_graph(flows)
        self._last_graph = graph
        return self.extract_with_graph(flows, graph)

    def extract_with_graph(self, flows: list[dict], graph: dict) -> list[dict]:
        if not flows:
            return flows

        n_nodes = len(graph["nodes"])
        logger.info(
            "GraphFeatureBuilder 开始计算: %d 条流, %d 个节点",
            len(flows), n_nodes,
        )

        out_nb_sets = graph["out_nb_sets"]
        in_nb_sets = graph["in_nb_sets"]
        all_nb_sets = {
            ip: out_nb_sets.get(ip, set()) | in_nb_sets.get(ip, set())
            for ip in graph["nodes"]
        }

        betweenness = self._compute_betweenness(graph, all_nb_sets)
        clustering = self._compute_clustering(graph, out_nb_sets, all_nb_sets)
        degree_stats = self._compute_degree_stats(all_nb_sets)

        node_max_baseline = graph["node_max_baseline"]
        nb_stats_cache: dict[str, tuple[float, float]] = {}
        for ip in graph["nodes"]:
            nbs = all_nb_sets.get(ip, set())
            if not nbs:
                nb_stats_cache[ip] = (0.0, 0.0)
                continue
            max_b = 0.0
            sum_b = 0.0
            cnt = 0
            for nb in nbs:
                mb = node_max_baseline.get(nb, 0.0)
                if mb > max_b:
                    max_b = mb
                sum_b += mb
                cnt += 1
            nb_stats_cache[ip] = (max_b, sum_b / cnt if cnt else 0.0)

        ego_density_cache: dict[str, float] = {}
        for ip in graph["nodes"]:
            nbs = all_nb_sets.get(ip, set())
            k = len(nbs)
            if k < 2:
                ego_density_cache[ip] = 0.0
                continue
            if k > 200:
                ego_density_cache[ip] = 0.0
                continue
            ego_edges = 0
            for n1 in nbs:
                out_of_n1 = out_nb_sets.get(n1, set())
                ego_edges += len(out_of_n1 & nbs) - (1 if n1 in (out_of_n1 & nbs) else 0)
            max_possible = k * (k - 1)
            ego_density_cache[ip] = ego_edges / max_possible if max_possible > 0 else 0.0

        subnet_peer_count_cache: dict[str, int] = {}
        subnet_anomaly_cache: dict[str, float] = {}
        for peers in graph["subnets"].values():
            count = len(peers)
            anomaly = 0
            total = 0
            for p in peers:
                mb = node_max_baseline.get(p, 0.0)
                total += 1
                if mb >= 0.7:
                    anomaly += 1
            ratio = anomaly / total if total > 0 else 0.0
            for p in peers:
                subnet_peer_count_cache[p] = count
                subnet_anomaly_cache[p] = ratio

        mean_deg = degree_stats.get("mean", 0)
        std_deg = degree_stats.get("std", 0)
        hub_threshold = mean_deg + 2 * std_deg

        for flow in flows:
            src_ip = flow.get("src_ip", "0.0.0.0")
            dst_ip = flow.get("dst_ip", "0.0.0.0")
            baseline = flow.get("_detection", {}).get("baseline_score", 0.0)

            src_nbs = all_nb_sets.get(src_ip, set())
            src_out = len(out_nb_sets.get(src_ip, set()))
            src_in = len(in_nb_sets.get(src_ip, set()))
            src_deg = len(src_nbs)
            src_nb_max, src_nb_mean = nb_stats_cache.get(src_ip, (0.0, 0.0))
            dst_nb_max, _ = nb_stats_cache.get(dst_ip, (0.0, 0.0))

            gf = {
                "node_degree": float(src_deg),
                "node_in_degree": float(src_in),
                "node_out_degree": float(src_out),
                "node_degree_ratio": float(src_out) / max(src_in, 1),
                "neighbor_max_baseline": round(max(src_nb_max, dst_nb_max), 4),
                "neighbor_mean_baseline": round(src_nb_mean, 4),
                "edge_density_local": round(ego_density_cache.get(src_ip, 0.0), 4),
                "subnet_peer_count": float(subnet_peer_count_cache.get(src_ip, 0)),
                "subnet_anomaly_ratio": round(subnet_anomaly_cache.get(src_ip, 0.0), 4),
                "is_hub_node": 1.0 if src_deg > hub_threshold and src_deg > 3 else 0.0,
                "betweenness_centrality": round(betweenness.get(src_ip, 0.0), 6),
                "clustering_coefficient": round(clustering.get(src_ip, 0.0), 4),
            }

            det = flow.setdefault("_detection", {})
            det["graph_features"] = gf
            det["graph_score"] = self._compute_graph_score(gf, baseline)

        logger.info(
            "GraphFeatureBuilder 完成: %d 条流, %d 个节点, %d 条边",
            len(flows),
            n_nodes,
            sum(len(targets) for targets in graph["out_edges"].values()),
        )
        return flows

    def _build_graph(self, flows: list[dict]) -> dict:
        nodes: set[str] = set()
        out_edges: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        in_edges: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        node_baselines: dict[str, list[float]] = defaultdict(list)
        subnets: dict[str, set[str]] = defaultdict(set)

        for flow in flows:
            src = flow.get("src_ip", "0.0.0.0")
            dst = flow.get("dst_ip", "0.0.0.0")
            baseline = flow.get("_detection", {}).get("baseline_score", 0.0)

            nodes.add(src)
            nodes.add(dst)
            out_edges[src][dst].append(baseline)
            in_edges[dst][src].append(baseline)
            node_baselines[src].append(baseline)
            node_baselines[dst].append(baseline)

            subnets[self._ip_to_subnet(src)].add(src)
            subnets[self._ip_to_subnet(dst)].add(dst)

        out_nb_sets = {ip: set(out_edges[ip].keys()) for ip in nodes if ip in out_edges}
        in_nb_sets = {ip: set(in_edges[ip].keys()) for ip in nodes if ip in in_edges}
        node_max_baseline = {
            ip: max(scores) if scores else 0.0
            for ip, scores in node_baselines.items()
        }

        return {
            "nodes": nodes,
            "out_edges": out_edges,
            "in_edges": in_edges,
            "out_nb_sets": out_nb_sets,
            "in_nb_sets": in_nb_sets,
            "node_baselines": node_baselines,
            "node_max_baseline": node_max_baseline,
            "subnets": subnets,
        }

    def _compute_betweenness(
        self, graph: dict, all_nb_sets: dict[str, set[str]],
    ) -> dict[str, float]:
        nodes = list(graph["nodes"])
        n = len(nodes)
        if n < 3:
            return {ip: 0.0 for ip in nodes}

        betweenness: dict[str, float] = dict.fromkeys(nodes, 0.0)
        sources = nodes if n <= 100 else random.sample(nodes, min(50, n))
        out_edges = graph["out_edges"]

        for s in sources:
            stack: list[str] = []
            pred: dict[str, list[str]] = defaultdict(list)
            sigma: dict[str, int] = defaultdict(int)
            sigma[s] = 1
            dist: dict[str, int] = defaultdict(lambda: -1)
            dist[s] = 0
            queue = deque([s])

            while queue:
                v = queue.popleft()
                stack.append(v)
                d_v = dist[v]
                for w in out_edges.get(v, {}):
                    if dist[w] < 0:
                        dist[w] = d_v + 1
                        queue.append(w)
                    if dist[w] == d_v + 1:
                        sigma[w] += sigma[v]
                        pred[w].append(v)

            delta: dict[str, float] = defaultdict(float)
            while stack:
                w = stack.pop()
                sw = sigma[w]
                if sw > 0:
                    dw = delta[w]
                    for v in pred[w]:
                        delta[v] += (sigma[v] / sw) * (1.0 + dw)
                if w != s:
                    betweenness[w] += delta[w]

        if n > 2:
            scale = 1.0 / ((n - 1) * (n - 2))
            if n > 100:
                scale *= n / len(sources)
            for ip in betweenness:
                betweenness[ip] *= scale

        return betweenness

    def _compute_clustering(
        self, graph: dict,
        out_nb_sets: dict[str, set[str]],
        all_nb_sets: dict[str, set[str]],
    ) -> dict[str, float]:
        result: dict[str, float] = {}

        for ip in graph["nodes"]:
            neighbors = all_nb_sets.get(ip, set())
            k = len(neighbors)

            if k < 2:
                result[ip] = 0.0
                continue

            if k > 500:
                result[ip] = 0.0
                continue

            links = 0
            for n1 in neighbors:
                out_of_n1 = out_nb_sets.get(n1, set())
                links += len(out_of_n1 & neighbors) - (1 if ip in out_of_n1 else 0)

            result[ip] = links / (k * (k - 1)) if k > 1 else 0.0

        return result

    def _compute_degree_stats(self, all_nb_sets: dict[str, set[str]]) -> dict[str, float]:
        if not all_nb_sets:
            return {"mean": 0.0, "std": 0.0}

        degrees = [len(nbs) for nbs in all_nb_sets.values()]
        if not degrees:
            return {"mean": 0.0, "std": 0.0}

        mean = sum(degrees) / len(degrees)
        variance = sum((d - mean) ** 2 for d in degrees) / len(degrees)
        return {"mean": mean, "std": variance ** 0.5}

    def _compute_graph_score(self, gf: dict, baseline: float) -> float:
        score = 0.0
        score += gf.get("neighbor_max_baseline", 0.0) * 0.35
        score += gf.get("subnet_anomaly_ratio", 0.0) * 0.25
        score += min(gf.get("betweenness_centrality", 0.0) * 10, 1.0) * 0.15
        score += gf.get("is_hub_node", 0.0) * 0.10
        score += (1.0 - gf.get("edge_density_local", 0.0)) * 0.15
        return min(round(score, 4), 1.0)

    @staticmethod
    def _ip_to_subnet(ip: str) -> str:
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
        return ip

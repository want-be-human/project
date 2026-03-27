"""
图结构特征构建器。
从流量批次构建临时有向图，提取节点级和边级结构特征。
纯内存计算，不依赖数据库。
"""

from collections import defaultdict

from app.core.logging import get_logger

logger = get_logger(__name__)


class GraphFeatureBuilder:
    """
    从流量批次构建有向图并提取结构特征。
    节点 = IP 地址，边 = 连接关系，边属性 = baseline_score。
    """

    GRAPH_FEATURE_NAMES: list[str] = [
        "node_degree",              # 节点度（入度+出度）
        "node_in_degree",           # 入度
        "node_out_degree",          # 出度
        "node_degree_ratio",        # 出度/入度比（入度为0时默认出度值）
        "neighbor_max_baseline",    # 邻居最高 baseline_score
        "neighbor_mean_baseline",   # 邻居平均 baseline_score
        "edge_density_local",       # 局部边密度（ego graph 实际边数/最大可能边数）
        "subnet_peer_count",        # 同子网（/24）节点数
        "subnet_anomaly_ratio",     # 同子网异常流比例（baseline_score >= 0.7）
        "is_hub_node",              # 是否为高度中心节点（度 > 均值+2σ）
        "betweenness_centrality",   # 介数中心性
        "clustering_coefficient",   # 聚类系数
    ]

    def __init__(self):
        pass

    def build_and_extract(self, flows: list[dict]) -> list[dict]:
        """
        从流量批次构建有向图，为每条 flow 提取图特征。

        写入 flow["_detection"]["graph_features"] 和
             flow["_detection"]["graph_score"]（图特征聚合分数）。

        参数：
            flows: 包含 _detection.baseline_score 的流字典列表
        返回：
            已填充图特征的流列表
        """
        if not flows:
            return flows

        # ── 构建图结构 ──
        graph = self._build_graph(flows)

        # ── 预计算全局指标 ──
        betweenness = self._compute_betweenness(graph)
        clustering = self._compute_clustering(graph)
        degree_stats = self._compute_degree_stats(graph)

        # ── 为每条 flow 提取特征 ──
        for flow in flows:
            src_ip = flow.get("src_ip", "0.0.0.0")
            dst_ip = flow.get("dst_ip", "0.0.0.0")
            baseline = flow.get("_detection", {}).get("baseline_score", 0.0)

            # 以源 IP 为主节点提取特征
            gf = self._extract_node_features(
                graph, src_ip, betweenness, clustering, degree_stats
            )

            # 补充目标节点信息作为辅助
            dst_features = self._extract_node_features(
                graph, dst_ip, betweenness, clustering, degree_stats
            )
            # 取源和目标的较高风险值
            gf["neighbor_max_baseline"] = max(
                gf["neighbor_max_baseline"],
                dst_features.get("neighbor_max_baseline", 0.0),
            )

            det = flow.setdefault("_detection", {})
            det["graph_features"] = gf

            # 图特征聚合分数：综合度异常、邻居风险、中心性
            det["graph_score"] = self._compute_graph_score(gf, baseline)

        logger.info(
            "GraphFeatureBuilder 完成: %d 条流, %d 个节点, %d 条边",
            len(flows),
            len(graph["nodes"]),
            sum(len(targets) for targets in graph["out_edges"].values()),
        )
        return flows

    def _build_graph(self, flows: list[dict]) -> dict:
        """
        构建轻量级有向图数据结构。

        返回：
            {
                "nodes": set[str],                          # 所有 IP
                "out_edges": dict[str, dict[str, list]],    # src -> {dst: [baseline_scores]}
                "in_edges": dict[str, dict[str, list]],     # dst -> {src: [baseline_scores]}
                "node_baselines": dict[str, list[float]],   # IP -> 关联流的 baseline_scores
                "subnets": dict[str, set[str]],             # /24子网 -> IP集合
            }
        """
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

            # 子网分组（/24）
            subnets[self._ip_to_subnet(src)].add(src)
            subnets[self._ip_to_subnet(dst)].add(dst)

        return {
            "nodes": nodes,
            "out_edges": out_edges,
            "in_edges": in_edges,
            "node_baselines": node_baselines,
            "subnets": subnets,
        }

    def _extract_node_features(
        self,
        graph: dict,
        ip: str,
        betweenness: dict[str, float],
        clustering: dict[str, float],
        degree_stats: dict,
    ) -> dict[str, float]:
        """提取单个节点的图结构特征。"""
        out_neighbors = set(graph["out_edges"].get(ip, {}).keys())
        in_neighbors = set(graph["in_edges"].get(ip, {}).keys())
        all_neighbors = out_neighbors | in_neighbors

        out_degree = len(out_neighbors)
        in_degree = len(in_neighbors)
        degree = len(all_neighbors)

        # ── 邻居 baseline 统计 ──
        neighbor_baselines = []
        for nb in all_neighbors:
            scores = graph["node_baselines"].get(nb, [])
            if scores:
                neighbor_baselines.append(max(scores))

        neighbor_max = max(neighbor_baselines) if neighbor_baselines else 0.0
        neighbor_mean = (
            sum(neighbor_baselines) / len(neighbor_baselines)
            if neighbor_baselines else 0.0
        )

        # ── 局部边密度（ego graph）──
        if degree >= 2:
            # ego graph 中邻居之间的实际边数
            ego_edges = 0
            for n1 in all_neighbors:
                for n2 in all_neighbors:
                    if n1 != n2 and n2 in graph["out_edges"].get(n1, {}):
                        ego_edges += 1
            max_possible = degree * (degree - 1)  # 有向图最大边数
            edge_density = ego_edges / max_possible if max_possible > 0 else 0.0
        else:
            edge_density = 0.0

        # ── 子网特征 ──
        subnet = self._ip_to_subnet(ip)
        subnet_peers = graph["subnets"].get(subnet, set())
        subnet_peer_count = len(subnet_peers)

        # 同子网异常比例
        anomaly_count = 0
        total_in_subnet = 0
        for peer in subnet_peers:
            scores = graph["node_baselines"].get(peer, [])
            if scores:
                total_in_subnet += 1
                if max(scores) >= 0.7:
                    anomaly_count += 1
        subnet_anomaly_ratio = (
            anomaly_count / total_in_subnet if total_in_subnet > 0 else 0.0
        )

        # ── hub 节点判定 ──
        mean_deg = degree_stats.get("mean", 0)
        std_deg = degree_stats.get("std", 0)
        is_hub = 1.0 if degree > mean_deg + 2 * std_deg and degree > 3 else 0.0

        return {
            "node_degree": float(degree),
            "node_in_degree": float(in_degree),
            "node_out_degree": float(out_degree),
            "node_degree_ratio": float(out_degree) / max(in_degree, 1),
            "neighbor_max_baseline": round(neighbor_max, 4),
            "neighbor_mean_baseline": round(neighbor_mean, 4),
            "edge_density_local": round(edge_density, 4),
            "subnet_peer_count": float(subnet_peer_count),
            "subnet_anomaly_ratio": round(subnet_anomaly_ratio, 4),
            "is_hub_node": is_hub,
            "betweenness_centrality": round(betweenness.get(ip, 0.0), 6),
            "clustering_coefficient": round(clustering.get(ip, 0.0), 4),
        }

    def _compute_betweenness(self, graph: dict) -> dict[str, float]:
        """
        计算近似介数中心性。
        对大图使用采样近似（节点数 > 100 时随机采样 50 个源节点）。
        """
        nodes = list(graph["nodes"])
        n = len(nodes)
        if n < 3:
            return {ip: 0.0 for ip in nodes}

        betweenness: dict[str, float] = {ip: 0.0 for ip in nodes}

        # BFS 最短路径计数
        import random
        sources = nodes if n <= 100 else random.sample(nodes, min(50, n))

        for s in sources:
            # BFS
            stack: list[str] = []
            pred: dict[str, list[str]] = {ip: [] for ip in nodes}
            sigma: dict[str, int] = {ip: 0 for ip in nodes}
            sigma[s] = 1
            dist: dict[str, int] = {ip: -1 for ip in nodes}
            dist[s] = 0
            queue = [s]

            while queue:
                v = queue.pop(0)
                stack.append(v)
                for w in graph["out_edges"].get(v, {}):
                    if dist[w] < 0:
                        dist[w] = dist[v] + 1
                        queue.append(w)
                    if dist[w] == dist[v] + 1:
                        sigma[w] += sigma[v]
                        pred[w].append(v)

            # 反向累积
            delta: dict[str, float] = {ip: 0.0 for ip in nodes}
            while stack:
                w = stack.pop()
                for v in pred[w]:
                    if sigma[w] > 0:
                        delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
                if w != s:
                    betweenness[w] += delta[w]

        # 归一化
        if n > 2:
            scale = 1.0 / ((n - 1) * (n - 2))
            if n > 100:
                scale *= n / len(sources)  # 采样补偿
            for ip in betweenness:
                betweenness[ip] *= scale

        return betweenness

    def _compute_clustering(self, graph: dict) -> dict[str, float]:
        """计算每个节点的聚类系数（无向化处理）。"""
        result: dict[str, float] = {}

        for ip in graph["nodes"]:
            out_nb = set(graph["out_edges"].get(ip, {}).keys())
            in_nb = set(graph["in_edges"].get(ip, {}).keys())
            neighbors = out_nb | in_nb
            k = len(neighbors)

            if k < 2:
                result[ip] = 0.0
                continue

            # 邻居之间的连接数（无向化）
            links = 0
            nb_list = list(neighbors)
            for i in range(len(nb_list)):
                for j in range(i + 1, len(nb_list)):
                    n1, n2 = nb_list[i], nb_list[j]
                    if (n2 in graph["out_edges"].get(n1, {}) or
                            n1 in graph["out_edges"].get(n2, {})):
                        links += 1

            result[ip] = (2.0 * links) / (k * (k - 1))

        return result

    def _compute_degree_stats(self, graph: dict) -> dict[str, float]:
        """计算全局度统计（均值和标准差）。"""
        degrees = []
        for ip in graph["nodes"]:
            out_nb = set(graph["out_edges"].get(ip, {}).keys())
            in_nb = set(graph["in_edges"].get(ip, {}).keys())
            degrees.append(len(out_nb | in_nb))

        if not degrees:
            return {"mean": 0.0, "std": 0.0}

        mean = sum(degrees) / len(degrees)
        variance = sum((d - mean) ** 2 for d in degrees) / len(degrees)
        return {"mean": mean, "std": variance ** 0.5}

    def _compute_graph_score(self, gf: dict, baseline: float) -> float:
        """
        图特征聚合分数。
        综合度异常、邻居风险、中心性等信号。
        """
        score = 0.0

        # 邻居风险贡献（权重 0.35）
        score += gf.get("neighbor_max_baseline", 0.0) * 0.35

        # 子网异常比例贡献（权重 0.25）
        score += gf.get("subnet_anomaly_ratio", 0.0) * 0.25

        # 介数中心性贡献（权重 0.15）——高中心性节点被攻击影响更大
        score += min(gf.get("betweenness_centrality", 0.0) * 10, 1.0) * 0.15

        # hub 节点加成（权重 0.10）
        score += gf.get("is_hub_node", 0.0) * 0.10

        # 局部边密度贡献（权重 0.15）——低密度可能是扫描行为
        # 反转：密度越低分数越高
        score += (1.0 - gf.get("edge_density_local", 0.0)) * 0.15

        return min(round(score, 4), 1.0)

    @staticmethod
    def _ip_to_subnet(ip: str) -> str:
        """将 IP 转换为 /24 子网标识。"""
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
        return ip

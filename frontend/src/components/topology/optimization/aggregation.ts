import type { GraphNode, GraphEdge } from '@/lib/api/types';
import type { OptimizedNode, OptimizedEdge, ClusterInfo } from './types';

/**
 * 从节点 ID 中提取 /24 子网前缀。
 * "ip:192.168.1.10" → "192.168.1"
 * "subnet:10.0.0.0/24" → "10.0.0"
 * 无法识别时返回 "other"
 */
export function subnetPrefix(nodeId: string): string {
  const raw = nodeId.replace(/^(ip:|subnet:)/, '');
  const m = raw.match(/^(\d+\.\d+\.\d+)/);
  return m ? m[1] : 'other';
}

/**
 * 将原始图聚合为优化图。
 * 未展开的子网组生成合成簇节点，边按簇合并。
 *
 * @param nodes       原始节点列表
 * @param edges       原始边列表
 * @param expandedClusters 已展开的簇 ID 集合
 * @returns 聚合后的节点、边和映射表
 */
export function aggregateGraph(
  nodes: GraphNode[],
  edges: GraphEdge[],
  expandedClusters: Set<string>,
): {
  nodes: OptimizedNode[];
  edges: OptimizedEdge[];
  nodeToClusterMap: Map<string, string>;
} {
  // 按子网前缀分组
  const groups = new Map<string, GraphNode[]>();
  for (const node of nodes) {
    const prefix = subnetPrefix(node.id);
    if (!groups.has(prefix)) groups.set(prefix, []);
    groups.get(prefix)!.push(node);
  }

  const resultNodes: OptimizedNode[] = [];
  const nodeToClusterMap = new Map<string, string>();

  for (const [prefix, members] of groups) {
    const clusterId = `cluster:${prefix}`;
    const isExpanded = expandedClusters.has(clusterId);

    // 单节点组或已展开的组：保留原始节点
    if (members.length <= 1 || isExpanded) {
      for (const node of members) {
        resultNodes.push({ ...node, lodLevel: 'full' });
        if (members.length > 1) {
          // 已展开簇的成员仍记录映射关系
          nodeToClusterMap.set(node.id, clusterId);
        }
      }
      continue;
    }

    // 未展开的多节点组：生成合成簇节点
    const risks = members.map(n => n.risk);
    const maxRisk = Math.max(...risks);
    const avgRisk = risks.reduce((a, b) => a + b, 0) / risks.length;

    // 计算簇关联边总权重
    const memberIdSet = new Set(members.map(n => n.id));
    let totalWeight = 0;
    for (const edge of edges) {
      if (memberIdSet.has(edge.source) || memberIdSet.has(edge.target)) {
        totalWeight += edge.weight;
      }
    }

    const clusterInfo: ClusterInfo = {
      isCluster: true,
      clusterPrefix: prefix,
      memberIds: members.map(n => n.id),
      memberCount: members.length,
      maxRisk,
      avgRisk,
      totalWeight,
      expanded: false,
    };

    resultNodes.push({
      id: clusterId,
      label: `${prefix}.* (${members.length})`,
      type: 'cluster',
      risk: maxRisk,
      cluster: clusterInfo,
      lodLevel: 'full',
    });

    // 记录每个成员到簇的映射
    for (const node of members) {
      nodeToClusterMap.set(node.id, clusterId);
    }
  }

  // 边合并：将端点解析为簇 ID，合并同源同目标的边
  const resultEdges = mergeEdges(edges, nodeToClusterMap);

  return { nodes: resultNodes, edges: resultEdges, nodeToClusterMap };
}

/**
 * 将原始图直接包装为优化图格式（不做聚合）。
 * 用于 viewLevel === 'host' 时的直通模式。
 */
export function passthroughGraph(
  nodes: GraphNode[],
  edges: GraphEdge[],
): {
  nodes: OptimizedNode[];
  edges: OptimizedEdge[];
  nodeToClusterMap: Map<string, string>;
} {
  const optimizedNodes: OptimizedNode[] = nodes.map(n => ({
    ...n,
    lodLevel: 'full' as const,
  }));

  const optimizedEdges: OptimizedEdge[] = edges.map(e => ({
    ...e,
    isMerged: false,
    mergedCount: 1,
    mergedEdgeIds: [e.id],
    visibility: 'full' as const,
  }));

  return {
    nodes: optimizedNodes,
    edges: optimizedEdges,
    nodeToClusterMap: new Map(),
  };
}

// ── 内部：边合并 ──

/**
 * 将边的端点通过 nodeToClusterMap 解析，合并同源同目标的边。
 * 簇内部边（source 和 target 解析到同一簇）标记为 intra-cluster。
 */
function mergeEdges(
  edges: GraphEdge[],
  nodeToClusterMap: Map<string, string>,
): OptimizedEdge[] {
  // 解析端点：如果节点属于未展开的簇，替换为簇 ID
  const resolveEndpoint = (nodeId: string): string =>
    nodeToClusterMap.get(nodeId) ?? nodeId;

  // 按 (resolvedSource, resolvedTarget) 分组（无向：排序后合并）
  const buckets = new Map<string, GraphEdge[]>();
  for (const edge of edges) {
    const rs = resolveEndpoint(edge.source);
    const rt = resolveEndpoint(edge.target);

    // 簇内边：source 和 target 解析到同一簇
    // 仍然保留，但后续 edge-filter 可以隐藏
    const key = rs <= rt ? `${rs}||${rt}` : `${rt}||${rs}`;
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key)!.push(edge);
  }

  const result: OptimizedEdge[] = [];
  for (const [key, group] of buckets) {
    const [rs, rt] = key.split('||');

    if (group.length === 1) {
      const e = group[0];
      result.push({
        ...e,
        source: rs,
        target: rt,
        isMerged: false,
        mergedCount: 1,
        mergedEdgeIds: [e.id],
        visibility: 'full',
      });
      continue;
    }

    // 合并多条边
    const mergedId = `merged:${rs}-${rt}`;
    const protocols = [...new Set(group.flatMap(e => e.protocols ?? []))];
    const services = deduplicateServices(group.flatMap(e => e.services ?? []));
    const alertIds = [...new Set(group.flatMap(e => e.alert_ids ?? []))];
    const allIntervals = group.flatMap(e => e.activeIntervals ?? []);
    const totalWeight = group.reduce((sum, e) => sum + e.weight, 0);
    const maxRisk = Math.max(...group.map(e => e.risk ?? 0));

    result.push({
      id: mergedId,
      source: rs,
      target: rt,
      weight: totalWeight,
      protocols,
      services,
      alert_ids: alertIds,
      activeIntervals: allIntervals,
      risk: maxRisk,
      isMerged: true,
      mergedCount: group.length,
      mergedEdgeIds: group.map(e => e.id),
      visibility: 'full',
    });
  }

  return result;
}

/** 服务去重（按 proto+port） */
function deduplicateServices(
  services: Array<{ proto: string; port: number }>,
): Array<{ proto: string; port: number }> {
  const seen = new Set<string>();
  const result: Array<{ proto: string; port: number }> = [];
  for (const s of services) {
    const key = `${s.proto}:${s.port}`;
    if (!seen.has(key)) {
      seen.add(key);
      result.push(s);
    }
  }
  return result;
}

import { useMemo } from 'react';
import type { GraphNode, GraphEdge, GraphResponse } from '@/lib/api/types';

/** 节点度数、邻居、协议统计等聚合指标 */
export interface NodeMetrics {
  inDegree: number;                                          // 入度
  outDegree: number;                                         // 出度
  totalNeighbors: number;                                    // 去重邻居数
  topRiskNeighbors: Array<{ node: GraphNode; risk: number }>; // Top-N 高风险邻居
  protocolCounts: Record<string, number>;                    // 协议 → 出现次数
  servicePorts: Array<{ proto: string; port: number; count: number }>; // 服务/端口统计
  firstSeen: string | null;                                  // 最早活跃时间
  lastSeen: string | null;                                   // 最晚活跃时间
  cumulativeWeight: number;                                  // 累计流量权重
  alertIds: string[];                                        // 去重告警 ID 列表
  connectedEdges: GraphEdge[];                               // 关联边列表
}

/**
 * 根据完整图数据计算指定节点的聚合指标。
 * 所有计算均为纯前端，不依赖额外后端接口。
 */
export function useNodeMetrics(
  nodeId: string | undefined,
  graph: GraphResponse | null,
  topN: number = 5,
): NodeMetrics | null {
  return useMemo(() => {
    if (!nodeId || !graph) return null;

    const { nodes, edges } = graph;
    const nodeMap = new Map(nodes.map(n => [n.id, n]));

    // 筛选与该节点关联的所有边
    const connectedEdges = edges.filter(e => e.source === nodeId || e.target === nodeId);

    // 入度 / 出度
    let inDegree = 0;
    let outDegree = 0;
    const neighborIds = new Set<string>();

    for (const e of connectedEdges) {
      if (e.target === nodeId) {
        inDegree++;
        neighborIds.add(e.source);
      }
      if (e.source === nodeId) {
        outDegree++;
        neighborIds.add(e.target);
      }
    }

    // Top-N 高风险邻居
    const neighbors = Array.from(neighborIds)
      .map(id => nodeMap.get(id))
      .filter((n): n is GraphNode => !!n)
      .sort((a, b) => b.risk - a.risk);
    const topRiskNeighbors = neighbors.slice(0, topN).map(n => ({ node: n, risk: n.risk }));

    // 协议统计
    const protocolCounts: Record<string, number> = {};
    for (const e of connectedEdges) {
      for (const p of e.protocols ?? []) {
        protocolCounts[p] = (protocolCounts[p] || 0) + 1;
      }
    }

    // 服务/端口统计
    const svcMap = new Map<string, { proto: string; port: number; count: number }>();
    for (const e of connectedEdges) {
      for (const s of e.services ?? []) {
        const key = `${s.proto}/${s.port}`;
        const existing = svcMap.get(key);
        if (existing) {
          existing.count++;
        } else {
          svcMap.set(key, { proto: s.proto, port: s.port, count: 1 });
        }
      }
    }
    const servicePorts = Array.from(svcMap.values()).sort((a, b) => b.count - a.count);

    // First seen / Last seen（从所有关联边的 activeIntervals 取极值）
    let firstSeen: string | null = null;
    let lastSeen: string | null = null;
    for (const e of connectedEdges) {
      for (const [start, end] of e.activeIntervals ?? []) {
        if (!firstSeen || start < firstSeen) firstSeen = start;
        if (!lastSeen || end > lastSeen) lastSeen = end;
      }
    }

    // 累计流量权重
    const cumulativeWeight = connectedEdges.reduce((sum, e) => sum + e.weight, 0);

    // 去重告警 ID
    const alertSet = new Set<string>();
    for (const e of connectedEdges) {
      for (const aid of e.alert_ids ?? []) {
        alertSet.add(aid);
      }
    }
    const alertIds = Array.from(alertSet);

    return {
      inDegree,
      outDegree,
      totalNeighbors: neighborIds.size,
      topRiskNeighbors,
      protocolCounts,
      servicePorts,
      firstSeen,
      lastSeen,
      cumulativeWeight,
      alertIds,
      connectedEdges,
    };
  }, [nodeId, graph, topN]);
}

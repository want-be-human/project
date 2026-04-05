import type { ViewLevel, EdgeFilterConfig } from './types';
import { DEFAULT_EDGE_FILTER } from './types';

/**
 * 根据原始节点数量决定默认视图层级。
 * - 小图（≤30）：直接显示主机级，无需聚合
 * - 中图（31-150）：子网聚合，支持展开单个簇
 * - 大图（>150）：子网聚合 + 摘要边 + 高风险标签
 */
export function computeDefaultViewLevel(nodeCount: number): ViewLevel {
  if (nodeCount <= 30) return 'host';
  return 'subnet';
}

/**
 * 根据图规模计算默认边过滤配置。
 */
export function computeDefaultEdgeFilter(
  nodeCount: number,
  _edgeCount: number,
): EdgeFilterConfig {
  // 中/大图（>30）：隐藏簇内边
  if (nodeCount > 30) {
    return { activeOnly: false, hideIntraCluster: true };
  }
  // 小图（≤30）：不过滤
  return { ...DEFAULT_EDGE_FILTER };
}

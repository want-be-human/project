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
 * 大图使用更激进的过滤以保证可读性。
 */
export function computeDefaultEdgeFilter(
  nodeCount: number,
  _edgeCount: number,
): EdgeFilterConfig {
  // 大图（>150）：激进过滤，只显示高风险高权重边
  if (nodeCount > 150) {
    return {
      minRisk: 0.3,
      minWeight: 3,
      activeOnly: false,
      hideIntraCluster: true,
    };
  }
  // 中图（31-150）：仅隐藏簇内边
  if (nodeCount > 30) {
    return {
      minRisk: 0,
      minWeight: 0,
      activeOnly: false,
      hideIntraCluster: true,
    };
  }
  // 小图（≤30）：host 级别，不过滤
  return { ...DEFAULT_EDGE_FILTER };
}

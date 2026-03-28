import type { ViewLevel, EdgeFilterConfig } from './types';
import { DEFAULT_EDGE_FILTER } from './types';

/**
 * 根据原始节点数量决定默认视图层级。
 * - 小图（≤50）：直接显示主机级
 * - 中图（51-200）：子网聚合，支持展开单个簇
 * - 大图（>200）：子网聚合 + 摘要模式
 */
export function computeDefaultViewLevel(nodeCount: number): ViewLevel {
  if (nodeCount <= 50) return 'host';
  return 'subnet';
}

/**
 * 根据图规模计算默认边过滤配置。
 * 大图使用更激进的过滤以保证可读性。
 */
export function computeDefaultEdgeFilter(
  nodeCount: number,
  edgeCount: number,
): EdgeFilterConfig {
  // 大图：激进过滤
  if (nodeCount > 200) {
    return {
      minRisk: 0.2,
      minWeight: 5,
      activeOnly: false,
      hideIntraCluster: true,
    };
  }
  // 中图：仅隐藏簇内边
  if (nodeCount > 50) {
    return {
      minRisk: 0,
      minWeight: 0,
      activeOnly: false,
      hideIntraCluster: true,
    };
  }
  // 小图：不过滤
  return { ...DEFAULT_EDGE_FILTER };
}

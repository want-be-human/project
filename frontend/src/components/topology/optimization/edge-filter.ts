import type { OptimizedEdge, EdgeFilterConfig, EdgeVisibility } from './types';

/**
 * 判断边在指定时间点是否活跃。
 * currentTime === 0 时视为全部活跃。
 */
function isEdgeActive(edge: OptimizedEdge, currentTime: number): boolean {
  if (currentTime === 0) return true;
  return (edge.activeIntervals ?? []).some(([start, end]) => {
    const s = new Date(start).getTime();
    const e = new Date(end).getTime();
    return currentTime >= s && currentTime <= e;
  });
}

/**
 * 计算边的累计活跃时长（毫秒）。
 * 用于时间窗自适应：活跃时间占比过低的边自动弱化。
 */
function computeActiveDuration(edge: OptimizedEdge): number {
  let total = 0;
  for (const [start, end] of edge.activeIntervals ?? []) {
    const s = new Date(start).getTime();
    const e = new Date(end).getTime();
    if (e > s) total += e - s;
  }
  return total;
}

/**
 * 判断边是否为簇内部边（source 和 target 属于同一簇）。
 */
function isIntraCluster(edge: OptimizedEdge): boolean {
  return edge.source === edge.target;
}

/**
 * 计算单条边的可见性。
 * 综合考虑风险、权重、活跃性、时间窗宽度。
 *
 * @param edge            优化后的边
 * @param config          边过滤配置
 * @param currentTime     当前时间（unix ms），0 表示不过滤
 * @param timeWindowWidth 时间窗宽度（ms），用于自适应弱化
 */
export function computeEdgeVisibility(
  edge: OptimizedEdge,
  config: EdgeFilterConfig,
  currentTime: number,
  timeWindowWidth: number,
): EdgeVisibility {
  // 簇内边
  if (config.hideIntraCluster && isIntraCluster(edge)) return 'hidden';

  // 时间活跃性
  if (config.activeOnly && !isEdgeActive(edge, currentTime)) return 'hidden';

  const edgeRisk = edge.risk ?? 0;

  // 风险阈值：低于一半直接隐藏，低于阈值弱化
  if (config.minRisk > 0) {
    if (edgeRisk < config.minRisk * 0.5) return 'hidden';
    if (edgeRisk < config.minRisk) return 'dimmed';
  }

  // 权重阈值
  if (config.minWeight > 0) {
    if (edge.weight < config.minWeight * 0.5) return 'hidden';
    if (edge.weight < config.minWeight) return 'dimmed';
  }

  // 时间窗自适应：窗口越宽，短暂活跃的边越暗
  // 防止时间窗扩大时标签和边瞬间不可读
  if (timeWindowWidth > 0) {
    const activeDuration = computeActiveDuration(edge);
    const ratio = activeDuration / timeWindowWidth;
    if (ratio < 0.02) return 'hidden';   // 活跃时间不足窗口 2%
    if (ratio < 0.05) return 'dimmed';   // 活跃时间不足窗口 5%
  }

  return 'full';
}

/**
 * 批量计算所有边的可见性。
 * 返回新的边数组（visibility 已更新）。
 */
export function applyEdgeFilter(
  edges: OptimizedEdge[],
  config: EdgeFilterConfig,
  currentTime: number,
  timeWindowWidth: number,
): OptimizedEdge[] {
  return edges.map(e => ({
    ...e,
    visibility: computeEdgeVisibility(e, config, currentTime, timeWindowWidth),
  }));
}

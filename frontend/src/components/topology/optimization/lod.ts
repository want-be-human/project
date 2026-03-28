import type { NodeLOD } from './types';

/**
 * 计算两点之间的欧氏距离。
 */
function distance3D(
  a: [number, number, number],
  b: [number, number, number],
): number {
  return Math.sqrt(
    (a[0] - b[0]) ** 2 +
    (a[1] - b[1]) ** 2 +
    (a[2] - b[2]) ** 2,
  );
}

/**
 * 计算单个节点的细节层次。
 * 基于相机距离和总可见节点数的密度因子。
 * 簇节点始终至少 medium 级别（它们代表多个节点，更重要）。
 *
 * @param nodePosition      节点世界坐标
 * @param cameraPosition    相机世界坐标
 * @param totalVisibleNodes 当前可见节点总数
 * @param isCluster         是否为簇节点
 */
export function computeNodeLOD(
  nodePosition: [number, number, number],
  cameraPosition: [number, number, number],
  totalVisibleNodes: number,
  isCluster: boolean,
): NodeLOD {
  const dist = distance3D(nodePosition, cameraPosition);

  // 簇节点：始终至少 medium
  if (isCluster) {
    if (dist < 15) return 'full';
    if (dist < 30) return 'medium';
    return 'low';
  }

  // 密度因子：节点越多，LOD 降级越早
  const densityFactor = Math.max(1, totalVisibleNodes / 100);

  if (dist < 8 / densityFactor) return 'full';
  if (dist < 15 / densityFactor) return 'medium';
  if (dist < 25 / densityFactor) return 'low';
  if (dist < 40 / densityFactor) return 'dot';
  return 'hidden';
}

/**
 * 根据 LOD 级别和全局标签开关决定是否显示标签。
 * 仅 full 和 medium 级别显示标签。
 */
export function shouldShowLabel(
  lodLevel: NodeLOD,
  showLabelsGlobal: boolean,
): boolean {
  if (!showLabelsGlobal) return false;
  return lodLevel === 'full' || lodLevel === 'medium';
}

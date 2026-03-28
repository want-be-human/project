import type { LayoutConfig, LayoutResult } from './types';
import { subnetPrefix } from '../optimization/aggregation';

/**
 * 子网分簇布局。
 * 按 /24 子网前缀对节点分组，将各组排布在外环上，
 * 并把组内节点排布在更小的内环上。
 * 已聚合的簇节点（id 以 "cluster:" 开头）直接作为独立组处理。
 */
export function clusteredSubnetLayout(config: LayoutConfig): LayoutResult {
  const { nodes } = config;
  if (nodes.length === 0) return {};

  // 按子网前缀分组（簇节点使用其自身前缀）
  const groups = new Map<string, typeof nodes>();
  for (const node of nodes) {
    // 已聚合的簇节点：提取前缀避免二次分组
    const prefix = node.id.startsWith('cluster:')
      ? node.id.replace('cluster:', '')
      : subnetPrefix(node.id);
    if (!groups.has(prefix)) groups.set(prefix, []);
    groups.get(prefix)!.push(node);
  }

  const positions: LayoutResult = {};
  const groupKeys = Array.from(groups.keys()).sort();
  const groupCount = groupKeys.length;

  // 集群中心外环半径
  const outerRadius = 5 + groupCount * 3;

  groupKeys.forEach((key, gi) => {
    const members = groups.get(key)!;
    const groupAngle = (gi / groupCount) * Math.PI * 2;

    // 组中心
    const cx = Math.cos(groupAngle) * outerRadius;
    const cz = Math.sin(groupAngle) * outerRadius;

    // 组成员内环
    const innerRadius = 1 + members.length * 0.6;
    members.forEach((node, ni) => {
      const nodeAngle = (ni / members.length) * Math.PI * 2;
      positions[node.id] = [
        cx + Math.cos(nodeAngle) * innerRadius,
        (node.risk - 0.5) * 3,
        cz + Math.sin(nodeAngle) * innerRadius,
      ];
    });
  });

  return positions;
}

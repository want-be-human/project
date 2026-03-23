import type { LayoutConfig, LayoutResult } from './types';

/**
 * 从节点 ID 中提取 /24 子网前缀。
 * "ip:192.168.1.10" → "192.168.1"
 * "subnet:10.0.0.0/24" → "10.0.0"
 */
function subnetPrefix(nodeId: string): string {
  const raw = nodeId.replace(/^(ip:|subnet:)/, '');
  const m = raw.match(/^(\d+\.\d+\.\d+)/);
  return m ? m[1] : 'other';
}

/**
 * 子网分簇布局。
 * 按 /24 子网前缀对节点分组，将各组排布在外环上，
 * 并把组内节点排布在更小的内环上。
 */
export function clusteredSubnetLayout(config: LayoutConfig): LayoutResult {
  const { nodes } = config;
  if (nodes.length === 0) return {};

  // 按子网前缀分组
  const groups = new Map<string, typeof nodes>();
  for (const node of nodes) {
    const prefix = subnetPrefix(node.id);
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

import type { LayoutConfig, LayoutResult } from './types';

/**
 * Extract /24 subnet prefix from a node ID.
 * "ip:192.168.1.10" → "192.168.1"
 * "subnet:10.0.0.0/24" → "10.0.0"
 */
function subnetPrefix(nodeId: string): string {
  const raw = nodeId.replace(/^(ip:|subnet:)/, '');
  const m = raw.match(/^(\d+\.\d+\.\d+)/);
  return m ? m[1] : 'other';
}

/**
 * Clustered-subnet layout.
 * Groups nodes by /24 subnet prefix, arranges groups on a ring,
 * and places nodes within each group in a smaller ring.
 */
export function clusteredSubnetLayout(config: LayoutConfig): LayoutResult {
  const { nodes } = config;
  if (nodes.length === 0) return {};

  // Group by subnet prefix
  const groups = new Map<string, typeof nodes>();
  for (const node of nodes) {
    const prefix = subnetPrefix(node.id);
    if (!groups.has(prefix)) groups.set(prefix, []);
    groups.get(prefix)!.push(node);
  }

  const positions: LayoutResult = {};
  const groupKeys = Array.from(groups.keys()).sort();
  const groupCount = groupKeys.length;

  // Outer ring radius for cluster centres
  const outerRadius = 5 + groupCount * 3;

  groupKeys.forEach((key, gi) => {
    const members = groups.get(key)!;
    const groupAngle = (gi / groupCount) * Math.PI * 2;

    // Group centre
    const cx = Math.cos(groupAngle) * outerRadius;
    const cz = Math.sin(groupAngle) * outerRadius;

    // Inner ring for group members
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

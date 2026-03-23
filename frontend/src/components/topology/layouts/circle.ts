import type { LayoutConfig, LayoutResult } from './types';

/**
 * Circle 布局：在 XZ 平面上进行确定性排布，Y 轴由风险值决定。
 * 从原始 Topology3D.tsx 的 computeLayout() 中提取。
 */
export function circleLayout(config: LayoutConfig): LayoutResult {
  const { nodes } = config;
  const positions: LayoutResult = {};
  const n = nodes.length;
  if (n === 0) return positions;

  nodes.forEach((node, i) => {
    const angle = (i / n) * Math.PI * 2;
    const radius = 4 + n * 0.5;
    positions[node.id] = [
      Math.cos(angle) * radius,
      (node.risk - 0.5) * 3, // Y 轴基于风险值
      Math.sin(angle) * radius,
    ];
  });
  return positions;
}

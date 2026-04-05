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

  // 最小间距法：半径刚好让相邻节点不重叠
  const minSpacing = 2.0; // 节点视觉尺寸约 2 单位
  const radius = Math.max((minSpacing * n) / (2 * Math.PI), 3);

  nodes.forEach((node, i) => {
    const angle = (i / n) * Math.PI * 2;
    positions[node.id] = [
      Math.cos(angle) * radius,
      (node.risk - 0.5) * 3, // Y 轴基于风险值
      Math.sin(angle) * radius,
    ];
  });
  return positions;
}

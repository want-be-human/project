import type { LayoutConfig, LayoutResult } from './types';

/**
 * Circle layout: deterministic placement on XZ plane with Y based on risk.
 * Extracted from original Topology3D.tsx computeLayout().
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
      (node.risk - 0.5) * 3, // Y based on risk
      Math.sin(angle) * radius,
    ];
  });
  return positions;
}

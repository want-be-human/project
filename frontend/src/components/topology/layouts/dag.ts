import type { LayoutConfig, LayoutResult } from './types';
import { forceLayout } from './force';

/**
 * DAG (directed acyclic graph) layout using Kahn topological sort.
 * X axis = layer depth, Y axis = risk, Z axis = spread within layer.
 * Falls back to force layout when a cycle is detected.
 */
export function dagLayout(config: LayoutConfig): LayoutResult {
  const { nodes, edges } = config;
  if (nodes.length === 0) return {};

  const nodeSet = new Set(nodes.map((n) => n.id));

  // Build adjacency & in-degree
  const adj = new Map<string, string[]>();
  const inDeg = new Map<string, number>();
  for (const n of nodes) {
    adj.set(n.id, []);
    inDeg.set(n.id, 0);
  }
  for (const e of edges) {
    if (!nodeSet.has(e.source) || !nodeSet.has(e.target)) continue;
    if (e.source === e.target) continue;
    adj.get(e.source)!.push(e.target);
    inDeg.set(e.target, (inDeg.get(e.target) ?? 0) + 1);
  }

  // Kahn's algorithm
  const queue: string[] = [];
  for (const [id, deg] of inDeg) {
    if (deg === 0) queue.push(id);
  }

  const order: string[] = [];
  const depth = new Map<string, number>();

  while (queue.length > 0) {
    const cur = queue.shift()!;
    order.push(cur);
    const d = depth.get(cur) ?? 0;
    for (const next of adj.get(cur) ?? []) {
      const nd = (depth.get(next) ?? 0);
      depth.set(next, Math.max(nd, d + 1));
      inDeg.set(next, (inDeg.get(next) ?? 1) - 1);
      if (inDeg.get(next) === 0) queue.push(next);
    }
  }

  // Cycle detected — fall back to force
  if (order.length < nodes.length) {
    return forceLayout(config);
  }

  // Group nodes by layer
  const riskMap = new Map(nodes.map((n) => [n.id, n.risk]));
  const layers = new Map<number, string[]>();
  let maxDepth = 0;
  for (const id of order) {
    const d = depth.get(id) ?? 0;
    if (d > maxDepth) maxDepth = d;
    if (!layers.has(d)) layers.set(d, []);
    layers.get(d)!.push(id);
  }

  const positions: LayoutResult = {};
  const layerSpacingX = 5;

  for (const [d, ids] of layers) {
    const count = ids.length;
    ids.forEach((id, i) => {
      const zSpread = count > 1 ? ((i / (count - 1)) - 0.5) * count * 2.5 : 0;
      const risk = riskMap.get(id) ?? 0;
      positions[id] = [
        (d - maxDepth / 2) * layerSpacingX,
        (risk - 0.5) * 3,
        zSpread,
      ];
    });
  }

  return positions;
}

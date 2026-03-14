import type { LayoutConfig, LayoutResult } from './types';
import { circleLayout } from './circle';

// d3-force-3d has no official @types — use dynamic import + manual typing
interface SimNode {
  id: string;
  x: number;
  y: number;
  z: number;
  risk: number;
}

/**
 * Force-directed 3D layout using d3-force-3d.
 * Initialises node positions from circle layout to avoid random-start jitter,
 * then runs 300 simulation ticks synchronously.
 */
export function forceLayout(config: LayoutConfig): LayoutResult {
  const { nodes, edges } = config;
  if (nodes.length === 0) return {};

  // Seed from circle layout for stability
  const seed = circleLayout(config);

  // Build simulation nodes
  const simNodes: SimNode[] = nodes.map((n) => ({
    id: n.id,
    x: seed[n.id]?.[0] ?? 0,
    y: seed[n.id]?.[1] ?? 0,
    z: seed[n.id]?.[2] ?? 0,
    risk: n.risk,
  }));

  // Build links
  const nodeSet = new Set(nodes.map((n) => n.id));
  const links = edges
    .filter((e) => nodeSet.has(e.source) && nodeSet.has(e.target))
    .map((e) => ({ source: e.source, target: e.target }));

  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const d3Force3d = require('d3-force-3d');
    const sim = d3Force3d
      .forceSimulation(simNodes, 3)
      .force('charge', d3Force3d.forceManyBody().strength(-120))
      .force(
        'link',
        d3Force3d
          .forceLink(links)
          .id((d: SimNode) => d.id)
          .distance(5)
      )
      .force('center', d3Force3d.forceCenter())
      .stop();

    // Run 300 ticks synchronously
    for (let i = 0; i < 300; i++) sim.tick();

    const positions: LayoutResult = {};
    for (const n of simNodes) {
      // Retain risk-based Y offset
      positions[n.id] = [n.x, (n.risk - 0.5) * 3, n.z];
    }
    return positions;
  } catch {
    // Fallback if d3-force-3d is unavailable
    return seed;
  }
}

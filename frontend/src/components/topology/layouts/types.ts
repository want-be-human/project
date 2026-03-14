import type { GraphNode, GraphEdge } from '@/lib/api/types';

/** Available layout modes */
export type LayoutMode = 'circle' | 'force' | 'dag' | 'clustered-subnet';

/** Position dictionary: nodeId → [x, y, z] */
export type LayoutResult = Record<string, [number, number, number]>;

/** Input for layout computation */
export interface LayoutConfig {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

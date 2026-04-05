import type { GraphNode, GraphEdge } from '@/lib/api/types';

/** 可用的布局模式 */
export type LayoutMode = 'circle' | 'dag' | 'clustered-subnet';

/** 坐标字典：nodeId → [x, y, z] */
export type LayoutResult = Record<string, [number, number, number]>;

/** 布局计算输入 */
export interface LayoutConfig {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

import type { GraphNode, GraphEdge, GraphResponse } from '@/lib/api/types';
import type { LayoutResult } from '../layouts/types';

// === 视图层级 ===

/** 当前图的聚合粒度 */
export type ViewLevel = 'subnet' | 'host' | 'service';

// === 节点细节层次 ===

/**
 * full:   球体 + 标签 + 风险圆盘 + 脉冲环
 * medium: 球体 + 标签
 * low:    仅球体（无标签）
 * dot:    极小点（InstancedMesh 候选）
 * hidden: 视锥外，不渲染
 */
export type NodeLOD = 'full' | 'medium' | 'low' | 'dot' | 'hidden';

/** 边可见性 */
export type EdgeVisibility = 'full' | 'dimmed' | 'hidden';

// === 聚合簇信息 ===

export interface ClusterInfo {
  isCluster: true;
  /** 子网前缀，如 "192.168.1" */
  clusterPrefix: string;
  /** 原始成员节点 ID 列表 */
  memberIds: string[];
  memberCount: number;
  /** 成员最大风险 */
  maxRisk: number;
  /** 成员平均风险 */
  avgRisk: number;
  /** 成员关联边总权重 */
  totalWeight: number;
  /** 当前是否展开 */
  expanded: boolean;
}

/** 优化后的节点：原始节点或聚合簇节点 */
export interface OptimizedNode extends GraphNode {
  /** 仅聚合簇节点有此字段 */
  cluster?: ClusterInfo;
  /** 当前细节层次 */
  lodLevel: NodeLOD;
}

/** 优化后的边：可能是合并边 */
export interface OptimizedEdge extends GraphEdge {
  /** 是否为合并边 */
  isMerged: boolean;
  /** 合并了多少条原始边 */
  mergedCount: number;
  /** 原始边 ID（用于 dry-run 映射） */
  mergedEdgeIds: string[];
  /** 当前可见性 */
  visibility: EdgeVisibility;
}

// === 包围盒与相机 ===

export interface BoundingBoxInfo {
  min: [number, number, number];
  max: [number, number, number];
  center: [number, number, number];
  /** 对角线长度 */
  diagonal: number;
}

export interface CameraLimits {
  minDistance: number;
  maxDistance: number;
  fitPosition: [number, number, number];
  fitTarget: [number, number, number];
}

export interface GridParams {
  size: number;
  divisions: number;
  positionY: number;
}

// === 边过滤配置 ===

export interface EdgeFilterConfig {
  /** 仅显示当前时间活跃的边 */
  activeOnly: boolean;
  /** 隐藏簇内部边 */
  hideIntraCluster: boolean;
}

// === 优化层输出 ===

export interface OptimizedGraph {
  nodes: OptimizedNode[];
  edges: OptimizedEdge[];
  boundingBox: BoundingBoxInfo;
  cameraLimits: CameraLimits;
  gridParams: GridParams;
  /** 原始节点 ID → 所属簇 ID 的映射 */
  nodeToClusterMap: Map<string, string>;
}

// === 优化层状态 ===

export interface OptimizationState {
  viewLevel: ViewLevel;
  expandedClusters: Set<string>;
  edgeFilter: EdgeFilterConfig;
  /** 当前相机距离（由 Scene 内部回传） */
  cameraDistance: number;
}

// === 优化层 Context 值 ===

export interface OptimizationContextValue {
  /** 优化后的图数据 */
  optimizedGraph: OptimizedGraph | null;
  /** 当前优化层状态 */
  state: OptimizationState;
  /** 设置视图层级 */
  setViewLevel: (level: ViewLevel) => void;
  /** 展开指定簇 */
  expandCluster: (clusterId: string) => void;
  /** 折叠指定簇 */
  collapseCluster: (clusterId: string) => void;
  /** 切换簇展开/折叠 */
  toggleCluster: (clusterId: string) => void;
  /** 展开所有簇 */
  expandAll: () => void;
  /** 折叠所有簇 */
  collapseAll: () => void;
  /** 更新边过滤配置 */
  setEdgeFilter: (config: Partial<EdgeFilterConfig>) => void;
  /** 更新相机距离（由 Scene 回传） */
  setCameraDistance: (distance: number) => void;
  /** 获取某个簇的成员节点 */
  getClusterMembers: (clusterId: string) => GraphNode[];
}

/** 默认边过滤配置 */
export const DEFAULT_EDGE_FILTER: EdgeFilterConfig = {
  activeOnly: false,
  hideIntraCluster: false,
};

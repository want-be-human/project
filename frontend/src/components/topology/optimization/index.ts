// 大图共享优化层 — 公共导出

export type {
  ViewLevel,
  NodeLOD,
  EdgeVisibility,
  ClusterInfo,
  OptimizedNode,
  OptimizedEdge,
  BoundingBoxInfo,
  CameraLimits,
  GridParams,
  EdgeFilterConfig,
  OptimizedGraph,
  OptimizationState,
  OptimizationContextValue,
} from './types';

export { DEFAULT_EDGE_FILTER } from './types';

export { subnetPrefix, aggregateGraph, passthroughGraph } from './aggregation';
export { computeEdgeVisibility, applyEdgeFilter } from './edge-filter';
export { computeNodeLOD, shouldShowLabel } from './lod';
export { computeBoundingBox, computeCameraLimits, computeGridParams } from './bounding-box';
export { computeDefaultViewLevel, computeDefaultEdgeFilter } from './view-strategy';
export { mapDryRunSets } from './dry-run-mapping';
export type { ClusterDryRunStatus, MappedDryRunSets } from './dry-run-mapping';

export { OptimizationProvider, useOptimization } from './context';

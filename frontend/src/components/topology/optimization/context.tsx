'use client';

import {
  createContext,
  useContext,
  useState,
  useMemo,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react';
import type { GraphNode, GraphEdge, GraphResponse } from '@/lib/api/types';
import type {
  ViewLevel,
  EdgeFilterConfig,
  OptimizationState,
  OptimizationContextValue,
  OptimizedGraph,
} from './types';
import { DEFAULT_EDGE_FILTER } from './types';
import { computeDefaultViewLevel, computeDefaultEdgeFilter } from './view-strategy';
import { aggregateGraph, passthroughGraph } from './aggregation';
import { applyEdgeFilter } from './edge-filter';
import { computeBoundingBox, computeCameraLimits, computeGridParams } from './bounding-box';

const OptimizationContext = createContext<OptimizationContextValue | null>(null);

interface OptimizationProviderProps {
  /** 当前展示用图（displayGraph） */
  graph: GraphResponse | null;
  /** 当前时间（unix ms） */
  currentTime: number;
  /** 时间窗起点（unix ms） */
  timeWindowStart: number;
  /** 时间窗终点（unix ms） */
  timeWindowEnd: number;
  children: ReactNode;
}

/**
 * 大图共享优化层 Provider。
 * 在原始图数据与布局/渲染管线之间提供聚合、过滤、LOD 等能力。
 * 包裹在 TopologyPage 中，所有子组件通过 useOptimization() 消费。
 */
export function OptimizationProvider({
  graph,
  currentTime,
  timeWindowStart,
  timeWindowEnd,
  children,
}: OptimizationProviderProps) {
  // 根据节点数量计算默认视图层级
  const defaultViewLevel = useMemo(
    () => graph ? computeDefaultViewLevel(graph.nodes.length) : 'host' as ViewLevel,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [graph?.nodes.length],
  );

  const [viewLevel, setViewLevel] = useState<ViewLevel>(defaultViewLevel);
  const [expandedClusters, setExpandedClusters] = useState<Set<string>>(new Set());
  const [edgeFilter, setEdgeFilterState] = useState<EdgeFilterConfig>(DEFAULT_EDGE_FILTER);
  const [cameraDistance, setCameraDistance] = useState(20);

  // graph 变化时重置状态
  useEffect(() => {
    if (!graph) return;
    setViewLevel(computeDefaultViewLevel(graph.nodes.length));
    setExpandedClusters(new Set());
    setEdgeFilterState(computeDefaultEdgeFilter(graph.nodes.length, graph.edges.length));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph?.nodes.length]);

  // 聚合计算
  const aggregated = useMemo(() => {
    if (!graph) return null;
    if (viewLevel === 'host') {
      return passthroughGraph(graph.nodes, graph.edges);
    }
    return aggregateGraph(graph.nodes, graph.edges, expandedClusters);
  }, [graph, viewLevel, expandedClusters]);

  // 边过滤
  const timeWindowWidth = timeWindowEnd - timeWindowStart;
  const filteredEdges = useMemo(() => {
    if (!aggregated) return null;
    return applyEdgeFilter(aggregated.edges, edgeFilter, currentTime, timeWindowWidth);
  }, [aggregated, edgeFilter, currentTime, timeWindowWidth]);

  // 组装优化图（包围盒和相机限制在布局计算后由 Scene 补充，这里先用占位值）
  const optimizedGraph = useMemo<OptimizedGraph | null>(() => {
    if (!aggregated || !filteredEdges) return null;

    // 占位包围盒（实际值在 Scene 中 computeLayout 后计算）
    const placeholderBB = {
      min: [0, 0, 0] as [number, number, number],
      max: [0, 0, 0] as [number, number, number],
      center: [0, 0, 0] as [number, number, number],
      diagonal: 10,
    };

    return {
      nodes: aggregated.nodes,
      edges: filteredEdges,
      boundingBox: placeholderBB,
      cameraLimits: computeCameraLimits(placeholderBB),
      gridParams: computeGridParams(placeholderBB),
      nodeToClusterMap: aggregated.nodeToClusterMap,
    };
  }, [aggregated, filteredEdges]);

  // ── 操作回调 ──

  const expandCluster = useCallback((clusterId: string) => {
    setExpandedClusters(prev => {
      const next = new Set(prev);
      next.add(clusterId);
      return next;
    });
  }, []);

  const collapseCluster = useCallback((clusterId: string) => {
    setExpandedClusters(prev => {
      const next = new Set(prev);
      next.delete(clusterId);
      return next;
    });
  }, []);

  const toggleCluster = useCallback((clusterId: string) => {
    setExpandedClusters(prev => {
      const next = new Set(prev);
      if (next.has(clusterId)) {
        next.delete(clusterId);
      } else {
        next.add(clusterId);
      }
      return next;
    });
  }, []);

  const expandAll = useCallback(() => {
    if (!aggregated) return;
    const allClusterIds = new Set(
      aggregated.nodes
        .filter(n => n.cluster?.isCluster)
        .map(n => n.id),
    );
    setExpandedClusters(allClusterIds);
  }, [aggregated]);

  const collapseAll = useCallback(() => {
    setExpandedClusters(new Set());
  }, []);

  const setEdgeFilter = useCallback((config: Partial<EdgeFilterConfig>) => {
    setEdgeFilterState(prev => ({ ...prev, ...config }));
  }, []);

  const getClusterMembers = useCallback((clusterId: string): GraphNode[] => {
    if (!graph) return [];
    const node = aggregated?.nodes.find(n => n.id === clusterId);
    if (!node?.cluster) return [];
    const memberIdSet = new Set(node.cluster.memberIds);
    return graph.nodes.filter(n => memberIdSet.has(n.id));
  }, [graph, aggregated]);

  // ── Context 值 ──

  const state: OptimizationState = useMemo(() => ({
    viewLevel,
    expandedClusters,
    edgeFilter,
    cameraDistance,
  }), [viewLevel, expandedClusters, edgeFilter, cameraDistance]);

  const contextValue = useMemo<OptimizationContextValue>(() => ({
    optimizedGraph,
    state,
    setViewLevel,
    expandCluster,
    collapseCluster,
    toggleCluster,
    expandAll,
    collapseAll,
    setEdgeFilter,
    setCameraDistance,
    getClusterMembers,
  }), [
    optimizedGraph,
    state,
    expandCluster,
    collapseCluster,
    toggleCluster,
    expandAll,
    collapseAll,
    setEdgeFilter,
    getClusterMembers,
  ]);

  return (
    <OptimizationContext.Provider value={contextValue}>
      {children}
    </OptimizationContext.Provider>
  );
}

/**
 * 消费优化层 Context。
 * 必须在 OptimizationProvider 内部使用。
 */
export function useOptimization(): OptimizationContextValue {
  const ctx = useContext(OptimizationContext);
  if (!ctx) {
    throw new Error('useOptimization 必须在 OptimizationProvider 内使用');
  }
  return ctx;
}

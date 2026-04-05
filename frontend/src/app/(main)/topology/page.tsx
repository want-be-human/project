'use client';

import { useEffect, useState, useCallback, useMemo, useRef, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import dynamic from 'next/dynamic';
import { api } from '@/lib/api';
import { GraphResponse, GraphNode, GraphEdge, DryRunResult } from '@/lib/api/types';
import { RefreshCw } from 'lucide-react';
import { useTranslations } from 'next-intl';
import TopologyToolbar from '@/components/topology/TopologyToolbar';
import TimeSlider from '@/components/topology/TimeSlider';
import SideInspector from '@/components/topology/SideInspector';
import TopologyLegend from '@/components/topology/TopologyLegend';
import DryRunOverlay from '@/components/topology/DryRunOverlay';
import type { LayoutMode } from '@/components/topology/layouts/types';
import type { CameraPreset } from '@/components/topology/CameraController';
import { OptimizationProvider } from '@/components/topology/optimization';
import { useOptimization } from '@/components/topology/optimization/context';

// 桥接组件：在 OptimizationProvider 内部消费 context，向 TopologyToolbar 传递优化层 props
function OptimizedToolbar(props: React.ComponentProps<typeof TopologyToolbar>) {
  const { state, setViewLevel, expandAll, collapseAll } = useOptimization();
  return (
    <TopologyToolbar
      {...props}
      viewLevel={state.viewLevel}
      onViewLevelChange={setViewLevel}
      onExpandAll={expandAll}
      onCollapseAll={collapseAll}
    />
  );
}

// 桥接组件：向 SideInspector 传递优化层统计信息
function OptimizedSideInspector(props: React.ComponentProps<typeof SideInspector>) {
  const { optimizedGraph, state } = useOptimization();
  const clusterCount = optimizedGraph?.nodes.filter(n => n.cluster?.isCluster).length ?? 0;
  const expandedClusterCount = state.expandedClusters.size;
  return (
    <SideInspector
      {...props}
      viewLevel={state.viewLevel}
      clusterCount={clusterCount}
      expandedClusterCount={expandedClusterCount}
    />
  );
}

// dry-run 视图模式：before（原始图）/ after（变更后图）/ diff（差异高亮）
export type DryRunViewMode = 'before' | 'after' | 'diff';

// ── ISO UTC ↔ datetime-local 转换工具 ──

/** ISO UTC 字符串 → datetime-local 输入值（本地时区，YYYY-MM-DDTHH:mm） */
function isoToLocalInput(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** datetime-local 输入值（本地时区）→ ISO UTC 字符串 */
function localInputToIso(local: string): string {
  if (!local) return '';
  const d = new Date(local);
  if (isNaN(d.getTime())) return '';
  return d.toISOString();
}

// 3D 画布动态导入（不兼容 SSR）
const Topology3D = dynamic(() => import('@/components/topology/Topology3D'), {
  ssr: false,
  loading: () => (
    <div className="flex-grow flex items-center justify-center bg-slate-50">
      <RefreshCw className="w-6 h-6 animate-spin text-gray-400" />
    </div>
  ),
});

/** 本地构建 after 图（后端未返回 graph_after 时的回退方案） */
function buildLocalAfterGraph(graph: GraphResponse, dr: DryRunResult): GraphResponse {
  const removedN = new Set(dr.impact?.removed_node_ids ?? []);
  const removedE = new Set(dr.impact?.removed_edge_ids ?? []);
  const nd = dr.impact?.node_risk_deltas ?? {};
  const ed = dr.impact?.edge_weight_deltas ?? {};

  const nodes = graph.nodes
    .filter(n => !removedN.has(n.id))
    .map(n => nd[n.id] !== undefined ? { ...n, risk: nd[n.id] } : n);
  const edges = graph.edges
    .filter(e => !removedE.has(e.id))
    .map(e => ed[e.id] !== undefined ? { ...e, weight: ed[e.id] } : e);

  return { ...graph, nodes, edges };
}

/** 在原始图上叠加 deltas（diff 模式用） */
function applyDeltasToGraph(graph: GraphResponse, dr: DryRunResult): GraphResponse {
  const nd = dr.impact?.node_risk_deltas;
  const ed = dr.impact?.edge_weight_deltas;
  if (!nd && !ed) return graph;

  const nodes = nd
    ? graph.nodes.map(n => nd[n.id] !== undefined ? { ...n, risk: nd[n.id] } : n)
    : graph.nodes;
  const edges = ed
    ? graph.edges.map(e => ed[e.id] !== undefined ? { ...e, weight: ed[e.id] } : e)
    : graph.edges;

  return { ...graph, nodes, edges };
}

function TopologyInner() {
  const t = useTranslations('topology');
  const searchParams = useSearchParams();
  const highlightAlertId = searchParams.get('highlightAlertId');
  const dryRunId = searchParams.get('dryRunId');
  const urlStart = searchParams.get('start');
  const urlEnd = searchParams.get('end');
  const urlMode = searchParams.get('mode');

  // live topology 图（无 dry-run 时使用，或作为 dry-run 快照缺失时的回退）
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<'ip' | 'subnet'>((urlMode === 'subnet' ? 'subnet' : 'ip'));
  const [currentTime, setCurrentTime] = useState(0);

  // 时间过滤器：存储 ISO UTC 字符串
  const [filterStart, setFilterStart] = useState(urlStart || '');
  const [filterEnd, setFilterEnd] = useState(urlEnd || '');

  // Dry-run 相关状态
  const [dryRunResult, setDryRunResult] = useState<DryRunResult | null>(null);
  const [dryRunLoading, setDryRunLoading] = useState(false);
  const [dryRunNotFound, setDryRunNotFound] = useState(false);

  // dry-run 视图模式（默认 diff）
  const [viewMode, setViewMode] = useState<DryRunViewMode>('diff');

  // 侧边检查器选中状态
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);

  // 布局模式（用户直接切换）
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('circle');
  // 标签/箭头策略
  const showLabels = true;
  const showArrows = layoutMode === 'dag';
  const riskHeatEnabled = false;

  const [cameraPreset, setCameraPreset] = useState<CameraPreset>(null);
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null);

  // 切换布局模式时自动 fit 相机
  const prevLayoutMode = useRef(layoutMode);
  useEffect(() => {
    if (prevLayoutMode.current !== layoutMode) {
      prevLayoutMode.current = layoutMode;
      setCameraPreset('fit');
    }
  }, [layoutMode]);

  // searchParams 变化时同步时间过滤器
  useEffect(() => {
    const s = searchParams.get('start');
    const e = searchParams.get('end');
    if (s && s !== filterStart) setFilterStart(s);
    if (e && e !== filterEnd) setFilterEnd(e);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // 存在 dryRunId 时拉取 DryRunResult
  useEffect(() => {
    if (!dryRunId) {
      setDryRunResult(null);
      setDryRunNotFound(false);
      return;
    }
    setDryRunLoading(true);
    setDryRunNotFound(false);
    api.getDryRun(dryRunId)
      .then(result => {
        setDryRunResult(result);
      })
      .catch(e => {
        console.error('Failed to load dry-run result', e);
        setDryRunResult(null);
        setDryRunNotFound(true);
      })
      .finally(() => setDryRunLoading(false));
  }, [dryRunId]);

  // dry-run 加载完成后，用其窗口回填时间过滤器（如果 URL 没有 start/end）
  const dryRunBackfilled = useRef(false);
  useEffect(() => {
    if (!dryRunResult || dryRunBackfilled.current) return;
    dryRunBackfilled.current = true;
    if (!filterStart && dryRunResult.dry_run_start) {
      setFilterStart(dryRunResult.dry_run_start);
    }
    if (!filterEnd && dryRunResult.dry_run_end) {
      setFilterEnd(dryRunResult.dry_run_end);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dryRunResult]);

  // ── 直接使用后端返回的精确影响 ID 集合（不再从 alternative_paths 派生）──

  const removedNodeIds = useMemo(() => {
    if (!dryRunResult?.impact?.removed_node_ids) return undefined;
    const s = new Set(dryRunResult.impact.removed_node_ids);
    return s.size > 0 ? s : undefined;
  }, [dryRunResult]);

  const removedEdgeIds = useMemo(() => {
    if (!dryRunResult?.impact?.removed_edge_ids) return undefined;
    const s = new Set(dryRunResult.impact.removed_edge_ids);
    return s.size > 0 ? s : undefined;
  }, [dryRunResult]);

  const affectedNodeIds = useMemo(() => {
    if (!dryRunResult?.impact?.affected_node_ids) return undefined;
    const s = new Set(dryRunResult.impact.affected_node_ids);
    return s.size > 0 ? s : undefined;
  }, [dryRunResult]);

  const affectedEdgeIds = useMemo(() => {
    if (!dryRunResult?.impact?.affected_edge_ids) return undefined;
    const s = new Set(dryRunResult.impact.affected_edge_ids);
    return s.size > 0 ? s : undefined;
  }, [dryRunResult]);

  // 替代路径节点 ID（仅用于绿色绕行高亮，不作为"受影响"判定依据）
  const altPathNodeIds = useMemo(() => {
    if (!dryRunResult?.alternative_paths) return undefined;
    const s = new Set<string>();
    dryRunResult.alternative_paths.forEach(p => {
      p.path?.forEach(id => s.add(id));
    });
    return s.size > 0 ? s : undefined;
  }, [dryRunResult]);

  // dry-run 的 before 图快照
  const dryRunBefore = dryRunResult?.graph_before ?? null;

  // ── 根据 viewMode 生成展示用图（dry-run 快照优先，不依赖 live graph）──
  const displayGraph = useMemo<GraphResponse | null>(() => {
    // 无 dry-run 时显示 live graph
    if (!dryRunResult) return graph;

    switch (viewMode) {
      case 'before':
        // 优先使用 dry-run 快照的 before 图
        return dryRunBefore ?? graph;

      case 'after': {
        // 优先使用后端返回的 graph_after
        if (dryRunResult.graph_after) return dryRunResult.graph_after;
        // 回退：基于 before 快照本地计算
        const base = dryRunBefore ?? graph;
        return base ? buildLocalAfterGraph(base, dryRunResult) : null;
      }

      case 'diff': {
        // 基于 before 快照应用 deltas
        const diffBase = dryRunBefore ?? graph;
        return diffBase ? applyDeltasToGraph(diffBase, dryRunResult) : null;
      }

      default:
        return graph;
    }
  }, [graph, dryRunResult, dryRunBefore, viewMode]);

  // 图数据首次就绪时触发 fit（数据加载完成后 positions 才有意义）
  const graphFitted = useRef(false);
  useEffect(() => {
    if (displayGraph && !graphFitted.current) {
      graphFitted.current = true;
      setCameraPreset('fit');
    }
  }, [displayGraph]);

  // 保留原始值映射，供 SideInspector 展示 before→after
  const originalValues = useMemo(() => {
    const base = dryRunBefore ?? graph;
    if (!base || !dryRunResult) return undefined;
    const nodeDeltas = dryRunResult.impact?.node_risk_deltas;
    const edgeDeltas = dryRunResult.impact?.edge_weight_deltas;
    if (!nodeDeltas && !edgeDeltas) return undefined;

    const nodeRisks: Record<string, number> = {};
    const edgeWeights: Record<string, number> = {};
    if (nodeDeltas) {
      base.nodes.forEach(n => {
        if (nodeDeltas[n.id] !== undefined) nodeRisks[n.id] = n.risk;
      });
    }
    if (edgeDeltas) {
      base.edges.forEach(e => {
        if (edgeDeltas[e.id] !== undefined) edgeWeights[e.id] = e.weight;
      });
    }
    return { nodeRisks, edgeWeights };
  }, [dryRunBefore, graph, dryRunResult]);

  const fetchGraph = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = { mode };
      // filterStart/filterEnd 已经是 ISO UTC 字符串，直接传递
      if (filterStart) params.start = filterStart;
      if (filterEnd) params.end = filterEnd;
      const data = await api.getGraph(params);
      setGraph(data);
      // 将 currentTime 初始化为数据窗口起点
      if (data.meta?.start) {
        setCurrentTime(new Date(data.meta.start).getTime());
      }
    } catch (e) {
      console.error('Failed to load topology', e);
    } finally {
      setLoading(false);
    }
  }, [mode, filterStart, filterEnd]);

  useEffect(() => {
    fetchGraph();
  }, [fetchGraph]);

  // TimeSlider 的时间范围：优先从 displayGraph 的 meta 获取，否则从 filterStart/filterEnd 获取
  const sliderStartTime = useMemo(() => {
    if (displayGraph?.meta?.start) return new Date(displayGraph.meta.start).getTime();
    if (filterStart) return new Date(filterStart).getTime();
    return 0;
  }, [displayGraph, filterStart]);

  const sliderEndTime = useMemo(() => {
    if (displayGraph?.meta?.end) return new Date(displayGraph.meta.end).getTime();
    if (filterEnd) return new Date(filterEnd).getTime();
    return 0;
  }, [displayGraph, filterEnd]);

  const handleClearSelection = useCallback(() => {
    setSelectedNode(null);
    setSelectedEdge(null);
  }, []);

  // ── 告警严重度映射（研判面板用） ──
  const [alertSeverityMap, setAlertSeverityMap] = useState<Record<string, 'low' | 'medium' | 'high' | 'critical'>>({});
  const alertsFetched = useRef(false);

  useEffect(() => {
    if (!displayGraph || alertsFetched.current) return;
    // 检查图中是否有告警 ID
    const hasAlerts = displayGraph.edges.some(e => (e.alert_ids ?? []).length > 0);
    if (!hasAlerts) return;
    alertsFetched.current = true;
    // 拉取告警列表，构建 id→severity 映射
    api.listAlerts({}).then((alerts) => {
      const map: Record<string, 'low' | 'medium' | 'high' | 'critical'> = {};
      for (const a of alerts) {
        if (a.id && a.severity) map[a.id] = a.severity as any;
      }
      setAlertSeverityMap(map);
    }).catch(() => { /* 静默失败，面板仍可用 */ });
  }, [displayGraph]);

  // 研判面板内交叉选中回调
  const handleInspectorSelectNode = useCallback((node: GraphNode) => {
    setSelectedNode(node);
    setSelectedEdge(null);
    setFocusNodeId(node.id);
  }, []);

  const handleInspectorSelectEdge = useCallback((edge: GraphEdge) => {
    setSelectedEdge(edge);
    setSelectedNode(null);
  }, []);

  // dry-run 产生的替代路径，用于 3D 场景渲染
  const altPaths = dryRunResult?.alternative_paths;

  // diff 模式下才传递影响集合给 3D 组件
  const isDiff = viewMode === 'diff';

  return (
    <OptimizationProvider
      graph={displayGraph}
      currentTime={currentTime}
      timeWindowStart={sliderStartTime}
      timeWindowEnd={sliderEndTime}
    >
    <div className="h-[calc(100vh-64px)] flex flex-col">
      {/* 工具栏（通过桥接组件注入优化层 props） */}
      <OptimizedToolbar
        layoutMode={layoutMode}
        onLayoutModeChange={setLayoutMode}
        highlightAlertId={highlightAlertId}
        onRefresh={fetchGraph}
        loading={loading}
        startTime={isoToLocalInput(filterStart)}
        endTime={isoToLocalInput(filterEnd)}
        onStartTimeChange={(v) => setFilterStart(localInputToIso(v))}
        onEndTimeChange={(v) => setFilterEnd(localInputToIso(v))}
        onCameraPreset={setCameraPreset}
        dryRunActive={!!dryRunResult}
      />

      {/* 主体：3D 视图 + 侧边检查器 */}
      <div className="flex-grow flex overflow-hidden">
        {/* 3D 画布区域 */}
        <div className="flex-grow flex flex-col relative">
          {loading && !displayGraph ? (
            <div className="flex-grow flex items-center justify-center bg-slate-50">
              <div className="text-gray-400 flex flex-col items-center">
                <RefreshCw className="w-8 h-8 animate-spin mb-2" />
                <p>{t('loading')}</p>
              </div>
            </div>
          ) : displayGraph ? (
            <div className="flex-grow">
              <Topology3D
                nodes={displayGraph.nodes}
                edges={displayGraph.edges}
                currentTime={currentTime}
                highlightAlertId={highlightAlertId}
                removedNodeIds={isDiff ? removedNodeIds : undefined}
                removedEdgeIds={isDiff ? removedEdgeIds : undefined}
                affectedNodeIds={isDiff ? affectedNodeIds : undefined}
                affectedEdgeIds={isDiff ? affectedEdgeIds : undefined}
                altPathNodeIds={isDiff ? altPathNodeIds : undefined}
                layoutMode={layoutMode}
                showLabels={showLabels}
                showArrows={showArrows}
                riskHeatEnabled={riskHeatEnabled}
                cameraPreset={cameraPreset}
                onCameraPresetDone={() => setCameraPreset(null)}
                focusNodeId={focusNodeId}
                onFocusDone={() => setFocusNodeId(null)}
                altPaths={isDiff ? altPaths : undefined}
                onSelectNode={(node) => {
                  setSelectedNode(node);
                  if (node !== null) setSelectedEdge(null);
                }}
                onSelectEdge={(edge) => {
                  setSelectedEdge(edge);
                  if (edge !== null) setSelectedNode(null);
                }}
              />
            </div>
          ) : (
            <div className="flex-grow flex items-center justify-center text-gray-400">
              {t('noData')}
            </div>
          )}

          {/* 图例浮层 */}
          <TopologyLegend />

          {/* Dry-Run 影响浮层（含视图切换） */}
          {dryRunId && (
            <DryRunOverlay
              result={dryRunResult}
              loading={dryRunLoading}
              notFound={dryRunNotFound}
              viewMode={viewMode}
              onViewModeChange={setViewMode}
            />
          )}

          {/* TimeSlider 浮层 */}
          {displayGraph && sliderStartTime > 0 && sliderEndTime > 0 && (
            <div className="absolute bottom-4 left-4 right-4">
              <TimeSlider
                startTime={sliderStartTime}
                endTime={sliderEndTime}
                currentTime={currentTime}
                onChange={setCurrentTime}
              />
            </div>
          )}
        </div>

        {/* 侧边检查器（研判面板，通过桥接组件注入优化层 props） */}
        <OptimizedSideInspector
          selectedNode={selectedNode}
          selectedEdge={selectedEdge}
          displayGraph={displayGraph}
          currentTime={currentTime}
          layoutMode={layoutMode}
          viewMode={dryRunResult ? viewMode : undefined}
          dryRunResult={dryRunResult}
          removedNodeIds={removedNodeIds}
          removedEdgeIds={removedEdgeIds}
          affectedNodeIds={affectedNodeIds}
          affectedEdgeIds={affectedEdgeIds}
          originalValues={originalValues}
          altPaths={altPaths}
          alertSeverityMap={alertSeverityMap}
          onClose={handleClearSelection}
          onLocateNode={(nodeId) => setFocusNodeId(nodeId)}
          onSelectNode={handleInspectorSelectNode}
          onSelectEdge={handleInspectorSelectEdge}
        />
      </div>
    </div>
    </OptimizationProvider>
  );
}

export default function TopologyPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-screen"><RefreshCw className="w-6 h-6 animate-spin text-gray-400" /></div>}>
      <TopologyInner />
    </Suspense>
  );
}

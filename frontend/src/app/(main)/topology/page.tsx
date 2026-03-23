'use client';

import { useEffect, useState, useCallback, useMemo, Suspense } from 'react';
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

// 3D 画布动态导入（不兼容 SSR）
const Topology3D = dynamic(() => import('@/components/topology/Topology3D'), {
  ssr: false,
  loading: () => (
    <div className="flex-grow flex items-center justify-center bg-slate-50">
      <RefreshCw className="w-6 h-6 animate-spin text-gray-400" />
    </div>
  ),
});

function TopologyInner() {
  const t = useTranslations('topology');
  const searchParams = useSearchParams();
  const highlightAlertId = searchParams.get('highlightAlertId');
  const dryRunId = searchParams.get('dryRunId');
  const urlStart = searchParams.get('start');
  const urlEnd = searchParams.get('end');

  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<'ip' | 'subnet'>('ip');
  const [currentTime, setCurrentTime] = useState(0);
  const [filterStart, setFilterStart] = useState(urlStart || '');
  const [filterEnd, setFilterEnd] = useState(urlEnd || '');

  // Dry-run 状态
  const [dryRunResult, setDryRunResult] = useState<DryRunResult | null>(null);
  const [dryRunLoading, setDryRunLoading] = useState(false);
  const [dryRunNotFound, setDryRunNotFound] = useState(false);

  // SideInspector 选中状态
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);

  // ── 布局与视觉增强状态 ──
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('circle');
  const [showLabels, setShowLabels] = useState(true);
  const [showArrows, setShowArrows] = useState(false);
  const [riskHeatEnabled, setRiskHeatEnabled] = useState(false);
  const [cameraPreset, setCameraPreset] = useState<CameraPreset>(null);
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null);

  // DAG 模式下自动启用箭头
  const effectiveShowArrows = layoutMode === 'dag' ? true : showArrows;

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

  // 从 dry-run 结果计算受影响的节点 ID 与边 ID
  const impactedNodeIds = useMemo(() => {
    if (!dryRunResult) return undefined;
    const ids = new Set<string>();
    dryRunResult.alternative_paths?.forEach(p => {
      if (p.from) ids.add(p.from);
      if (p.to) ids.add(p.to);
      p.path?.forEach(nodeId => ids.add(nodeId));
    });
    return ids.size > 0 ? ids : undefined;
  }, [dryRunResult]);

  // dry-run 受影响的边：source 或 target 命中受影响节点的边
  const impactedEdgeIds = useMemo(() => {
    if (!impactedNodeIds || !graph) return undefined;
    const ids = new Set<string>();
    graph.edges.forEach(e => {
      if (impactedNodeIds.has(e.source) || impactedNodeIds.has(e.target)) {
        ids.add(e.id);
      }
    });
    return ids.size > 0 ? ids : undefined;
  }, [impactedNodeIds, graph]);

  // 应用 dry-run 增量，生成展示用的“after”图
  const displayGraph = useMemo<GraphResponse | null>(() => {
    if (!graph) return null;
    if (!dryRunResult) return graph;

    const nodeDeltas = dryRunResult.impact?.node_risk_deltas;
    const edgeDeltas = dryRunResult.impact?.edge_weight_deltas;
    if (!nodeDeltas && !edgeDeltas) return graph;

    const newNodes = nodeDeltas
      ? graph.nodes.map(n =>
          nodeDeltas[n.id] !== undefined
            ? { ...n, risk: nodeDeltas[n.id] }
            : n
        )
      : graph.nodes;

    const newEdges = edgeDeltas
      ? graph.edges.map(e =>
          edgeDeltas[e.id] !== undefined
            ? { ...e, weight: edgeDeltas[e.id] }
            : e
        )
      : graph.edges;

    return { ...graph, nodes: newNodes, edges: newEdges };
  }, [graph, dryRunResult]);

  // 保留原始值映射，供 SideInspector 展示 before→after
  const originalValues = useMemo(() => {
    if (!graph || !dryRunResult) return undefined;
    const nodeDeltas = dryRunResult.impact?.node_risk_deltas;
    const edgeDeltas = dryRunResult.impact?.edge_weight_deltas;
    if (!nodeDeltas && !edgeDeltas) return undefined;

    const nodeRisks: Record<string, number> = {};
    const edgeWeights: Record<string, number> = {};
    if (nodeDeltas) {
      graph.nodes.forEach(n => {
        if (nodeDeltas[n.id] !== undefined) nodeRisks[n.id] = n.risk;
      });
    }
    if (edgeDeltas) {
      graph.edges.forEach(e => {
        if (edgeDeltas[e.id] !== undefined) edgeWeights[e.id] = e.weight;
      });
    }
    return { nodeRisks, edgeWeights };
  }, [graph, dryRunResult]);

  const fetchGraph = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = { mode };
      if (filterStart) params.start = new Date(filterStart).toISOString();
      if (filterEnd) params.end = new Date(filterEnd).toISOString();
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

  const startTime = graph?.meta?.start ? new Date(graph.meta.start).getTime() : 0;
  const endTime = graph?.meta?.end ? new Date(graph.meta.end).getTime() : 0;

  const handleClearSelection = useCallback(() => {
    setSelectedNode(null);
    setSelectedEdge(null);
  }, []);

  // dry-run 产生的替代路径，用于 3D 场景渲染
  const altPaths = dryRunResult?.alternative_paths;

  return (
    <div className="h-[calc(100vh-64px)] flex flex-col">
      {/* 工具栏 */}
      <TopologyToolbar
        mode={mode}
        onModeChange={setMode}
        highlightAlertId={highlightAlertId}
        onRefresh={fetchGraph}
        loading={loading}
        startTime={filterStart}
        endTime={filterEnd}
        onStartTimeChange={setFilterStart}
        onEndTimeChange={setFilterEnd}
        layoutMode={layoutMode}
        onLayoutModeChange={setLayoutMode}
        showLabels={showLabels}
        onShowLabelsChange={setShowLabels}
        showArrows={effectiveShowArrows}
        onShowArrowsChange={setShowArrows}
        riskHeatEnabled={riskHeatEnabled}
        onRiskHeatChange={setRiskHeatEnabled}
        onCameraPreset={setCameraPreset}
      />

      {/* 主体：3D 视图 + 侧边检查器 */}
      <div className="flex-grow flex overflow-hidden">
        {/* 3D 画布区域 */}
        <div className="flex-grow flex flex-col relative">
          {loading && !graph ? (
            <div className="flex-grow flex items-center justify-center bg-slate-50">
              <div className="text-gray-400 flex flex-col items-center">
                <RefreshCw className="w-8 h-8 animate-spin mb-2" />
                <p>{t('loading')}</p>
              </div>
            </div>
          ) : graph ? (
            <div className="flex-grow">
              <Topology3D
                nodes={displayGraph!.nodes}
                edges={displayGraph!.edges}
                currentTime={currentTime}
                highlightAlertId={highlightAlertId}
                impactedNodeIds={impactedNodeIds}
                impactedEdgeIds={impactedEdgeIds}
                layoutMode={layoutMode}
                showLabels={showLabels}
                showArrows={effectiveShowArrows}
                riskHeatEnabled={riskHeatEnabled}
                cameraPreset={cameraPreset}
                onCameraPresetDone={() => setCameraPreset(null)}
                focusNodeId={focusNodeId}
                onFocusDone={() => setFocusNodeId(null)}
                altPaths={altPaths}
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

          {/* Dry-Run 影响浮层 */}
          {dryRunId && <DryRunOverlay result={dryRunResult} loading={dryRunLoading} notFound={dryRunNotFound} />}

          {/* TimeSlider 浮层 */}
          {graph && startTime > 0 && endTime > 0 && (
            <div className="absolute bottom-4 left-4 right-4">
              <TimeSlider
                startTime={startTime}
                endTime={endTime}
                currentTime={currentTime}
                onChange={setCurrentTime}
              />
            </div>
          )}
        </div>

        {/* 侧边检查器 */}
        <SideInspector
          selectedNode={selectedNode}
          selectedEdge={selectedEdge}
          dryRunResult={dryRunResult}
          impactedNodeIds={impactedNodeIds}
          impactedEdgeIds={impactedEdgeIds}
          originalValues={originalValues}
          onClose={handleClearSelection}
          onLocateNode={(nodeId) => setFocusNodeId(nodeId)}
        />
      </div>
    </div>
  );
}

export default function TopologyPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-screen"><RefreshCw className="w-6 h-6 animate-spin text-gray-400" /></div>}>
      <TopologyInner />
    </Suspense>
  );
}

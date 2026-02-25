'use client';

import { useEffect, useState, useCallback, useMemo, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import dynamic from 'next/dynamic';
import { api } from '@/lib/api';
import { GraphResponse, GraphNode, GraphEdge, DryRunResult } from '@/lib/api/types';
import { RefreshCw } from 'lucide-react';
import TopologyToolbar from '@/components/topology/TopologyToolbar';
import TimeSlider from '@/components/topology/TimeSlider';
import SideInspector from '@/components/topology/SideInspector';
import TopologyLegend from '@/components/topology/TopologyLegend';
import DryRunOverlay from '@/components/topology/DryRunOverlay';

// Dynamic import for 3D canvas (SSR-incompatible)
const Topology3D = dynamic(() => import('@/components/topology/Topology3D'), {
  ssr: false,
  loading: () => (
    <div className="flex-grow flex items-center justify-center bg-slate-50">
      <RefreshCw className="w-6 h-6 animate-spin text-gray-400" />
    </div>
  ),
});

function TopologyInner() {
  const searchParams = useSearchParams();
  const highlightAlertId = searchParams.get('highlightAlertId');
  const dryRunId = searchParams.get('dryRunId');

  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<'ip' | 'subnet'>('ip');
  const [currentTime, setCurrentTime] = useState(0);

  // Dry-run state
  const [dryRunResult, setDryRunResult] = useState<DryRunResult | null>(null);
  const [dryRunLoading, setDryRunLoading] = useState(false);

  // Selection state for SideInspector
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);

  // Fetch DryRunResult when dryRunId is present
  useEffect(() => {
    if (!dryRunId) { setDryRunResult(null); return; }
    setDryRunLoading(true);
    api.listDryRuns({ alert_id: '' })
      .then(results => {
        const found = results.find(r => r.id === dryRunId);
        setDryRunResult(found || results[0] || null);
      })
      .catch(e => console.error('Failed to load dry-run result', e))
      .finally(() => setDryRunLoading(false));
  }, [dryRunId]);

  // Compute impacted node IDs and edge IDs from dry-run result
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

  // Edges impacted by dry-run: edges whose source or target is an impacted node
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

  // Apply dry-run deltas to produce the "after" graph for display
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

  // Keep a map of original values so SideInspector can show before→after
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
      const data = await api.getGraph({ mode });
      setGraph(data);
      // Initialize currentTime to the start of the data window
      if (data.meta?.start) {
        setCurrentTime(new Date(data.meta.start).getTime());
      }
    } catch (e) {
      console.error('Failed to load topology', e);
    } finally {
      setLoading(false);
    }
  }, [mode]);

  useEffect(() => {
    fetchGraph();
  }, [fetchGraph]);

  const startTime = graph?.meta?.start ? new Date(graph.meta.start).getTime() : 0;
  const endTime = graph?.meta?.end ? new Date(graph.meta.end).getTime() : 0;

  const handleClearSelection = useCallback(() => {
    setSelectedNode(null);
    setSelectedEdge(null);
  }, []);

  return (
    <div className="h-[calc(100vh-64px)] flex flex-col">
      {/* Toolbar */}
      <TopologyToolbar
        mode={mode}
        onModeChange={setMode}
        highlightAlertId={highlightAlertId}
        onRefresh={fetchGraph}
        loading={loading}
      />

      {/* Main body: 3D view + Side inspector */}
      <div className="flex-grow flex overflow-hidden">
        {/* 3D Canvas area */}
        <div className="flex-grow flex flex-col relative">
          {loading && !graph ? (
            <div className="flex-grow flex items-center justify-center bg-slate-50">
              <div className="text-gray-400 flex flex-col items-center">
                <RefreshCw className="w-8 h-8 animate-spin mb-2" />
                <p>Loading topology data...</p>
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
              No topology data available.
            </div>
          )}

          {/* Legend overlay */}
          <TopologyLegend />

          {/* Dry-Run impact overlay */}
          {dryRunId && <DryRunOverlay result={dryRunResult} loading={dryRunLoading} />}

          {/* TimeSlider overlay */}
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

        {/* Side Inspector */}
        <SideInspector
          selectedNode={selectedNode}
          selectedEdge={selectedEdge}
          dryRunResult={dryRunResult}
          impactedNodeIds={impactedNodeIds}
          impactedEdgeIds={impactedEdgeIds}
          originalValues={originalValues}
          onClose={handleClearSelection}
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

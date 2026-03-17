'use client';

import { useCallback, useMemo, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { EvidenceChain } from '@/lib/api/types';
import { 
  ReactFlow, 
  MiniMap, 
  Controls, 
  Background, 
  useNodesState, 
  useEdgesState,
  MarkerType,
  Node,
  Edge
} from 'reactflow';
import 'reactflow/dist/style.css';
import { ShieldAlert, Activity, FileText, Zap, Search, PlayCircle } from 'lucide-react';

interface EvidenceChainViewProps {
  chain: EvidenceChain;
}

// Custom node styles based on type
const getNodeStyle = (type: string) => {
  switch (type) {
    case 'alert': return { background: '#fee2e2', border: '1px solid #ef4444', color: '#991b1b' };
    case 'flow': return { background: '#e0f2fe', border: '1px solid #3b82f6', color: '#1e40af' };
    case 'feature': return { background: '#f3e8ff', border: '1px solid #a855f7', color: '#6b21a8' };
    case 'investigation': return { background: '#fef9c3', border: '1px solid #d946ef', color: '#86198f' };
    case 'action': return { background: '#ffedd5', border: '1px solid #eab308', color: '#a16207' };
    case 'dryrun': return { background: '#dcfce7', border: '1px solid #22c55e', color: '#166534' };
    default: return { background: '#f3f4f6', border: '1px solid #9ca3af', color: '#374151' };
  }
};

const getNodeIcon = (type: string) => {
  switch (type) {
    case 'alert': return <ShieldAlert className="w-4 h-4" />;
    case 'flow': return <Activity className="w-4 h-4" />;
    case 'feature': return <Zap className="w-4 h-4" />;
    case 'investigation': return <Search className="w-4 h-4" />;
    case 'action': return <FileText className="w-4 h-4" />;
    case 'dryrun': return <PlayCircle className="w-4 h-4" />;
    default: return null;
  }
};

export default function EvidenceChainView({ chain }: EvidenceChainViewProps) {
  const router = useRouter();

  // Auto-layout logic (simple horizontal layout for Week 5)
  const { initialNodes, initialEdges } = useMemo(() => {
    const nodes: Node[] = [];
    const edges: Edge[] = [];
    
    // Group nodes by type to assign X coordinates (columns)
    const typeColumns: Record<string, number> = {
      'feature': 0,
      'flow': 250,
      'alert': 500,
      'investigation': 750,
      'action': 1000,
      'dryrun': 1250
    };

    // Track Y positions per column
    const colY: Record<number, number> = {};

    chain.nodes.forEach((n) => {
      const x = typeColumns[n.type] ?? 0;
      const y = colY[x] || 0;
      colY[x] = y + 100; // Spacing between nodes vertically

      nodes.push({
        id: n.id,
        position: { x, y },
        data: { 
          label: (
            <div className="flex flex-col items-center p-1">
              <div className="flex items-center gap-1 font-bold text-xs mb-1 uppercase tracking-wider opacity-80">
                {getNodeIcon(n.type)} {n.type}
              </div>
              <div className="text-xs text-center break-words max-w-[150px]">
                {n.label}
              </div>
            </div>
          )
        },
        style: {
          ...getNodeStyle(n.type),
          borderRadius: '8px',
          padding: '10px',
          width: 180,
          boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)'
        }
      });
    });

    chain.edges.forEach((e, i) => {
      edges.push({
        id: `e-${i}-${e.source}-${e.target}`,
        source: e.source,
        target: e.target,
        label: e.type,
        labelStyle: { fill: '#6b7280', fontWeight: 500, fontSize: 10 },
        labelBgStyle: { fill: '#f9fafb', fillOpacity: 0.8 },
        animated: e.type === 'simulated_by',
        style: { stroke: '#9ca3af', strokeWidth: 2 },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: '#9ca3af',
        },
      });
    });

    return { initialNodes: nodes, initialEdges: edges };
  }, [chain]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Sync ReactFlow internal state when chain prop changes (e.g. after auto-refresh)
  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  const onNodeClick = useCallback((event: React.MouseEvent, node: Node) => {
    const rawId = node.id;
    if (rawId.startsWith('flow:')) {
      const flowId = rawId.replace('flow:', '');
      // In a real app, we might open a drawer or navigate
      router.push(`/flows?flow_id=${flowId}`);
    } else if (rawId.startsWith('dry:')) {
      // Scroll to dry run panel
      document.getElementById('dryrun-panel')?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [router]);

  return (
    <div className="h-[500px] w-full bg-gray-50 rounded-lg border border-gray-200 overflow-hidden">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        fitView
        attributionPosition="bottom-right"
      >
        <Controls />
        <MiniMap 
          nodeStrokeColor={(n) => {
            if (n.style?.background) return n.style.background as string;
            return '#eee';
          }}
          nodeColor={(n) => {
            if (n.style?.background) return n.style.background as string;
            return '#fff';
          }}
        />
        <Background color="#ccc" gap={16} />
      </ReactFlow>
    </div>
  );
}
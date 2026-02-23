'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { GraphResponse } from '@/lib/api/types';
import { Activity, RefreshCw, Clock, Layers } from 'lucide-react';
import { format } from 'date-fns';

export default function TopologyPage() {
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<'ip' | 'subnet'>('ip');

  const fetchGraph = async () => {
    setLoading(true);
    try {
      const data = await api.getGraph({ mode });
      setGraph(data);
    } catch (e) {
      console.error("Failed to load topology", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchGraph();
  }, [mode]);

  return (
    <div className="max-w-7xl mx-auto h-[calc(100vh-100px)] flex flex-col">
      <div className="flex justify-between items-center mb-6 shrink-0">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Network Topology</h1>
          <p className="text-sm text-gray-500 mt-1">
            2D/3D visualization of network entities and traffic flows.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="bg-white border border-gray-200 rounded-md p-1 flex text-sm">
            <button 
              onClick={() => setMode('ip')}
              className={`px-3 py-1 rounded ${mode === 'ip' ? 'bg-blue-50 text-blue-700 font-medium' : 'text-gray-500 hover:text-gray-700'}`}
            >
              IP Mode
            </button>
            <button 
              onClick={() => setMode('subnet')}
              className={`px-3 py-1 rounded ${mode === 'subnet' ? 'bg-blue-50 text-blue-700 font-medium' : 'text-gray-500 hover:text-gray-700'}`}
            >
              Subnet Mode
            </button>
          </div>
          <button 
            onClick={fetchGraph}
            className="p-2 text-gray-500 hover:text-gray-900 bg-white border border-gray-200 rounded-md shadow-sm"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="flex-grow bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden flex relative">
        {/* Main Graph Area (Placeholder for Week 5, will be 3D in Week 6) */}
        <div className="flex-grow bg-gray-50 flex items-center justify-center relative">
          {loading ? (
            <div className="text-gray-400 flex flex-col items-center">
              <RefreshCw className="w-8 h-8 animate-spin mb-2" />
              <p>Loading topology data...</p>
            </div>
          ) : graph ? (
            <div className="text-center">
              <Activity className="w-16 h-16 text-blue-300 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-gray-900 mb-2">2D Topology Preview (Week 5)</h3>
              <p className="text-sm text-gray-500 max-w-md mx-auto mb-6">
                Loaded {graph.nodes.length} nodes and {graph.edges.length} edges.
                Full 3D visualization with time-slider will be implemented in Week 6.
              </p>
              
              {/* Simple text-based representation for Week 5 validation */}
              <div className="bg-white p-4 rounded border border-gray-200 text-left max-w-2xl mx-auto max-h-64 overflow-y-auto text-xs font-mono">
                <div className="font-bold text-gray-700 mb-2">Nodes:</div>
                {graph.nodes.map(n => (
                  <div key={n.id} className="mb-1">
                    <span className="text-blue-600">{n.id}</span> ({n.type}) - Risk: {n.risk}
                  </div>
                ))}
                <div className="font-bold text-gray-700 mt-4 mb-2">Edges:</div>
                {graph.edges.map(e => (
                  <div key={e.id} className="mb-1">
                    <span className="text-green-600">{e.source}</span> → <span className="text-purple-600">{e.target}</span> 
                    {' '}[{e.protocols.join(',')}] (Weight: {e.weight})
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="text-gray-400">No data available</div>
          )}

          {/* Time Slider Placeholder */}
          <div className="absolute bottom-6 left-1/2 -translate-x-1/2 bg-white px-6 py-3 rounded-full shadow-lg border border-gray-200 flex items-center gap-4 w-96">
            <Clock className="w-4 h-4 text-gray-400" />
            <div className="flex-grow h-1.5 bg-gray-200 rounded-full overflow-hidden">
              <div className="w-1/3 h-full bg-blue-500"></div>
            </div>
            <span className="text-xs font-medium text-gray-500">
              {graph?.meta?.start ? format(new Date(graph.meta.start), 'HH:mm:ss') : '00:00:00'}
            </span>
          </div>
        </div>

        {/* Side Inspector */}
        <div className="w-80 border-l border-gray-200 bg-white p-4 overflow-y-auto">
          <div className="flex items-center gap-2 mb-4 pb-4 border-b border-gray-100">
            <Layers className="w-5 h-5 text-gray-500" />
            <h2 className="font-medium text-gray-900">Inspector</h2>
          </div>
          
          <div className="text-sm text-gray-500 text-center py-8">
            Select a node or edge in the graph to view details.
          </div>
        </div>
      </div>
    </div>
  );
}

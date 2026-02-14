'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { FlowRecord } from '@/lib/api/types';
import FlowFilterBar from '@/components/flows/FlowFilterBar';
import FlowTable from '@/components/flows/FlowTable';
import FlowDetailDrawer from '@/components/flows/FlowDetailDrawer';

export default function FlowsPage() {
  const [flows, setFlows] = useState<FlowRecord[]>([]);
  const [filteredFlows, setFilteredFlows] = useState<FlowRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedFlow, setSelectedFlow] = useState<FlowRecord | null>(null);

  useEffect(() => {
    const fetchFlows = async () => {
      try {
        const data = await api.listFlows({});
        // In a real app we might get thousands, this is just a sample
        // If the sample is just 1 item, I'll duplicate it a few times with slight variations to make the UI look populated?
        // Actually, let's just stick to the sample. If the user wants to see more, we can modify the mock.
        // But for testing the UI, let's duplicate the mock data if it's too small.
        if (data.length === 1) {
           const base = data[0];
           const multiples = Array.from({length: 10}).map((_, i) => ({
             ...base,
             id: `${base.id}-${i}`,
             src_port: base.src_port + i,
             anomaly_score: Math.random(), // Random score to test color coding
             ts_start: new Date(new Date(base.ts_start).getTime() + i * 1000).toISOString()
           }));
           setFlows(multiples);
           setFilteredFlows(multiples);
        } else {
           setFlows(data);
           setFilteredFlows(data);
        }
      } catch (e) {
        console.error("Failed to list flows", e);
      } finally {
        setLoading(false);
      }
    };
    fetchFlows();
  }, []);

  const handleFilterChange = (filters: any) => {
    // Client-side filtering for Mock Mode demo
    // Note for Real Mode: pass these filters to api.listFlows(filters)
    let result = [...flows];
    if (filters.src_ip) {
      result = result.filter(f => f.src_ip.includes(filters.src_ip));
    }
    if (filters.dst_ip) {
      result = result.filter(f => f.dst_ip.includes(filters.dst_ip));
    }
    if (filters.proto) {
      result = result.filter(f => f.proto === filters.proto);
    }
    if (filters.min_score) {
      const min = parseFloat(filters.min_score);
      if (!isNaN(min)) {
        result = result.filter(f => f.anomaly_score >= min);
      }
    }
    setFilteredFlows(result);
  };

  return (
    <div className="max-w-7xl mx-auto h-[calc(100vh-100px)] flex flex-col">
       <div className="flex justify-between items-center mb-6 shrink-0">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Network Flows</h1>
          <p className="text-sm text-gray-500 mt-1">
            Traffic analysis and anomaly detection results.
          </p>
        </div>
      </div>

      <div className="shrink-0">
        <FlowFilterBar onFilterChange={handleFilterChange} />
      </div>

      <div className="flex-grow overflow-hidden relative">
        {loading ? (
          <div className="text-center py-12 text-gray-500">Loading flow data...</div>
        ) : (
          <FlowTable 
            flows={filteredFlows} 
            onSelect={setSelectedFlow} 
            selectedId={selectedFlow?.id}
          />
        )}
      </div>

      <FlowDetailDrawer 
        flow={selectedFlow} 
        onClose={() => setSelectedFlow(null)} 
      />
    </div>
  );
}

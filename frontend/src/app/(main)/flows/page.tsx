'use client';

import { useEffect, useState, useCallback } from 'react';
import { api } from '@/lib/api';
import { FlowRecord } from '@/lib/api/types';
import { useTranslations } from 'next-intl';
import FlowFilterBar from '@/components/flows/FlowFilterBar';
import FlowTable from '@/components/flows/FlowTable';
import FlowDetailDrawer from '@/components/flows/FlowDetailDrawer';

export default function FlowsPage() {
  const t = useTranslations('flows');
  const [flows, setFlows] = useState<FlowRecord[]>([]);
  const [filters, setFilters] = useState<any>({});
  const [loading, setLoading] = useState(true);
  const [selectedFlow, setSelectedFlow] = useState<FlowRecord | null>(null);

  useEffect(() => {
    const fetchFlows = async () => {
      try {
        const data = await api.listFlows({});
        setFlows(data);
      } catch (e) {
        console.error("Failed to list flows", e);
      } finally {
        setLoading(false);
      }
    };
    fetchFlows();
  }, []);

  const handleFilterChange = useCallback((newFilters: any) => {
    setFilters(newFilters);
  }, []);

  // Derive filtered flows from state
  const filteredFlows = flows.filter(f => {
    if (filters.pcap_id && !f.pcap_id.includes(filters.pcap_id)) return false;
    if (filters.src_ip && !f.src_ip.includes(filters.src_ip)) return false;
    if (filters.dst_ip && !f.dst_ip.includes(filters.dst_ip)) return false;
    if (filters.proto && f.proto !== filters.proto) return false;
    if (filters.min_score) {
      const min = parseFloat(filters.min_score);
      if (!isNaN(min) && (f.anomaly_score == null || f.anomaly_score < min)) return false;
    }
    if (filters.time_start) {
      const start = new Date(filters.time_start).getTime();
      if (!isNaN(start) && new Date(f.ts_start).getTime() < start) return false;
    }
    if (filters.time_end) {
      const end = new Date(filters.time_end).getTime();
      if (!isNaN(end) && new Date(f.ts_end).getTime() > end) return false;
    }
    return true;
  });

  return (
    <div className="max-w-7xl mx-auto h-[calc(100vh-100px)] flex flex-col">
       <div className="flex justify-between items-center mb-6 shrink-0">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{t('title')}</h1>
          <p className="text-sm text-gray-500 mt-1">
            {t('description')}
          </p>
        </div>
      </div>

      <div className="shrink-0">
        <FlowFilterBar onFilterChange={handleFilterChange} />
      </div>

      <div className="flex-grow overflow-hidden relative">
        {loading ? (
          <div className="text-center py-12 text-gray-500">{t('loading')}</div>
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

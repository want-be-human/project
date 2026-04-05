'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { api } from '@/lib/api';
import { FlowRecord, FlowListParams } from '@/lib/api/types';
import { useTranslations } from 'next-intl';
import FlowFilterBar from '@/components/flows/FlowFilterBar';
import FlowTable from '@/components/flows/FlowTable';
import FlowDetailDrawer from '@/components/flows/FlowDetailDrawer';
import Pagination from '@/components/shared/Pagination';

export default function FlowsPage() {
  const t = useTranslations('flows');
  const [flows, setFlows] = useState<FlowRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState<FlowListParams>({});
  const [loading, setLoading] = useState(true);
  const [selectedFlow, setSelectedFlow] = useState<FlowRecord | null>(null);

  const fetchFlows = useCallback(async (params: FlowListParams) => {
    setLoading(true);
    try {
      const result = await api.listFlows(params);
      setFlows(result.items);
      setTotal(result.total);
    } catch (e) {
      console.error("Failed to list flows", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFlows({ ...filters, limit, offset });
  }, [filters, limit, offset, fetchFlows]);

  const handleFilterChange = useCallback((rawFilters: Record<string, string | undefined>) => {
    // Map FlowFilterBar keys to backend API param names
    const mapped: FlowListParams = {
      pcap_id: rawFilters.pcap_id,
      src_ip: rawFilters.src_ip,
      dst_ip: rawFilters.dst_ip,
      proto: rawFilters.proto,
      min_score: rawFilters.min_score ? parseFloat(rawFilters.min_score) : undefined,
      start: rawFilters.time_start ? new Date(rawFilters.time_start).toISOString() : undefined,
      end: rawFilters.time_end ? new Date(rawFilters.time_end).toISOString() : undefined,
    };
    // Remove undefined values
    const cleaned = Object.fromEntries(
      Object.entries(mapped).filter(([, v]) => v !== undefined && v !== '')
    ) as FlowListParams;
    setFilters(cleaned);
    setOffset(0);
  }, []);

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
            flows={flows}
            onSelect={setSelectedFlow}
            selectedId={selectedFlow?.id}
          />
        )}
      </div>

      <Pagination
        total={total}
        limit={limit}
        offset={offset}
        onPageChange={setOffset}
        onPageSizeChange={(newLimit) => { setLimit(newLimit); setOffset(0); }}
      />

      <FlowDetailDrawer
        flow={selectedFlow}
        onClose={() => setSelectedFlow(null)}
      />
    </div>
  );
}

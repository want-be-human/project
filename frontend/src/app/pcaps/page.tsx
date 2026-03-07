'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { PcapFile } from '@/lib/api/types';
import { wsClient } from '@/lib/ws';
import { useTranslations } from 'next-intl';
import PcapUploadPanel from '@/components/pcaps/PcapUploadPanel';
import PcapListTable from '@/components/pcaps/PcapListTable';

export default function PcapsPage() {
  const t = useTranslations('pcaps');
  const [pcaps, setPcaps] = useState<PcapFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [processingId, setProcessingId] = useState<string | null>(null);

  const fetchPcaps = async () => {
    try {
      const data = await api.listPcaps();
      setPcaps(data);
    } catch (e) {
      console.error("Failed to list pcaps", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPcaps();
  }, []);

  // Subscribe to WS events for real-time progress updates
  useEffect(() => {
    const unsubProgress = wsClient.onEvent('pcap.process.progress', (data: { pcap_id: string; percent: number }) => {
      setPcaps(prev => prev.map(p =>
        p.id === data.pcap_id
          ? { ...p, status: 'processing' as const, progress: data.percent }
          : p
      ));
    });

    const unsubDone = wsClient.onEvent('pcap.process.done', (data: { pcap_id: string; flow_count: number; alert_count: number }) => {
      setPcaps(prev => prev.map(p =>
        p.id === data.pcap_id
          ? { ...p, status: 'done' as const, progress: 100, flow_count: data.flow_count, alert_count: data.alert_count }
          : p
      ));
      // Also do a full refresh to ensure consistency
      fetchPcaps();
    });

    return () => {
      unsubProgress();
      unsubDone();
    };
  }, []);

  const handleProcess = async (id: string) => {
    setProcessingId(id);
    try {
      await api.processPcap(id, { mode: 'flows_and_detect' });
      // WS events (pcap.process.progress / pcap.process.done) will handle updates
      // Do an initial optimistic status change
      setPcaps(prev => prev.map(p =>
        p.id === id ? { ...p, status: 'processing' as const, progress: 0 } : p
      ));
    } catch (e) {
      console.error(e);
      alert(t('processFailed'));
    } finally {
      setProcessingId(null);
    }
  };

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{t('title')}</h1>
          <p className="text-sm text-gray-500 mt-1">
            {t('description')}
          </p>
        </div>
      </div>

      <PcapUploadPanel onUploadSuccess={fetchPcaps} />
      
      {loading ? (
        <div className="text-center py-12 text-gray-500">{t('uploading')}</div>
      ) : (
        <PcapListTable 
          pcaps={pcaps} 
          onProcess={handleProcess}
          processingId={processingId}
        />
      )}
    </div>
  );
}

'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { PcapFile, PipelineRun } from '@/lib/api/types';
import { wsClient } from '@/lib/ws';
import { useTranslations } from 'next-intl';
import { Activity } from 'lucide-react';
import PcapUploadPanel from '@/components/pcaps/PcapUploadPanel';
import PcapListTable from '@/components/pcaps/PcapListTable';
import PipelineStageTimeline from '@/components/pipeline/PipelineStageTimeline';

export default function PcapsPage() {
  const t = useTranslations('pcaps');
  const [pcaps, setPcaps] = useState<PcapFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [processingId, setProcessingId] = useState<string | null>(null);

  const [selectedPcap, setSelectedPcap] = useState<PcapFile | null>(null);
  const [pipelineRun, setPipelineRun] = useState<PipelineRun | null>(null);
  const [pipelineLoading, setPipelineLoading] = useState(false);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [pipelineRefreshToken, setPipelineRefreshToken] = useState(0);

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

  // Fetch pipeline run when a PCAP is selected or after processing completes
  useEffect(() => {
    if (!selectedPcap) {
      setPipelineRun(null);
      setPipelineError(null);
      return;
    }
    if (selectedPcap.status === 'processing' || selectedPcap.status === 'uploaded') {
      setPipelineRun(null);
      setPipelineError(null);
      return;
    }

    let cancelled = false;
    setPipelineLoading(true);
    setPipelineError(null);
    setPipelineRun(null);

    api.getPipelineRun(selectedPcap.id)
      .then(run => { if (!cancelled) setPipelineRun(run); })
      .catch((err: Error) => {
        if (!cancelled) {
          // 404 means feature flag is off — show graceful empty state, not an error
          if (!err.message.includes('404')) {
            setPipelineError(err.message);
          }
        }
      })
      .finally(() => { if (!cancelled) setPipelineLoading(false); });

    return () => { cancelled = true; };
  }, [selectedPcap?.id, pipelineRefreshToken]);

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
      // If the completed PCAP is selected, refresh its pipeline data
      if (data.pcap_id === selectedPcap?.id) {
        setPipelineRefreshToken(t => t + 1);
      }
    });

    return () => {
      unsubProgress();
      unsubDone();
    };
  }, [selectedPcap?.id]);

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

  const handleSelectPcap = (pcap: PcapFile) => {
    setSelectedPcap(prev => prev?.id === pcap.id ? null : pcap);
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
          onSelect={handleSelectPcap}
          selectedId={selectedPcap?.id}
        />
      )}

      {selectedPcap && (
        <div className="mt-6 bg-white p-5 rounded-lg border border-gray-200 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold text-gray-900 flex items-center gap-2">
              <Activity className="w-4 h-4 text-indigo-600" />
              Pipeline
              <span className="font-mono text-sm text-gray-500 font-normal">{selectedPcap.filename}</span>
            </h2>
            <button
              onClick={() => setSelectedPcap(null)}
              className="text-xs text-gray-400 hover:text-gray-600 px-2 py-1 rounded hover:bg-gray-100 transition-colors"
            >
              Dismiss
            </button>
          </div>
          <PipelineStageTimeline
            pipelineRun={pipelineRun}
            loading={pipelineLoading}
            error={pipelineError}
          />
        </div>
      )}
    </div>
  );
}

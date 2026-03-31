'use client';

import { useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { PcapFile, PipelineRun } from '@/lib/api/types';
import { wsClient } from '@/lib/ws';
import {
  PCAP_PROCESS_PROGRESS,
  PCAP_PROCESS_DONE,
  PCAP_PROCESS_FAILED,
} from '@/lib/events';
import { useTranslations } from 'next-intl';
import { Activity } from 'lucide-react';
import PcapUploadPanel from '@/components/pcaps/PcapUploadPanel';
import PcapListTable from '@/components/pcaps/PcapListTable';
import PipelineStageTimeline from '@/components/pipeline/PipelineStageTimeline';

export default function PcapsPage() {
  const t = useTranslations('pcaps');
  // 引入 pipeline 命名空间的国际化翻译
  const tPipeline = useTranslations('pipeline');
  const [pcaps, setPcaps] = useState<PcapFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const [selectedPcap, setSelectedPcap] = useState<PcapFile | null>(null);
  const [pipelineRun, setPipelineRun] = useState<PipelineRun | null>(null);
  const [pipelineLoading, setPipelineLoading] = useState(false);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [pipelineRefreshToken, setPipelineRefreshToken] = useState(0);
  // Pipeline 可观测性功能是否被禁用（API 返回 404 时设置）
  const [featureDisabled, setFeatureDisabled] = useState(false);

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

  // 当选中 PCAP 或处理完成后获取对应的 Pipeline 运行记录
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
    // 每次重新获取时重置 featureDisabled 状态
    setFeatureDisabled(false);

    api.getPipelineRun(selectedPcap.id)
      .then(run => { if (!cancelled) setPipelineRun(run); })
      .catch((err: Error) => {
        if (!cancelled) {
          if (err.message.includes('404')) {
            // 404 表示 Pipeline 可观测性功能未启用，设置特定状态标识
            setFeatureDisabled(true);
          } else {
            setPipelineError(err.message);
          }
        }
      })
      .finally(() => { if (!cancelled) setPipelineLoading(false); });

    return () => { cancelled = true; };
  }, [selectedPcap?.id, pipelineRefreshToken]);

  // 订阅 WebSocket 事件以实时更新处理进度
  useEffect(() => {
    const unsubProgress = wsClient.onEvent(PCAP_PROCESS_PROGRESS, (data: { pcap_id: string; percent: number }) => {
      setPcaps(prev => prev.map(p =>
        p.id === data.pcap_id
          ? { ...p, status: 'processing' as const, progress: data.percent }
          : p
      ));
    });

    const unsubDone = wsClient.onEvent(PCAP_PROCESS_DONE, (data: { pcap_id: string; flow_count: number; alert_count: number }) => {
      setPcaps(prev => prev.map(p =>
        p.id === data.pcap_id
          ? { ...p, status: 'done' as const, progress: 100, flow_count: data.flow_count, alert_count: data.alert_count }
          : p
      ));
      // 同时执行一次全量刷新，确保数据一致
      fetchPcaps();
      // 若当前选中的是已完成的 PCAP，则刷新其 Pipeline 数据
      if (data.pcap_id === selectedPcap?.id) {
        setPipelineRefreshToken(t => t + 1);
      }
    });

    // 订阅处理失败事件，更新对应 PCAP 状态为 failed
    const unsubFailed = wsClient.onEvent(PCAP_PROCESS_FAILED, (data: { pcap_id: string; error?: string }) => {
      setPcaps(prev => prev.map(p =>
        p.id === data.pcap_id
          ? { ...p, status: 'failed' as const, progress: 0, error_message: data.error }
          : p
      ));
    });

    return () => {
      unsubProgress();
      unsubDone();
      unsubFailed();
    };
  }, [selectedPcap?.id]);

  // 轮询兜底机制：当存在 processing 状态的 PCAP 时，启动 3 秒间隔轮询
  // 确保即使 WebSocket 广播失败，前端也能最终获取正确状态
  useEffect(() => {
    const hasProcessing = pcaps.some(p => p.status === 'processing');
    if (!hasProcessing) return;

    const timer = setInterval(async () => {
      try {
        const data = await api.listPcaps();
        setPcaps(data);
      } catch (e) {
        console.error('轮询 PCAP 列表失败', e);
      }
    }, 3000);

    return () => clearInterval(timer);
  }, [pcaps]);

  // 用 useRef 跟踪 selectedPcap 的上一次状态，用于检测 processing → done 的转换
  const prevSelectedStatusRef = useRef<string | undefined>(selectedPcap?.status);

  // 同步 selectedPcap 状态：当 pcaps 列表更新时，保持 selectedPcap 数据最新
  useEffect(() => {
    if (!selectedPcap) {
      prevSelectedStatusRef.current = undefined;
      return;
    }

    const updated = pcaps.find(p => p.id === selectedPcap.id);
    if (!updated) return;

    // 用列表中的最新数据同步 selectedPcap
    setSelectedPcap(updated);

    // 检测 processing → done 的状态转换，自动触发 Pipeline 面板刷新
    const prevStatus = prevSelectedStatusRef.current;
    if (prevStatus === 'processing' && updated.status === 'done') {
      setPipelineRefreshToken(t => t + 1);
    }

    // 更新 ref 为当前最新状态
    prevSelectedStatusRef.current = updated.status;
  }, [pcaps]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleProcess = async (id: string) => {
    setProcessingId(id);
    try {
      await api.processPcap(id, { mode: 'flows_and_detect' });
      // 后续状态更新由 WebSocket 事件（pcap.process.progress / pcap.process.done）处理
      // 先进行一次乐观状态更新
      setPcaps(prev => prev.map(p =>
        p.id === id ? { ...p, status: 'processing' as const, progress: 10 } : p
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

  const handleDelete = async (id: string) => {
    if (!window.confirm(t('deleteConfirmMessage'))) return;
    setDeletingId(id);
    try {
      await api.deletePcap(id);
      setPcaps(prev => prev.filter(p => p.id !== id));
      if (selectedPcap?.id === id) {
        setSelectedPcap(null);
        setPipelineRun(null);
        setPipelineError(null);
      }
    } catch (e) {
      console.error(e);
      alert(t('deleteFailed'));
    } finally {
      setDeletingId(null);
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
          onSelect={handleSelectPcap}
          selectedId={selectedPcap?.id}
          onDelete={handleDelete}
          deletingId={deletingId}
        />
      )}

      {selectedPcap && (
        <div className="mt-6 bg-white p-5 rounded-lg border border-gray-200 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold text-gray-900 flex items-center gap-2">
              <Activity className="w-4 h-4 text-indigo-600" />
              {tPipeline('title')}
              <span className="font-mono text-sm text-gray-500 font-normal">{selectedPcap.filename}</span>
            </h2>
            <button
              onClick={() => setSelectedPcap(null)}
              className="text-xs text-gray-400 hover:text-gray-600 px-2 py-1 rounded hover:bg-gray-100 transition-colors"
            >
              {tPipeline('dismiss')}
            </button>
          </div>
          {/* 处理中提示：PCAP 正在处理时显示 */}
          {selectedPcap.status === 'processing' && (
            <div className="mb-3 px-3 py-2 bg-blue-50 border border-blue-200 rounded text-sm text-blue-700">
              {tPipeline('processingHint')}
            </div>
          )}
          {/* Pipeline 可观测性功能未启用提示 */}
          {featureDisabled && (
            <div className="mb-3 px-3 py-2 bg-yellow-50 border border-yellow-200 rounded text-sm text-yellow-700">
              {tPipeline('featureDisabled')}
            </div>
          )}
          {!featureDisabled && (
            <PipelineStageTimeline
              pipelineRun={pipelineRun}
              loading={pipelineLoading}
              error={pipelineError}
            />
          )}
        </div>
      )}
    </div>
  );
}

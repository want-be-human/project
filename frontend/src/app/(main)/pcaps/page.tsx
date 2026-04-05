'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { api } from '@/lib/api';
import { PcapFile, PipelineRun, Batch, BatchDetail, BatchFileRecord } from '@/lib/api/types';
import { wsClient } from '@/lib/ws';
import {
  PCAP_PROCESS_PROGRESS,
  PCAP_PROCESS_DONE,
  PCAP_PROCESS_FAILED,
  BATCH_FILE_STATUS,
  BATCH_COMPLETED,
  BATCH_FAILED,
  BATCH_CANCELLED,
} from '@/lib/events';
import { useTranslations } from 'next-intl';
import { Activity } from 'lucide-react';
import UnifiedUploadPanel from '@/components/pcaps/UnifiedUploadPanel';
import PcapListTable from '@/components/pcaps/PcapListTable';
import BatchOverviewSection from '@/components/pcaps/BatchOverviewSection';
import BatchDetailPanel from '@/components/batch/BatchDetailPanel';
import PipelineStageTimeline from '@/components/pipeline/PipelineStageTimeline';

export default function PcapsPage() {
  const t = useTranslations('pcaps');
  const tPipeline = useTranslations('pipeline');

  // ═══════════════════════════════════════════
  //  Section 1: 上传区状态
  // ═══════════════════════════════════════════
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // ═══════════════════════════════════════════
  //  Section 2: 批次状态
  // ═══════════════════════════════════════════
  const [batches, setBatches] = useState<Batch[]>([]);
  const [batchesLoading, setBatchesLoading] = useState(true);
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null);
  const [batchDetail, setBatchDetail] = useState<BatchDetail | null>(null);
  const [batchDetailLoading, setBatchDetailLoading] = useState(false);
  const [isStartingBatch, setIsStartingBatch] = useState(false);
  const [isCancellingBatch, setIsCancellingBatch] = useState(false);
  const [isRetryingBatch, setIsRetryingBatch] = useState(false);
  const [deletingBatchId, setDeletingBatchId] = useState<string | null>(null);

  // ═══════════════════════════════════════════
  //  Section 3+4: PCAP 文件状态（保留原有）
  // ═══════════════════════════════════════════
  const [pcaps, setPcaps] = useState<PcapFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const [selectedPcap, setSelectedPcap] = useState<PcapFile | null>(null);
  const [pipelineRun, setPipelineRun] = useState<PipelineRun | null>(null);
  const [pipelineLoading, setPipelineLoading] = useState(false);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [pipelineRefreshToken, setPipelineRefreshToken] = useState(0);
  const [featureDisabled, setFeatureDisabled] = useState(false);

  // ── Toast ──
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const showToast = useCallback((type: 'success' | 'error', message: string) => {
    setToast({ type, message });
    setTimeout(() => setToast(null), 4000);
  }, []);

  // ═══════════════════════════════════════════
  //  数据加载
  // ═══════════════════════════════════════════

  const fetchPcaps = useCallback(async () => {
    try {
      const data = await api.listPcaps();
      setPcaps(data);
    } catch (e) {
      console.error('Failed to list pcaps', e);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchBatches = useCallback(async () => {
    try {
      const data = await api.listBatches({ limit: 50 });
      // 过滤已取消的批次
      setBatches(data.filter(b => b.status !== 'cancelled'));
    } catch (e) {
      console.error('Failed to list batches', e);
    } finally {
      setBatchesLoading(false);
    }
  }, []);

  const fetchBatchDetail = useCallback(async (batchId: string) => {
    setBatchDetailLoading(true);
    try {
      const detail = await api.getBatchDetail(batchId);
      setBatchDetail(detail);
    } catch (e) {
      console.error('Failed to get batch detail', e);
    } finally {
      setBatchDetailLoading(false);
    }
  }, []);

  // 初始加载
  useEffect(() => {
    fetchPcaps();
    fetchBatches();
  }, [fetchPcaps, fetchBatches]);

  // ═══════════════════════════════════════════
  //  WebSocket 订阅 — PCAP 事件（保留原有）
  // ═══════════════════════════════════════════

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
      fetchPcaps();
      if (data.pcap_id === selectedPcap?.id) {
        setPipelineRefreshToken(t => t + 1);
      }
    });

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
  }, [selectedPcap?.id, fetchPcaps]);

  // ═══════════════════════════════════════════
  //  WebSocket 订阅 — 批次事件（新增）
  // ═══════════════════════════════════════════

  useEffect(() => {
    if (!selectedBatchId) return;
    const bid = selectedBatchId;

    const unsub1 = wsClient.onEvent(BATCH_FILE_STATUS, (data: any) => {
      if (data.batch_id !== bid) return;
      setBatchDetail(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          files: prev.files.map((f: BatchFileRecord) =>
            f.id === data.batch_file_id
              ? {
                  ...f,
                  status: data.status ?? f.status,
                  flow_count: data.flow_count ?? f.flow_count,
                  alert_count: data.alert_count ?? f.alert_count,
                  error_message: data.error ?? f.error_message,
                }
              : f
          ),
        };
      });
    });

    const unsub2 = wsClient.onEvent(BATCH_COMPLETED, (data: any) => {
      if (data.batch_id !== bid) return;
      fetchBatchDetail(bid);
      fetchBatches();
      fetchPcaps(); // 批次完成可能有新 PCAP 文件
    });

    const unsub3 = wsClient.onEvent(BATCH_FAILED, (data: any) => {
      if (data.batch_id !== bid) return;
      fetchBatchDetail(bid);
      fetchBatches();
    });

    const unsub4 = wsClient.onEvent(BATCH_CANCELLED, (data: any) => {
      if (data.batch_id !== bid) return;
      fetchBatchDetail(bid);
      fetchBatches();
    });

    return () => {
      unsub1();
      unsub2();
      unsub3();
      unsub4();
    };
  }, [selectedBatchId, fetchBatchDetail, fetchBatches, fetchPcaps]);

  // ═══════════════════════════════════════════
  //  轮询兜底
  // ═══════════════════════════════════════════

  // PCAP 处理中轮询（保留原有）
  useEffect(() => {
    const hasProcessing = pcaps.some(p => p.status === 'processing');
    if (!hasProcessing) return;
    const timer = setInterval(async () => {
      try { const data = await api.listPcaps(); setPcaps(data); } catch {}
    }, 3000);
    return () => clearInterval(timer);
  }, [pcaps]);

  // 批次处理中轮询（新增）
  useEffect(() => {
    if (!batchDetail || batchDetail.status !== 'processing') return;
    const timer = setInterval(() => fetchBatchDetail(batchDetail.id), 5000);
    return () => clearInterval(timer);
  }, [batchDetail?.id, batchDetail?.status, fetchBatchDetail]);

  // ═══════════════════════════════════════════
  //  Pipeline 相关（保留原有）
  // ═══════════════════════════════════════════

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
    setFeatureDisabled(false);

    api.getPipelineRun(selectedPcap.id)
      .then(run => { if (!cancelled) setPipelineRun(run); })
      .catch((err: Error) => {
        if (!cancelled) {
          if (err.message.includes('404')) {
            setFeatureDisabled(true);
          } else {
            setPipelineError(err.message);
          }
        }
      })
      .finally(() => { if (!cancelled) setPipelineLoading(false); });

    return () => { cancelled = true; };
  }, [selectedPcap?.id, pipelineRefreshToken]);

  const prevSelectedStatusRef = useRef<string | undefined>(selectedPcap?.status);

  useEffect(() => {
    if (!selectedPcap) {
      prevSelectedStatusRef.current = undefined;
      return;
    }
    const updated = pcaps.find(p => p.id === selectedPcap.id);
    if (!updated) return;
    setSelectedPcap(updated);
    const prevStatus = prevSelectedStatusRef.current;
    if (prevStatus === 'processing' && updated.status === 'done') {
      setPipelineRefreshToken(t => t + 1);
    }
    prevSelectedStatusRef.current = updated.status;
  }, [pcaps]);

  // ═══════════════════════════════════════════
  //  操作处理 — PCAP（保留原有）
  // ═══════════════════════════════════════════

  const handleProcess = async (id: string) => {
    setProcessingId(id);
    try {
      await api.processPcap(id, { mode: 'flows_and_detect' });
      setPcaps(prev => prev.map(p =>
        p.id === id ? { ...p, status: 'processing' as const, progress: 10 } : p
      ));
    } catch (e) {
      console.error(e);
      showToast('error', t('processFailed'));
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
      fetchBatches(); // 同步刷新批次列表
      if (selectedPcap?.id === id) {
        setSelectedPcap(null);
        setPipelineRun(null);
        setPipelineError(null);
      }
    } catch (e) {
      console.error(e);
      showToast('error', t('deleteFailed'));
    } finally {
      setDeletingId(null);
    }
  };

  // ═══════════════════════════════════════════
  //  操作处理 — 统一上传（全部走 Batch API）
  // ═══════════════════════════════════════════

  const handleSubmitUpload = async (files: File[], name: string, source: string, tags: string[]) => {
    setIsUploading(true);
    setUploadError(null);
    try {
      // 1. 创建批次
      const batch = await api.createBatch({ name: name || undefined, source: source || undefined, tags: tags.length > 0 ? tags : undefined });

      // 2. 上传文件到批次
      await api.uploadBatchFiles(batch.id, files);

      // 3. 自动启动处理
      await api.startBatch(batch.id);

      // 4. 刷新数据
      await Promise.all([fetchBatches(), fetchPcaps()]);
      setSelectedBatchId(batch.id);
      await fetchBatchDetail(batch.id);
      showToast('success', t('uploadSuccessBatch'));
    } catch (e: any) {
      setUploadError(e.message || t('uploadFailed'));
      // 即使失败也刷新批次列表，让用户看到已创建的批次
      fetchBatches();
    } finally {
      setIsUploading(false);
    }
  };

  // ═══════════════════════════════════════════
  //  操作处理 — 批次控制（新增）
  // ═══════════════════════════════════════════

  const handleSelectBatch = useCallback((batchId: string) => {
    if (selectedBatchId === batchId) {
      setSelectedBatchId(null);
      setBatchDetail(null);
    } else {
      setSelectedBatchId(batchId);
      fetchBatchDetail(batchId);
    }
  }, [selectedBatchId, fetchBatchDetail]);

  const handleStartBatch = async () => {
    if (!selectedBatchId) return;
    setIsStartingBatch(true);
    try {
      await api.startBatch(selectedBatchId);
      await fetchBatchDetail(selectedBatchId);
      await fetchBatches();
      showToast('success', t('batchStartSuccess'));
    } catch (e: any) {
      showToast('error', e.message || 'Failed');
    } finally {
      setIsStartingBatch(false);
    }
  };

  const handleCancelBatch = async () => {
    if (!selectedBatchId) return;
    setIsCancellingBatch(true);
    try {
      await api.cancelBatch(selectedBatchId);
      await fetchBatchDetail(selectedBatchId);
      await fetchBatches();
      showToast('success', t('batchCancelSuccess'));
    } catch (e: any) {
      showToast('error', e.message || 'Failed');
    } finally {
      setIsCancellingBatch(false);
    }
  };

  const handleRetryAll = async () => {
    if (!selectedBatchId) return;
    setIsRetryingBatch(true);
    try {
      await api.retryBatch(selectedBatchId);
      await fetchBatchDetail(selectedBatchId);
      showToast('success', t('batchRetrySuccess'));
    } catch (e: any) {
      showToast('error', e.message || 'Failed');
    } finally {
      setIsRetryingBatch(false);
    }
  };

  const handleRetryFile = async (fileId: string) => {
    if (!selectedBatchId) return;
    try {
      await api.retryBatchFile(selectedBatchId, fileId);
      await fetchBatchDetail(selectedBatchId);
      showToast('success', t('batchRetrySuccess'));
    } catch (e: any) {
      showToast('error', e.message || 'Failed');
    }
  };

  const handleDeleteBatch = async (batchId: string) => {
    if (!window.confirm(t('batchDeleteConfirm'))) return;
    setDeletingBatchId(batchId);
    let deletedPcapIds: string[] = [];
    try {
      const result = await api.deleteBatch(batchId);
      deletedPcapIds = result.pcap_ids ?? [];
      showToast('success', t('batchDeleteSuccess'));
    } catch (e: any) {
      showToast('error', e.message || t('batchDeleteFailed'));
    } finally {
      if (selectedBatchId === batchId) {
        setSelectedBatchId(null);
        setBatchDetail(null);
      }
      setDeletingBatchId(null);
      fetchBatches();
      // 后台清理 PCAP 可能尚未完成，用后端返回的 pcap_ids 在本地立即移除
      if (deletedPcapIds.length > 0) {
        const idSet = new Set(deletedPcapIds);
        setPcaps(prev => prev.filter(p => !idSet.has(p.id)));
      }
    }
  };

  // ═══════════════════════════════════════════
  //  渲染
  // ═══════════════════════════════════════════

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* 页面标题 */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">{t('title')}</h1>
        <p className="text-sm text-gray-500 mt-1">{t('description')}</p>
      </div>

      {/* 提示消息 */}
      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg text-sm font-medium ${
          toast.type === 'success' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'
        }`}>
          {toast.message}
        </div>
      )}

      {/* ── 区域 1：统一上传区 ── */}
      <UnifiedUploadPanel
        isUploading={isUploading}
        uploadError={uploadError}
        onSubmit={handleSubmitUpload}
        onUploadComplete={() => {
          fetchPcaps();
          fetchBatches();
        }}
      />

      {/* ── 区域 2：批次总览 ── */}
      <BatchOverviewSection
        batches={batches}
        loading={batchesLoading}
        selectedBatchId={selectedBatchId}
        onSelectBatch={handleSelectBatch}
        onDeleteBatch={handleDeleteBatch}
        deletingBatchId={deletingBatchId}
      />

      {/* ── 区域 3：批次详情（内联） ── */}
      {batchDetail && (
        <BatchDetailPanel
          batch={batchDetail}
          onBack={() => { setSelectedBatchId(null); setBatchDetail(null); }}
          onStart={handleStartBatch}
          onCancel={handleCancelBatch}
          onRetryAll={handleRetryAll}
          onRetryFile={handleRetryFile}
          isStarting={isStartingBatch}
          isCancelling={isCancellingBatch}
          isRetrying={isRetryingBatch}
          embedded
        />
      )}

      {/* ── 区域 4：历史文件列表 ── */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-3">{t('allFiles')}</h2>
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
      </div>

      {/* ── 流水线时间线 ── */}
      {selectedPcap && (
        <div className="bg-white p-5 rounded-lg border border-gray-200 shadow-sm">
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
          {selectedPcap.status === 'processing' && (
            <div className="mb-3 px-3 py-2 bg-blue-50 border border-blue-200 rounded text-sm text-blue-700">
              {tPipeline('processingHint')}
            </div>
          )}
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

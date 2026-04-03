'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Fragment } from 'react';
import {
  ArrowLeft, Play, XCircle, RotateCcw, ExternalLink,
  CheckCircle, AlertCircle, Loader2, FileText, Clock,
  Ban, Copy, Search, Zap, Shield, Layers, ChevronDown, ChevronUp,
} from 'lucide-react';
import type { BatchDetail, BatchFileRecord, BatchJob } from '@/lib/api/types';
import { api } from '@/lib/api';

interface Props {
  batch: BatchDetail;
  onBack?: () => void;
  onStart: () => void;
  onCancel: () => void;
  onRetryAll: () => void;
  onRetryFile: (fileId: string) => void;
  isStarting: boolean;
  isCancelling: boolean;
  isRetrying: boolean;
  /** 内嵌模式：隐藏返回箭头，调整头部布局 */
  embedded?: boolean;
}

/** 批次详情面板 */
export default function BatchDetailPanel({
  batch, onBack, onStart, onCancel, onRetryAll, onRetryFile,
  isStarting, isCancelling, isRetrying, embedded,
}: Props) {
  const t = useTranslations('batches');
  const [expandedFile, setExpandedFile] = useState<string | null>(null);
  const [jobHistory, setJobHistory] = useState<Record<string, BatchJob[]>>({});
  const [loadingJobs, setLoadingJobs] = useState<string | null>(null);

  const canStart = batch.status === 'created' || batch.status === 'uploading';
  const canCancel = ['created', 'uploading', 'processing'].includes(batch.status);
  const canRetry = ['partial_failure', 'failed', 'cancelled'].includes(batch.status);
  const hasFailedFiles = batch.files.some(f => f.status === 'failed' && !f.reject_reason);

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatLatency = (ms: number | null) => {
    if (ms === null || ms === undefined) return '-';
    if (ms < 1000) return `${Math.round(ms)} ms`;
    return `${(ms / 1000).toFixed(1)} s`;
  };

  const statusIcon = (status: string) => {
    switch (status) {
      case 'done': case 'completed': return <CheckCircle className="w-4 h-4 text-green-500" />;
      case 'failed': return <AlertCircle className="w-4 h-4 text-red-500" />;
      case 'parsing': case 'featurizing': case 'detecting': case 'aggregating': case 'processing':
        return <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />;
      case 'queued': return <Clock className="w-4 h-4 text-gray-400" />;
      case 'rejected': return <Ban className="w-4 h-4 text-red-500" />;
      case 'duplicate': return <Copy className="w-4 h-4 text-yellow-500" />;
      case 'accepted': return <FileText className="w-4 h-4 text-blue-500" />;
      case 'cancelled': return <XCircle className="w-4 h-4 text-gray-500" />;
      default: return <FileText className="w-4 h-4 text-gray-400" />;
    }
  };

  const fileStatusColor = (status: string) => {
    switch (status) {
      case 'done': return 'bg-green-100 text-green-800';
      case 'failed': return 'bg-red-100 text-red-800';
      case 'rejected': return 'bg-red-100 text-red-800';
      case 'duplicate': return 'bg-yellow-100 text-yellow-800';
      case 'parsing': case 'featurizing': case 'detecting': case 'aggregating':
        return 'bg-blue-100 text-blue-800';
      case 'queued': return 'bg-gray-100 text-gray-600';
      case 'accepted': return 'bg-indigo-100 text-indigo-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const batchStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'bg-green-100 text-green-800';
      case 'processing': return 'bg-blue-100 text-blue-800';
      case 'failed': return 'bg-red-100 text-red-800';
      case 'partial_failure': return 'bg-yellow-100 text-yellow-800';
      case 'cancelled': return 'bg-gray-100 text-gray-800';
      default: return 'bg-indigo-100 text-indigo-800';
    }
  };

  const stageIcon = (status: string) => {
    switch (status) {
      case 'parsing': return <Search className="w-3 h-3" />;
      case 'featurizing': return <Zap className="w-3 h-3" />;
      case 'detecting': return <Shield className="w-3 h-3" />;
      case 'aggregating': return <Layers className="w-3 h-3" />;
      default: return null;
    }
  };

  const toggleJobHistory = async (fileId: string) => {
    if (expandedFile === fileId) {
      setExpandedFile(null);
      return;
    }
    setExpandedFile(fileId);
    if (!jobHistory[fileId]) {
      setLoadingJobs(fileId);
      try {
        const jobs = await api.getBatchFileJobs(batch.id, fileId);
        setJobHistory(prev => ({ ...prev, [fileId]: jobs }));
      } catch {
        // 静默处理
      } finally {
        setLoadingJobs(null);
      }
    }
  };

  const completed = batch.completed_files;
  const failed = batch.failed_files;
  const total = batch.total_files;
  const pctDone = total > 0 ? Math.round((completed / total) * 100) : 0;

  return (
    <div className="space-y-4">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {!embedded && (
            <button onClick={onBack} className="text-gray-500 hover:text-gray-700">
              <ArrowLeft className="w-5 h-5" />
            </button>
          )}
          <div>
            <h2 className="text-lg font-semibold text-gray-900">{batch.name}</h2>
            <div className="flex items-center gap-2 mt-1">
              <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${batchStatusColor(batch.status)}`}>
                {t(batch.status as any)}
              </span>
              {batch.source && <span className="text-xs text-gray-400">{batch.source}</span>}
              {batch.tags && batch.tags.length > 0 && (
                <div className="flex gap-1">
                  {batch.tags.map(tag => (
                    <span key={tag} className="px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded text-xs">{tag}</span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* 操作按钮 */}
        <div className="flex gap-2">
          {canStart && (
            <button
              onClick={onStart}
              disabled={isStarting}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50 text-sm"
            >
              <Play className="w-4 h-4" />
              {isStarting ? t('starting') : t('startProcessing')}
            </button>
          )}
          {canCancel && (
            <button
              onClick={onCancel}
              disabled={isCancelling}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50 text-sm"
            >
              <XCircle className="w-4 h-4" />
              {isCancelling ? t('cancelling') : t('cancel')}
            </button>
          )}
          {canRetry && hasFailedFiles && (
            <button
              onClick={onRetryAll}
              disabled={isRetrying}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-yellow-600 text-white rounded hover:bg-yellow-700 disabled:opacity-50 text-sm"
            >
              <RotateCcw className="w-4 h-4" />
              {isRetrying ? t('retrying') : t('retryAll')}
            </button>
          )}
          {(batch.status === 'completed' || batch.status === 'partial_failure') && (
            <a
              href={`/flows?pcap_id=${batch.files.filter(f => f.pcap_id).map(f => f.pcap_id).join(',')}`}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 text-white rounded hover:bg-green-700 text-sm"
            >
              <ExternalLink className="w-4 h-4" />
              {t('jumpToAnalysis')}
            </a>
          )}
        </div>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatCard label={t('files')} value={`${total}`} />
        <StatCard label={t('progress')} value={`${pctDone}%`} sub={`${completed}/${total}`} />
        <StatCard label={t('flowCount')} value={`${batch.total_flow_count}`} />
        <StatCard label={t('alertCount')} value={`${batch.total_alert_count}`} />
        <StatCard label={t('latency')} value={formatLatency(batch.total_latency_ms)} />
      </div>

      {/* 进度条 */}
      {batch.status === 'processing' && total > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <div className="flex justify-between text-sm text-gray-600 mb-2">
            <span>{t('progress')}</span>
            <span>{completed + failed} / {total}</span>
          </div>
          <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden flex">
            <div className="h-full bg-green-500 transition-all duration-300" style={{ width: `${(completed / total) * 100}%` }} />
            <div className="h-full bg-red-500 transition-all duration-300" style={{ width: `${(failed / total) * 100}%` }} />
          </div>
        </div>
      )}

      {/* 文件列表 */}
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-200">
          <h3 className="text-sm font-semibold text-gray-900">{t('fileList')}</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left">
                <th className="px-4 py-2 font-medium text-gray-600 w-8">#</th>
                <th className="px-4 py-2 font-medium text-gray-600">{t('filename')}</th>
                <th className="px-4 py-2 font-medium text-gray-600">{t('fileSize')}</th>
                <th className="px-4 py-2 font-medium text-gray-600">{t('fileStatus')}</th>
                <th className="px-4 py-2 font-medium text-gray-600">{t('flowCount')}</th>
                <th className="px-4 py-2 font-medium text-gray-600">{t('alertCount')}</th>
                <th className="px-4 py-2 font-medium text-gray-600">{t('latency')}</th>
                <th className="px-4 py-2 font-medium text-gray-600">{t('actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {batch.files.map(f => (
                <Fragment key={f.id}>
                  <tr className={`hover:bg-gray-50 ${f.status === 'failed' ? 'bg-red-50/30' : ''}`}>
                    <td className="px-4 py-2 text-gray-400">{f.sequence}</td>
                    <td className="px-4 py-2 text-gray-700 font-medium">{f.original_filename}</td>
                    <td className="px-4 py-2 text-gray-500">{formatSize(f.size_bytes)}</td>
                    <td className="px-4 py-2">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${fileStatusColor(f.status)}`}>
                        {statusIcon(f.status)}
                        {stageIcon(f.status)}
                        {t(f.status as any)}
                      </span>
                      {f.error_message && (
                        <p className="text-xs text-red-500 mt-0.5 max-w-xs truncate" title={f.error_message}>
                          {f.error_message}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-2 text-gray-600">{f.flow_count || '-'}</td>
                    <td className="px-4 py-2 text-gray-600">{f.alert_count || '-'}</td>
                    <td className="px-4 py-2 text-gray-500">{formatLatency(f.latency_ms)}</td>
                    <td className="px-4 py-2">
                      <div className="flex items-center gap-2">
                        {f.status === 'failed' && !f.reject_reason && (
                          <button
                            onClick={() => onRetryFile(f.id)}
                            className="text-yellow-600 hover:text-yellow-800 text-xs font-medium"
                          >
                            {t('retry')}
                          </button>
                        )}
                        <button
                          onClick={() => toggleJobHistory(f.id)}
                          className="text-gray-500 hover:text-gray-700"
                        >
                          {expandedFile === f.id
                            ? <ChevronUp className="w-4 h-4" />
                            : <ChevronDown className="w-4 h-4" />
                          }
                        </button>
                      </div>
                    </td>
                  </tr>
                  {/* 展开的作业历史 */}
                  {expandedFile === f.id && (
                    <tr key={`${f.id}-jobs`}>
                      <td colSpan={8} className="px-4 py-3 bg-gray-50">
                        {loadingJobs === f.id ? (
                          <div className="flex items-center gap-2 text-sm text-gray-500">
                            <Loader2 className="w-4 h-4 animate-spin" />
                            {t('jobHistory')}...
                          </div>
                        ) : jobHistory[f.id] && jobHistory[f.id].length > 0 ? (
                          <div>
                            <div className="text-xs font-medium text-gray-600 mb-2">{t('jobHistory')}</div>
                            <div className="space-y-1">
                              {jobHistory[f.id].map(job => (
                                <div key={job.id} className="flex items-center gap-3 text-xs bg-white rounded px-3 py-2 border border-gray-100">
                                  <span className="text-gray-400 font-mono">{job.id.slice(0, 8)}</span>
                                  <span className={`px-1.5 py-0.5 rounded font-medium ${
                                    job.status === 'completed' ? 'bg-green-100 text-green-800' :
                                    job.status === 'failed' ? 'bg-red-100 text-red-800' :
                                    job.status === 'running' ? 'bg-blue-100 text-blue-800' :
                                    'bg-gray-100 text-gray-600'
                                  }`}>
                                    {job.status}
                                  </span>
                                  {job.current_stage && <span className="text-gray-500">{job.current_stage}</span>}
                                  <span className="text-gray-400">#{job.retry_count}</span>
                                  {job.latency_ms && <span className="text-gray-400">{formatLatency(job.latency_ms)}</span>}
                                  {job.error_message && (
                                    <span className="text-red-500 truncate max-w-xs" title={job.error_message}>
                                      {job.error_message}
                                    </span>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : (
                          <div className="text-xs text-gray-400">{t('jobHistory')}: -</div>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-3">
      <div className="text-xs text-gray-500">{label}</div>
      <div className="text-lg font-semibold text-gray-900 mt-1">{value}</div>
      {sub && <div className="text-xs text-gray-400">{sub}</div>}
    </div>
  );
}

'use client';

import { useTranslations } from 'next-intl';
import type { Batch } from '@/lib/api/types';

interface Props {
  batches: Batch[];
  onSelect: (batchId: string) => void;
  onDelete?: (batchId: string) => void;
  deletingId?: string | null;
}

/** 批次列表表格 */
export default function BatchListTable({ batches, onSelect, onDelete, deletingId }: Props) {
  const t = useTranslations('batches');

  const statusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'bg-green-100 text-green-800';
      case 'processing': return 'bg-blue-100 text-blue-800';
      case 'failed': return 'bg-red-100 text-red-800';
      case 'partial_failure': return 'bg-yellow-100 text-yellow-800';
      case 'cancelled': return 'bg-gray-100 text-gray-800';
      case 'created': case 'uploading': return 'bg-indigo-100 text-indigo-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatTime = (iso: string) => {
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  };

  const formatLatency = (ms: number | null) => {
    if (ms === null || ms === undefined) return '-';
    if (ms < 1000) return `${Math.round(ms)} ms`;
    return `${(ms / 1000).toFixed(1)} s`;
  };

  if (batches.length === 0) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-8 text-center text-gray-500">
        {t('empty')}
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-left">
              <th className="px-4 py-3 font-medium text-gray-600">{t('name')}</th>
              <th className="px-4 py-3 font-medium text-gray-600">{t('status')}</th>
              <th className="px-4 py-3 font-medium text-gray-600">{t('files')}</th>
              <th className="px-4 py-3 font-medium text-gray-600">{t('progress')}</th>
              <th className="px-4 py-3 font-medium text-gray-600">{t('flowCount')}</th>
              <th className="px-4 py-3 font-medium text-gray-600">{t('alertCount')}</th>
              <th className="px-4 py-3 font-medium text-gray-600">{t('totalSize')}</th>
              <th className="px-4 py-3 font-medium text-gray-600">{t('latency')}</th>
              <th className="px-4 py-3 font-medium text-gray-600">{t('createdAt')}</th>
              <th className="px-4 py-3 font-medium text-gray-600">{t('actions')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {batches.map(b => (
              <tr key={b.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 font-medium text-gray-900">{b.name}</td>
                <td className="px-4 py-3">
                  <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${statusColor(b.status)}`}>
                    {t(b.status as any)}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-600">{b.total_files}</td>
                <td className="px-4 py-3">
                  <BatchProgressBar
                    completed={b.completed_files}
                    failed={b.failed_files}
                    total={b.total_files}
                  />
                </td>
                <td className="px-4 py-3 text-gray-600">{b.total_flow_count}</td>
                <td className="px-4 py-3 text-gray-600">{b.total_alert_count}</td>
                <td className="px-4 py-3 text-gray-500">{formatSize(b.total_size_bytes)}</td>
                <td className="px-4 py-3 text-gray-500">{formatLatency(b.total_latency_ms)}</td>
                <td className="px-4 py-3 text-gray-500 text-xs">{formatTime(b.created_at)}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => onSelect(b.id)}
                      className="text-indigo-600 hover:text-indigo-800 text-xs font-medium"
                    >
                      {t('viewDetail')}
                    </button>
                    {onDelete && (
                      <button
                        onClick={() => onDelete(b.id)}
                        disabled={deletingId === b.id || b.status === 'processing'}
                        className="text-red-600 hover:text-red-800 text-xs font-medium disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        {deletingId === b.id ? t('deleting') : t('delete')}
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** 内联进度条 */
function BatchProgressBar({ completed, failed, total }: { completed: number; failed: number; total: number }) {
  if (total === 0) return <span className="text-gray-400 text-xs">-</span>;
  const pctDone = (completed / total) * 100;
  const pctFail = (failed / total) * 100;

  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-2 bg-gray-200 rounded-full overflow-hidden flex">
        <div className="h-full bg-green-500 transition-all" style={{ width: `${pctDone}%` }} />
        <div className="h-full bg-red-500 transition-all" style={{ width: `${pctFail}%` }} />
      </div>
      <span className="text-xs text-gray-500">{completed + failed}/{total}</span>
    </div>
  );
}

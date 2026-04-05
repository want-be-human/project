'use client';

import { FileText, CheckCircle, AlertCircle, Loader2, Trash2 } from 'lucide-react';
import { PcapFile } from '@/lib/api/types';
import { useTranslations } from 'next-intl';
import { formatBytes } from '@/lib/utils';
import { format } from 'date-fns';

interface PcapListTableProps {
  pcaps: PcapFile[];
  onSelect?: (pcap: PcapFile) => void;
  selectedId?: string | null;
  onDelete?: (id: string) => void;
  deletingId?: string | null;
}

export default function PcapListTable({ pcaps, onSelect, selectedId, onDelete, deletingId }: PcapListTableProps) {
  const t = useTranslations('pcaps');

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'done': return <CheckCircle className="w-4 h-4 text-green-500" />;
      case 'processing': return <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />;
      case 'failed': return <AlertCircle className="w-4 h-4 text-red-500" />;
      default: return <FileText className="w-4 h-4 text-gray-400" />;
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
      <table className="w-full text-sm text-left">
        <thead className="bg-gray-50 text-gray-700 font-medium border-b border-gray-200">
          <tr>
            <th className="px-6 py-3">{t('filename')}</th>
            <th className="px-6 py-3">{t('size')}</th>
            <th className="px-6 py-3">{t('uploadedAt')}</th>
            <th className="px-6 py-3">{t('status')}</th>
            <th className="px-6 py-3">{t('flows')}</th>
            <th className="px-6 py-3">{t('alerts')}</th>
            <th className="px-6 py-3 text-right">{t('actions')}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {pcaps.length === 0 ? (
            <tr>
              <td colSpan={7} className="px-6 py-8 text-center text-gray-500">
                {t('empty')}
              </td>
            </tr>
          ) : (
            pcaps.map((pcap) => (
              <tr key={pcap.id} onClick={() => onSelect?.(pcap)} className={`hover:bg-gray-50 group transition-colors cursor-pointer ${selectedId === pcap.id ? 'bg-blue-50 ring-1 ring-inset ring-blue-200' : ''}`}>
                <td className="px-6 py-3 font-medium text-gray-900">{pcap.filename}</td>
                <td className="px-6 py-3 text-gray-500">{formatBytes(pcap.size_bytes)}</td>
                <td className="px-6 py-3 text-gray-500">
                  {pcap.created_at ? format(new Date(pcap.created_at), 'yyyy-MM-dd HH:mm') : '-'}
                </td>
                <td className="px-6 py-3">
                  <div className="flex items-center gap-2">
                    {getStatusIcon(pcap.status)}
                    {pcap.status === 'failed' ? (
                      <span className="text-red-600 font-medium">{t('statusFailed')}</span>
                    ) : (
                      <span className="capitalize text-gray-700">{pcap.status}</span>
                    )}
                    {pcap.status === 'processing' && pcap.progress && (
                      <span className="text-xs text-blue-600">({pcap.progress}%)</span>
                    )}
                  </div>
                  {pcap.status === 'failed' && pcap.error_message && (
                    <p className="mt-1 text-xs text-red-500" title={pcap.error_message}>
                      {t('errorTooltip')}：{pcap.error_message}
                    </p>
                  )}
                </td>
                <td className="px-6 py-3 text-gray-600">{pcap.flow_count || '-'}</td>
                <td className="px-6 py-3 text-gray-600">{pcap.alert_count || '-'}</td>
                <td className="px-6 py-3 text-right">
                  <div className="inline-flex items-center gap-2">
                    {onDelete && (
                      <button
                        onClick={(e) => { e.stopPropagation(); onDelete(pcap.id); }}
                        disabled={pcap.status === 'processing' || deletingId === pcap.id}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-red-700 bg-red-50 rounded hover:bg-red-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        aria-label={t('delete')}
                      >
                        {deletingId === pcap.id ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          <Trash2 className="w-3 h-3" />
                        )}
                        {t('delete')}
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

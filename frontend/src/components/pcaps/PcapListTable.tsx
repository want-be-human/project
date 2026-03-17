'use client';

import { Play, FileText, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { PcapFile } from '@/lib/api/types';
import { useTranslations } from 'next-intl';
import { formatBytes } from '@/lib/utils';
import { format } from 'date-fns';

interface PcapListTableProps {
  pcaps: PcapFile[];
  onProcess: (id: string) => void;
  processingId: string | null;
  onSelect?: (pcap: PcapFile) => void;
  selectedId?: string | null;
}

export default function PcapListTable({ pcaps, onProcess, processingId, onSelect, selectedId }: PcapListTableProps) {
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
                    <span className="capitalize text-gray-700">{pcap.status}</span>
                    {pcap.status === 'processing' && pcap.progress && (
                      <span className="text-xs text-blue-600">({pcap.progress}%)</span>
                    )}
                  </div>
                </td>
                <td className="px-6 py-3 text-gray-600">{pcap.flow_count || '-'}</td>
                <td className="px-6 py-3 text-gray-600">{pcap.alert_count || '-'}</td>
                <td className="px-6 py-3 text-right">
                  <button
                    onClick={(e) => { e.stopPropagation(); onProcess(pcap.id); }}
                    disabled={pcap.status === 'processing' || processingId === pcap.id}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-blue-700 bg-blue-50 rounded hover:bg-blue-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {processingId === pcap.id ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <Play className="w-3 h-3" />
                    )}
                    {t('analyze')}
                  </button>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

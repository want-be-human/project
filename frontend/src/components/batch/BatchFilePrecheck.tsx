'use client';

import { useTranslations } from 'next-intl';
import { CheckCircle, XCircle, Copy } from 'lucide-react';
import type { BatchFileRecord } from '@/lib/api/types';

interface Props {
  files: BatchFileRecord[];
}

/** 上传预检结果表 */
export default function BatchFilePrecheck({ files }: Props) {
  const t = useTranslations('batches');

  if (files.length === 0) return null;

  const accepted = files.filter(f => f.status === 'accepted').length;
  const rejected = files.filter(f => f.status === 'rejected').length;
  const duplicate = files.filter(f => f.status === 'duplicate').length;

  const statusIcon = (status: string) => {
    if (status === 'accepted') return <CheckCircle className="w-4 h-4 text-green-500" />;
    if (status === 'rejected') return <XCircle className="w-4 h-4 text-red-500" />;
    if (status === 'duplicate') return <Copy className="w-4 h-4 text-yellow-500" />;
    return null;
  };

  const statusColor = (status: string) => {
    if (status === 'accepted') return 'bg-green-100 text-green-800';
    if (status === 'rejected') return 'bg-red-100 text-red-800';
    if (status === 'duplicate') return 'bg-yellow-100 text-yellow-800';
    return 'bg-gray-100 text-gray-800';
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <h3 className="text-sm font-semibold text-gray-900 mb-3">{t('precheckTitle')}</h3>

      {/* 统计摘要 */}
      <div className="flex gap-4 mb-3 text-sm">
        <span className="text-green-600">{t('accepted')}: {accepted}</span>
        {rejected > 0 && <span className="text-red-600">{t('rejected')}: {rejected}</span>}
        {duplicate > 0 && <span className="text-yellow-600">{t('duplicate')}: {duplicate}</span>}
      </div>

      {/* 文件表 */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-left">
              <th className="px-3 py-2 font-medium text-gray-600">{t('filename')}</th>
              <th className="px-3 py-2 font-medium text-gray-600">{t('fileSize')}</th>
              <th className="px-3 py-2 font-medium text-gray-600">{t('fileStatus')}</th>
              <th className="px-3 py-2 font-medium text-gray-600">{t('reason')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {files.map(f => (
              <tr key={f.id} className={f.status !== 'accepted' ? 'bg-red-50/30' : ''}>
                <td className="px-3 py-2 text-gray-700">{f.original_filename}</td>
                <td className="px-3 py-2 text-gray-500">{formatSize(f.size_bytes)}</td>
                <td className="px-3 py-2">
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${statusColor(f.status)}`}>
                    {statusIcon(f.status)}
                    {t(f.status as any)}
                  </span>
                </td>
                <td className="px-3 py-2 text-gray-500 text-xs">{f.reject_reason || '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

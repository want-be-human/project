'use client';

import { useTranslations } from 'next-intl';
import { Layers, Loader2 } from 'lucide-react';
import type { Batch } from '@/lib/api/types';
import BatchListTable from '@/components/batch/BatchListTable';

/**
 * 批次总览区域。
 *
 * 展示所有批次列表，点击可选中查看详情。
 * 直接复用 BatchListTable 组件。
 */
interface BatchOverviewSectionProps {
  batches: Batch[];
  loading: boolean;
  selectedBatchId: string | null;
  onSelectBatch: (batchId: string) => void;
  onDeleteBatch?: (batchId: string) => void;
  deletingBatchId?: string | null;
}

export default function BatchOverviewSection({
  batches,
  loading,
  selectedBatchId,
  onSelectBatch,
  onDeleteBatch,
  deletingBatchId,
}: BatchOverviewSectionProps) {
  const t = useTranslations('pcaps');
  const tCommon = useTranslations('common');

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <Layers className="w-5 h-5 text-indigo-600" />
        <h2 className="text-lg font-semibold text-gray-900">{t('batchSection')}</h2>
        {batches.length > 0 && (
          <span className="px-2 py-0.5 bg-indigo-100 text-indigo-700 text-xs font-medium rounded-full">
            {batches.length}
          </span>
        )}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-8 text-gray-500">
          <Loader2 className="w-5 h-5 animate-spin mr-2" />
          {tCommon('loading')}
        </div>
      ) : batches.length === 0 ? (
        <div className="bg-white rounded-lg border border-gray-200 p-6 text-center text-gray-500 text-sm">
          {t('batchSectionEmpty')}
        </div>
      ) : (
        <BatchListTable
          batches={batches}
          onSelect={onSelectBatch}
          onDelete={onDeleteBatch}
          deletingId={deletingBatchId}
        />
      )}
    </div>
  );
}

'use client';

import { useTranslations } from 'next-intl';
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react';

interface PaginationProps {
  total: number;
  limit: number;
  offset: number;
  onPageChange: (offset: number) => void;
  onPageSizeChange: (limit: number) => void;
  pageSizeOptions?: number[];
}

export default function Pagination({
  total,
  limit,
  offset,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = [20, 50, 100],
}: PaginationProps) {
  const t = useTranslations('pagination');

  const totalPages = Math.max(1, Math.ceil(total / limit));
  const currentPage = Math.floor(offset / limit) + 1;

  const canPrev = currentPage > 1;
  const canNext = currentPage < totalPages;

  const goFirst = () => onPageChange(0);
  const goPrev = () => onPageChange(Math.max(0, offset - limit));
  const goNext = () => onPageChange(offset + limit);
  const goLast = () => onPageChange((totalPages - 1) * limit);

  const btnBase =
    'inline-flex items-center justify-center w-8 h-8 rounded text-sm transition-colors';
  const btnEnabled = 'text-gray-700 hover:bg-gray-100 cursor-pointer';
  const btnDisabled = 'text-gray-300 cursor-not-allowed';

  return (
    <div className="flex items-center justify-between px-4 py-2 bg-white border-t border-gray-200 text-sm text-gray-600 shrink-0">
      {/* Left: page size + total */}
      <div className="flex items-center gap-3">
        <span className="flex items-center gap-1.5">
          {t('pageSize')}
          <select
            value={limit}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            className="border border-gray-300 rounded px-1.5 py-0.5 text-sm bg-white cursor-pointer focus:ring-1 focus:ring-blue-500"
          >
            {pageSizeOptions.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
          {t('records')}
        </span>
        <span className="text-gray-400">|</span>
        <span>{t('totalRecords', { count: total })}</span>
      </div>

      {/* Right: navigation */}
      <div className="flex items-center gap-1">
        <button
          onClick={goFirst}
          disabled={!canPrev}
          className={`${btnBase} ${canPrev ? btnEnabled : btnDisabled}`}
          title={t('first')}
        >
          <ChevronsLeft className="w-4 h-4" />
        </button>
        <button
          onClick={goPrev}
          disabled={!canPrev}
          className={`${btnBase} ${canPrev ? btnEnabled : btnDisabled}`}
          title={t('previous')}
        >
          <ChevronLeft className="w-4 h-4" />
        </button>

        <span className="px-2 select-none">
          {t('page', { current: currentPage, total: totalPages })}
        </span>

        <button
          onClick={goNext}
          disabled={!canNext}
          className={`${btnBase} ${canNext ? btnEnabled : btnDisabled}`}
          title={t('next')}
        >
          <ChevronRight className="w-4 h-4" />
        </button>
        <button
          onClick={goLast}
          disabled={!canNext}
          className={`${btnBase} ${canNext ? btnEnabled : btnDisabled}`}
          title={t('last')}
        >
          <ChevronsRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}

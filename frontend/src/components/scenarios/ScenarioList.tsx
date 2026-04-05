'use client';

import { Scenario } from '@/lib/api/types';
import { Play, Archive, ArchiveRestore, Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';

interface Props {
  scenarios: Scenario[];
  viewMode: 'active' | 'archived';
  onViewModeChange: (mode: 'active' | 'archived') => void;
  onSelect: (scenario: Scenario) => void;
  onArchive: (scenario: Scenario) => void;
  onUnarchive: (scenario: Scenario) => void;
  onDeleteRequest: (scenario: Scenario) => void;
  selectedId?: string;
  runningId?: string;
}

export default function ScenarioList({
  scenarios,
  viewMode,
  onViewModeChange,
  onSelect,
  onArchive,
  onUnarchive,
  onDeleteRequest,
  selectedId,
  runningId,
}: Props) {
  const t = useTranslations('scenarios');

  return (
    <div className="bg-white rounded-lg shadow border border-gray-200 flex flex-col min-h-0">
      {/* 头部 */}
      <div className="px-4 py-3 border-b border-gray-200 flex justify-between items-center shrink-0">
        <h2 className="text-lg font-semibold text-gray-800">{t('listTitle')}</h2>
        <span className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded">
          {t('available', { count: scenarios.length })}
        </span>
      </div>

      {/* 标签页 */}
      <div className="flex border-b border-gray-200 shrink-0">
        <button
          onClick={() => onViewModeChange('active')}
          className={`flex-1 py-2 text-sm font-medium transition-colors ${
            viewMode === 'active'
              ? 'text-indigo-600 border-b-2 border-indigo-500'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          {t('tabActive')}
        </button>
        <button
          onClick={() => onViewModeChange('archived')}
          className={`flex-1 py-2 text-sm font-medium transition-colors ${
            viewMode === 'archived'
              ? 'text-indigo-600 border-b-2 border-indigo-500'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          {t('tabArchived')}
        </button>
      </div>

      {/* 列表 */}
      <div className="divide-y divide-gray-100 overflow-y-auto flex-1">
        {scenarios.length === 0 && (
          <div className="p-6 text-center text-sm text-gray-400">
            {viewMode === 'active' ? t('emptyActive') : t('emptyArchived')}
          </div>
        )}
        {scenarios.map((s) => {
          const isRunning = runningId === s.id;
          const isArchived = s.status === 'archived';

          return (
            <div
              key={s.id}
              className={`p-4 cursor-pointer transition-colors ${
                selectedId === s.id
                  ? 'bg-indigo-50 border-l-4 border-indigo-500'
                  : 'hover:bg-gray-50 border-l-4 border-transparent'
              }`}
              onClick={() => onSelect(s)}
            >
              <div className="flex justify-between items-start mb-2">
                <h3 className="font-medium text-gray-900">{s.name}</h3>
                <div className="flex items-center gap-1 shrink-0 ml-2">
                  {isRunning && (
                    <span className="flex items-center text-xs font-medium text-amber-600 bg-amber-50 px-2 py-0.5 rounded">
                      <Play className="w-3 h-3 mr-1 animate-pulse" /> {t('running')}
                    </span>
                  )}
                  {isArchived && !isRunning && (
                    <span className="text-xs font-medium text-gray-400 bg-gray-100 px-2 py-0.5 rounded">
                      {t('archived')}
                    </span>
                  )}
                </div>
              </div>

              {s.description && (
                <p className="text-sm text-gray-500 mb-3 line-clamp-2">{s.description}</p>
              )}

              <div className="flex flex-wrap gap-1 mb-3">
                {(s.tags || []).map((tag) => (
                  <span
                    key={tag}
                    className="text-[10px] uppercase font-semibold text-gray-600 bg-gray-100 border border-gray-200 px-1.5 py-0.5 rounded"
                  >
                    {tag}
                  </span>
                ))}
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs text-gray-500 mb-1">
                <div>
                  <span className="font-semibold text-gray-400">{t('minAlerts')}</span>{' '}
                  {s.expectations?.min_alerts || 0}
                </div>
                <div>
                  <span className="font-semibold text-gray-400">{t('dryRun')}</span>{' '}
                  {s.expectations?.dry_run_required ? t('required') : t('skipped')}
                </div>
              </div>

              <div className="text-xs text-gray-500 mb-3">
                <span className="font-semibold text-gray-400">{t('pcap')}</span>{' '}
                <span className="font-mono text-[10px]">{s.pcap_ref?.pcap_id?.slice(0, 18)}...</span>
              </div>

              {/* 操作按钮 — 阻止点击事件冒泡到行选中 */}
              <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
                {!isArchived ? (
                  <button
                    onClick={() => onArchive(s)}
                    disabled={isRunning}
                    title={isRunning ? t('archiveDisabledRunning') : t('archiveBtn')}
                    className="flex items-center gap-1 text-xs px-2 py-1 rounded border border-gray-200 text-gray-600 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <Archive className="w-3 h-3" /> {t('archiveBtn')}
                  </button>
                ) : (
                  <>
                    <button
                      onClick={() => onUnarchive(s)}
                      className="flex items-center gap-1 text-xs px-2 py-1 rounded border border-gray-200 text-gray-600 hover:bg-gray-100"
                    >
                      <ArchiveRestore className="w-3 h-3" /> {t('unarchiveBtn')}
                    </button>
                    <button
                      onClick={() => onDeleteRequest(s)}
                      disabled={isRunning}
                      title={isRunning ? t('deleteDisabledRunning') : t('deleteBtn')}
                      className="flex items-center gap-1 text-xs px-2 py-1 rounded border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      <Trash2 className="w-3 h-3" /> {t('deleteBtn')}
                    </button>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

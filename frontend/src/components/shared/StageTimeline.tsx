'use client';

import { useState, ReactNode } from 'react';
import { PipelineStageStatus } from '@/lib/api/types';
import {
  CheckCircle2, XCircle, Loader2, Clock, SkipForward,
  ChevronDown, ChevronRight, Activity,
} from 'lucide-react';
import { useTranslations } from 'next-intl';

/**
 * 通用阶段时间线组件
 *
 * 可用于 Pipeline 和 Scenario 的阶段展示，通过 props 配置 i18n 命名空间和阶段映射。
 */

// 导出工具函数供测试使用
export function formatDateTime(isoString: string): string {
  const d = new Date(isoString);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export function computeStageStats(stages: Array<{ status: string }>): {
  total: number;
  completed: number;
  failed: number;
  skipped: number;
  pending: number;
  running: number;
} {
  return {
    total: stages.length,
    completed: stages.filter(s => s.status === 'completed').length,
    failed: stages.filter(s => s.status === 'failed').length,
    skipped: stages.filter(s => s.status === 'skipped').length,
    pending: stages.filter(s => s.status === 'pending').length,
    running: stages.filter(s => s.status === 'running').length,
  };
}

export function getStatusStyle(status: string) {
  switch (status as PipelineStageStatus | 'success') {
    case 'success':
    case 'completed':
      return {
        badge: 'bg-green-100 text-green-800',
        icon: <CheckCircle2 className="w-4 h-4 text-green-500 shrink-0" />,
        overallBg: 'bg-green-50 border-green-200 text-green-800',
      };
    case 'failed':
      return {
        badge: 'bg-red-100 text-red-800',
        icon: <XCircle className="w-4 h-4 text-red-500 shrink-0" />,
        overallBg: 'bg-red-50 border-red-200 text-red-800',
      };
    case 'running':
      return {
        badge: 'bg-blue-100 text-blue-800',
        icon: <Loader2 className="w-4 h-4 text-blue-500 animate-spin shrink-0" />,
        overallBg: 'bg-blue-50 border-blue-200 text-blue-800',
      };
    case 'skipped':
      return {
        badge: 'bg-gray-100 text-gray-500',
        icon: <SkipForward className="w-4 h-4 text-gray-400 shrink-0" />,
        overallBg: 'bg-gray-50 border-gray-200 text-gray-600',
      };
    case 'pending':
    default:
      return {
        badge: 'bg-gray-100 text-gray-500',
        icon: <Clock className="w-4 h-4 text-gray-400 shrink-0" />,
        overallBg: 'bg-gray-50 border-gray-200 text-gray-600',
      };
  }
}

interface StageTimelineProps<T extends {
  stage_name: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  latency_ms: number | null;
  key_metrics: Record<string, any>;
  error_summary: string | null;
  input_summary: Record<string, any>;
  output_summary: Record<string, any>;
}> {
  run: {
    status: string;
    started_at: string | null;
    total_latency_ms: number | null;
    stages: T[];
  } | null;
  loading: boolean;
  error: string | null;
  stageI18nKeyMap: Record<string, string>;
  i18nNamespace: string;
  renderExtraDetail?: (stage: T) => ReactNode;
}

export default function StageTimeline<T extends {
  stage_name: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  latency_ms: number | null;
  key_metrics: Record<string, any>;
  error_summary: string | null;
  input_summary: Record<string, any>;
  output_summary: Record<string, any>;
}>({
  run,
  loading,
  error,
  stageI18nKeyMap,
  i18nNamespace,
  renderExtraDetail,
}: StageTimelineProps<T>) {
  const t = useTranslations(i18nNamespace);
  const [expandedStages, setExpandedStages] = useState<Set<string>>(new Set());

  const getStageLabel = (name: string): string => {
    const i18nKey = stageI18nKeyMap[name];
    if (i18nKey) {
      return t(i18nKey);
    }
    return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  };

  const getStatusLabel = (status: string): string => {
    const statusKeyMap: Record<string, string> = {
      pending: 'statusPending',
      running: 'statusRunning',
      completed: 'statusCompleted',
      failed: 'statusFailed',
      skipped: 'statusSkipped',
    };
    const i18nKey = statusKeyMap[status];
    if (i18nKey) {
      return t(i18nKey);
    }
    return status;
  };

  const toggleStage = (name: string) => {
    setExpandedStages(prev => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-500 py-4">
        <Loader2 className="w-4 h-4 animate-spin text-indigo-500" />
        <span>{t('loading')}</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
        {error}
      </div>
    );
  }

  if (!run) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-400 py-4">
        <Activity className="w-4 h-4" />
        <span>{t('noData')}</span>
      </div>
    );
  }

  const overallStyle = getStatusStyle(run.status);
  const stats = computeStageStats(run.stages);

  return (
    <div className="space-y-3">
      {/* 顶部总览 */}
      <div className={`px-4 py-3 rounded-lg border ${overallStyle.overallBg}`}>
        <div className="flex items-center gap-3">
          {overallStyle.icon}
          <div className="flex-1 min-w-0">
            <span className="font-semibold">{getStatusLabel(run.status)}</span>
            {run.started_at && (
              <span className="ml-3 text-xs opacity-70">
                {t('overviewStartedAt')}: {formatDateTime(run.started_at)}
              </span>
            )}
          </div>
          {run.total_latency_ms != null && (
            <span className="text-xs font-mono opacity-80 shrink-0">
              {t('overviewTotalLatency')}: {run.total_latency_ms.toFixed(0)} ms
            </span>
          )}
        </div>
        <div className="mt-2 flex gap-4 text-xs opacity-80">
          <span>{t('overviewStageStats', { completed: stats.completed, total: stats.total })}</span>
          {stats.failed > 0 && <span className="text-red-700">{stats.failed} {t('statusFailed')}</span>}
          {stats.skipped > 0 && <span>{stats.skipped} {t('statusSkipped')}</span>}
        </div>
      </div>

      {/* 阶段列表 */}
      {run.stages.length === 0 ? (
        <div className="text-sm text-gray-400 py-2">{t('noStages')}</div>
      ) : (
        <div className="space-y-2">
          {run.stages.map((stage) => {
            const stageStyle = getStatusStyle(stage.status);
            const isExpanded = expandedStages.has(stage.stage_name);
            const hasDetails = stage.error_summary || Object.keys(stage.key_metrics).length > 0 || renderExtraDetail;

            return (
              <div key={stage.stage_name} className="border border-gray-200 rounded-lg overflow-hidden">
                <button
                  onClick={() => hasDetails && toggleStage(stage.stage_name)}
                  className={`w-full px-4 py-3 flex items-center gap-3 text-left transition-colors ${
                    hasDetails ? 'hover:bg-gray-50 cursor-pointer' : 'cursor-default'
                  }`}
                  disabled={!hasDetails}
                >
                  {stageStyle.icon}
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-sm">{getStageLabel(stage.stage_name)}</div>
                    <div className="text-xs text-gray-500 mt-0.5">
                      <span className={`inline-block px-2 py-0.5 rounded ${stageStyle.badge}`}>
                        {getStatusLabel(stage.status)}
                      </span>
                      {stage.latency_ms != null && (
                        <span className="ml-2 font-mono">{stage.latency_ms.toFixed(0)} ms</span>
                      )}
                    </div>
                  </div>
                  {hasDetails && (
                    isExpanded ? <ChevronDown className="w-4 h-4 text-gray-400 shrink-0" /> : <ChevronRight className="w-4 h-4 text-gray-400 shrink-0" />
                  )}
                </button>

                {isExpanded && hasDetails && (
                  <div className="px-4 py-3 bg-gray-50 border-t border-gray-200 space-y-3 text-sm">
                    {stage.error_summary && (
                      <div>
                        <div className="font-medium text-red-700 mb-1">{t('detailError')}</div>
                        <div className="text-red-600 bg-red-50 px-3 py-2 rounded border border-red-200 font-mono text-xs">
                          {stage.error_summary}
                        </div>
                      </div>
                    )}

                    {renderExtraDetail && renderExtraDetail(stage)}

                    {Object.keys(stage.key_metrics).length > 0 && (
                      <div>
                        <div className="font-medium text-gray-700 mb-1">{t('detailKeyMetrics')}</div>
                        <div className="bg-white px-3 py-2 rounded border border-gray-200">
                          {Object.entries(stage.key_metrics).map(([k, v]) => (
                            <div key={k} className="flex justify-between text-xs py-0.5">
                              <span className="text-gray-600">{k}:</span>
                              <span className="font-mono text-gray-900">{JSON.stringify(v)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

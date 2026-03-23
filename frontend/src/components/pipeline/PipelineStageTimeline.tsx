'use client';

import { useState } from 'react';
import { PipelineRun, PipelineStageStatus, StageRecord } from '@/lib/api/types';
import {
  CheckCircle2, XCircle, Loader2, Clock, SkipForward,
  ChevronDown, ChevronRight, Activity,
} from 'lucide-react';
import { useTranslations } from 'next-intl';

/**
 * 阶段名称到 i18n 键名的映射表
 * 后端 stage_name → 前端 i18n 键名（pipeline 命名空间下）
 */
const STAGE_I18N_KEY_MAP: Record<string, string> = {
  parse:           'stageParse',
  feature_extract: 'stageFeatureExtract',
  detect:          'stageDetect',
  aggregate:       'stageAggregate',
  investigate:     'stageInvestigate',
  recommend:       'stageRecommend',
  compile_plan:    'stageCompilePlan',
  dry_run:         'stageDryRun',
  visualize:       'stageVisualize',
};

/**
 * 状态值到 i18n 键名的映射表
 */
const STATUS_I18N_KEY_MAP: Record<string, string> = {
  pending:   'statusPending',
  running:   'statusRunning',
  completed: 'statusCompleted',
  failed:    'statusFailed',
  skipped:   'statusSkipped',
};

/**
 * 格式化 ISO 时间字符串为 yyyy-MM-dd HH:mm:ss 格式
 * 导出以便测试使用
 */
export function formatDateTime(isoString: string): string {
  const d = new Date(isoString);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/**
 * 计算阶段统计信息
 * 导出以便测试使用
 */
export function computeStageStats(stages: StageRecord[]): {
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

// 状态样式映射函数，导出以便测试使用
export function getStatusStyle(status: string) {
  switch (status as PipelineStageStatus | 'success') {
    // 'success' 作为旧版状态值的 fallthrough 兼容，与 'completed' 共用同一样式
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

interface PipelineStageTimelineProps {
  pipelineRun: PipelineRun | null;
  loading: boolean;
  error: string | null;
}

export default function PipelineStageTimeline({ pipelineRun, loading, error }: PipelineStageTimelineProps) {
  const t = useTranslations('pipeline');
  const [expandedStages, setExpandedStages] = useState<Set<string>>(new Set());

  /**
   * 获取阶段的国际化名称
   * 已知阶段通过 i18n 键获取，未知阶段使用 fallback 逻辑
   */
  const getStageLabel = (name: string): string => {
    const i18nKey = STAGE_I18N_KEY_MAP[name];
    if (i18nKey) {
      return t(i18nKey);
    }
    // 未知阶段 fallback：将下划线替换为空格并首字母大写
    return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  };

  /**
   * 获取状态的国际化标签
   */
  const getStatusLabel = (status: string): string => {
    const i18nKey = STATUS_I18N_KEY_MAP[status];
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

  // 加载状态
  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-500 py-4">
        <Loader2 className="w-4 h-4 animate-spin text-indigo-500" />
        <span>{t('loading')}</span>
      </div>
    );
  }

  // 错误状态
  if (error) {
    return (
      <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
        {error}
      </div>
    );
  }

  // 无数据状态
  if (!pipelineRun) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-400 py-4">
        <Activity className="w-4 h-4" />
        <span>{t('noData')}</span>
      </div>
    );
  }

  const overallStyle = getStatusStyle(pipelineRun.status);
  const stats = computeStageStats(pipelineRun.stages);

  return (
    <div className="space-y-3">
      {/* 顶部总览区域 */}
      <div className={`px-4 py-3 rounded-lg border ${overallStyle.overallBg}`}>
        <div className="flex items-center gap-3">
          {overallStyle.icon}
          <div className="flex-1 min-w-0">
            <span className="font-semibold">{getStatusLabel(pipelineRun.status)}</span>
            {pipelineRun.started_at && (
              <span className="ml-3 text-xs opacity-70">
                {t('overviewStartedAt')}: {formatDateTime(pipelineRun.started_at)}
              </span>
            )}
          </div>
          {pipelineRun.total_latency_ms != null && (
            <span className="text-xs font-mono opacity-80 shrink-0">
              {t('overviewTotalLatency')}: {pipelineRun.total_latency_ms.toFixed(0)} ms
            </span>
          )}
        </div>
        {/* 阶段统计摘要 */}
        {stats.total > 0 && (
          <div className="mt-2 flex items-center gap-3 text-xs opacity-80">
            <span>{t('overviewStageStats', { completed: stats.completed, total: stats.total })}</span>
            {stats.failed > 0 && (
              <span className="text-red-700">{t('overviewFailed', { count: stats.failed })}</span>
            )}
            {stats.skipped > 0 && (
              <span className="text-gray-500">{t('overviewSkipped', { count: stats.skipped })}</span>
            )}
          </div>
        )}
      </div>

      {/* 阶段列表 */}
      {pipelineRun.stages.length === 0 ? (
        <div className="text-sm text-gray-400 px-4 py-3 border border-gray-100 rounded-lg bg-gray-50">
          {t('noStages')}
        </div>
      ) : (
        <div className="divide-y divide-gray-100 border border-gray-200 rounded-lg overflow-hidden bg-white">
          {pipelineRun.stages.map((stage) => {
            const style = getStatusStyle(stage.status);
            const expanded = expandedStages.has(stage.stage_name);
            const hasMetrics = stage.key_metrics && Object.keys(stage.key_metrics).length > 0;
            // skipped 阶段始终有详情可展示（跳过原因）
            const isSkipped = stage.status === 'skipped';
            const isFailed = stage.status === 'failed';
            const hasDetail = !!(stage.error_summary || isSkipped || hasMetrics ||
              (stage.input_summary && Object.keys(stage.input_summary).length > 0) ||
              (stage.output_summary && Object.keys(stage.output_summary).length > 0));

            return (
              <div key={stage.stage_name}>
                <button
                  className="w-full flex items-center gap-3 px-4 py-3 hover:bg-gray-50 text-left transition-colors"
                  onClick={() => hasDetail && toggleStage(stage.stage_name)}
                >
                  {style.icon}
                  <span className="flex-1 font-medium text-gray-900 text-sm">
                    {getStageLabel(stage.stage_name)}
                  </span>
                  <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${style.badge}`}>
                    {getStatusLabel(stage.status)}
                  </span>
                  {stage.latency_ms != null && (
                    <span className="text-xs text-gray-400 font-mono ml-2 shrink-0">
                      {stage.latency_ms.toFixed(0)} ms
                    </span>
                  )}
                  {hasDetail && (
                    expanded
                      ? <ChevronDown className="w-4 h-4 text-gray-400 ml-1 shrink-0" />
                      : <ChevronRight className="w-4 h-4 text-gray-400 ml-1 shrink-0" />
                  )}
                </button>

                {expanded && hasDetail && (
                  <div className="px-4 pb-4 pt-1 bg-gray-50 border-t border-gray-100 space-y-2">
                    {/* failed 阶段：显示错误信息标签 + error_summary */}
                    {isFailed && stage.error_summary && (
                      <div className="px-3 py-2 bg-red-50 border border-red-100 rounded text-xs text-red-700">
                        <span className="font-semibold">{t('detailError')}：</span>{stage.error_summary}
                      </div>
                    )}
                    {/* skipped 阶段：显示跳过原因标签 + error_summary 或默认文案 */}
                    {isSkipped && (
                      <div className="px-3 py-2 bg-gray-100 border border-gray-200 rounded text-xs text-gray-600">
                        <span className="font-semibold">{t('detailSkipReason')}：</span>{stage.error_summary || t('detailSkipReason')}
                      </div>
                    )}
                    {hasMetrics && (
                      <div>
                        <p className="text-xs font-semibold text-gray-500 mb-1">{t('detailKeyMetrics')}</p>
                        <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
                          {Object.entries(stage.key_metrics).map(([k, v]) => (
                            <div key={k} className="flex items-baseline gap-1">
                              <dt className="text-xs text-gray-500 truncate">{k}:</dt>
                              <dd className="text-xs font-mono text-gray-800 truncate">
                                {typeof v === 'number' ? v.toLocaleString() : String(v)}
                              </dd>
                            </div>
                          ))}
                        </dl>
                      </div>
                    )}
                    {stage.input_summary && Object.keys(stage.input_summary).length > 0 && (
                      <div>
                        <p className="text-xs font-semibold text-gray-500 mb-1">{t('detailInput')}</p>
                        <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
                          {Object.entries(stage.input_summary).map(([k, v]) => (
                            <div key={k} className="flex items-baseline gap-1">
                              <dt className="text-xs text-gray-500 truncate">{k}:</dt>
                              <dd className="text-xs font-mono text-gray-800 truncate">{String(v)}</dd>
                            </div>
                          ))}
                        </dl>
                      </div>
                    )}
                    {stage.output_summary && Object.keys(stage.output_summary).length > 0 && (
                      <div>
                        <p className="text-xs font-semibold text-gray-500 mb-1">{t('detailOutput')}</p>
                        <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
                          {Object.entries(stage.output_summary).map(([k, v]) => (
                            <div key={k} className="flex items-baseline gap-1">
                              <dt className="text-xs text-gray-500 truncate">{k}:</dt>
                              <dd className="text-xs font-mono text-gray-800 truncate">{String(v)}</dd>
                            </div>
                          ))}
                        </dl>
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

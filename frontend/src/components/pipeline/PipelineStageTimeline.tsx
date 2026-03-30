'use client';

import { PipelineRun } from '@/lib/api/types';
import StageTimeline from '@/components/shared/StageTimeline';

/**
 * Pipeline 阶段时间线组件（薄包装层）
 *
 * 保持原有 props 接口不变，内部委托给通用 StageTimeline 组件。
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

interface PipelineStageTimelineProps {
  pipelineRun: PipelineRun | null;
  loading: boolean;
  error: string | null;
}

export default function PipelineStageTimeline({ pipelineRun, loading, error }: PipelineStageTimelineProps) {
  return (
    <StageTimeline
      run={pipelineRun}
      loading={loading}
      error={error}
      stageI18nKeyMap={STAGE_I18N_KEY_MAP}
      i18nNamespace="pipeline"
    />
  );
}

// 导出工具函数以保持向后兼容（测试可能依赖这些导出）
export { formatDateTime, computeStageStats, getStatusStyle } from '@/components/shared/StageTimeline';

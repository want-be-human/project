'use client';

import { useTranslations } from 'next-intl';
import type { ScoreResult } from '@/lib/api/types';
import ScoreDial from './ScoreDial';

/** Hero 区域属性（仅消费 analytics 评分数据） */
interface HeroSectionProps {
  postureScore: number;
  scoreResult: ScoreResult | null;
  actionSafetyScore: number;
  actionSafetyResult: ScoreResult | null;
}

/**
 * Dashboard 首屏 Hero 区域
 * 双圆盘"决策驾驶舱"布局：左侧态势评分，右侧行动安全度
 */
export default function HeroSection({
  postureScore,
  scoreResult,
  actionSafetyScore,
  actionSafetyResult,
}: HeroSectionProps) {
  const t = useTranslations('dashboard');

  /* 行动安全 gauge 仅在有有效数据时渲染 */
  const hasSafetyScore = actionSafetyScore >= 0 && actionSafetyResult != null;

  return (
    <div className="relative bg-gray-900/80 border border-gray-700/50 rounded-2xl p-6 backdrop-blur-sm hover:border-cyan-500/40 transition-colors">
      {/* 项目名称 — 居中 */}
      <h1 className="text-2xl font-bold text-white text-center mb-6">
        {t('heroProjectName')}
      </h1>

      {/* 双仪表盘：决策驾驶舱布局 */}
      <div className="flex flex-col md:flex-row items-center justify-center gap-4 md:gap-6">
        {/* 左仪表盘：态势评分 */}
        <ScoreDial
          score={postureScore}
          label={t('heroPostureScore')}
          breakdown={scoreResult?.posture_components ?? []}
          explain={scoreResult?.explain_summary}
          colorStrategy="posture"
          scoreVersion={scoreResult?.score_version}
          riskIndex={scoreResult?.risk_index}
        />

        {/* 中央信息面板：摘要 + 版本 */}
        <div className="flex flex-col items-center justify-center gap-3 max-w-[260px] text-center">
          {scoreResult?.explain_summary && (
            <p className="text-[11px] text-gray-400 leading-relaxed">
              {scoreResult.explain_summary}
            </p>
          )}
          {(scoreResult?.score_version || actionSafetyResult?.score_version) && (
            <div className="flex items-center gap-2 text-[10px] text-gray-600">
              {scoreResult?.score_version && <span>{scoreResult.score_version}</span>}
              {scoreResult?.score_version && actionSafetyResult?.score_version && (
                <span className="w-px h-3 bg-gray-700" />
              )}
              {actionSafetyResult?.score_version && <span>{actionSafetyResult.score_version}</span>}
            </div>
          )}
          {actionSafetyResult?.explain_summary && (
            <p className="text-[11px] text-gray-400 leading-relaxed">
              {actionSafetyResult.explain_summary}
            </p>
          )}
        </div>

        {/* 右仪表盘：行动安全度 */}
        {hasSafetyScore && (
          <ScoreDial
            score={actionSafetyScore}
            label={t('heroActionSafety')}
            breakdown={actionSafetyResult?.posture_components ?? []}
            explain={actionSafetyResult?.explain_summary}
            colorStrategy="safety"
            scoreVersion={actionSafetyResult?.score_version}
            riskIndex={actionSafetyResult?.risk_index}
          />
        )}
      </div>
    </div>
  );
}

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
      <div className="flex flex-col md:flex-row items-center justify-center gap-8 md:gap-16">
        {/* 左仪表盘：态势评分 */}
        <ScoreDial
          score={postureScore}
          label={t('heroPostureScore')}
          breakdown={scoreResult?.posture_components ?? []}
          explain={scoreResult?.explain_summary}
          colorStrategy="posture"
          tooltipSide="left"
          scoreVersion={scoreResult?.score_version}
          riskIndex={scoreResult?.risk_index}
        />

        {/* 右仪表盘：行动安全度 */}
        {hasSafetyScore && (
          <ScoreDial
            score={actionSafetyScore}
            label={t('heroActionSafety')}
            breakdown={actionSafetyResult?.posture_components ?? []}
            explain={actionSafetyResult?.explain_summary}
            colorStrategy="safety"
            tooltipSide="right"
            scoreVersion={actionSafetyResult?.score_version}
            riskIndex={actionSafetyResult?.risk_index}
          />
        )}
      </div>
    </div>
  );
}

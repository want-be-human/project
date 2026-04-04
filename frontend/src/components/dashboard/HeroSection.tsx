'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import type { DashboardOverview, ScoreResult, PostureComponent } from '@/lib/api/types';
import CountUp from './CountUp';

interface HeroSectionProps {
  overview: DashboardOverview;
  postureScore: number;
  scoreResult: ScoreResult | null;
  actionSafetyScore: number;
  actionSafetyResult: ScoreResult | null;
  apiReachable: boolean;
}

/** 根据评分返回对应颜色类名 */
export function scoreColor(score: number): string {
  if (score >= 80) return 'text-green-400';
  if (score >= 50) return 'text-yellow-400';
  return 'text-red-400';
}

/** 根据评分返回环形进度条颜色 */
export function ringStroke(score: number): string {
  if (score >= 80) return '#4ade80';
  if (score >= 50) return '#facc15';
  return '#f87171';
}

/** 行动安全 gauge 使用蓝色系主色调以区分态势评分 */
function safetyRingStroke(score: number): string {
  if (score >= 80) return '#60a5fa';
  if (score >= 50) return '#fbbf24';
  return '#f87171';
}

/** 行动安全 gauge 文字颜色 */
function safetyScoreColor(score: number): string {
  if (score >= 80) return 'text-blue-400';
  if (score >= 50) return 'text-yellow-400';
  return 'text-red-400';
}

/**
 * 获取最后更新时间
 * 优先使用 pcap_last_done_at，其次 alert_last_analysis_at
 */
function getLastUpdated(overview: DashboardOverview): string | null {
  return overview.pcap_last_done_at ?? overview.alert_last_analysis_at ?? null;
}

/** 格式化 ISO 时间为固定格式显示（避免 SSR/客户端 hydration 不一致） */
function formatTime(iso: string | null): string {
  if (!iso) return '--';
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '--';
    const Y = d.getUTCFullYear();
    const M = String(d.getUTCMonth() + 1).padStart(2, '0');
    const D = String(d.getUTCDate()).padStart(2, '0');
    const h = String(d.getUTCHours()).padStart(2, '0');
    const m = String(d.getUTCMinutes()).padStart(2, '0');
    const s = String(d.getUTCSeconds()).padStart(2, '0');
    return `${Y}-${M}-${D} ${h}:${m}:${s}`;
  } catch {
    return '--';
  }
}

/** 态势评分组件中文名映射 */
const POSTURE_CN: Record<string, string> = {
  severity_pressure: '严重性压力',
  open_pressure: '开放告警压力',
  trend_pressure: '趋势压力',
  blast_radius: '爆炸半径',
  execution_risk: '执行风险',
};

/** 行动安全组件中文名映射 */
const ACTION_SAFETY_CN: Record<string, string> = {
  service_disruption_risk: '服务中断风险',
  reachability_drop: '可达性损失',
  impacted_ratio: '影响范围比例',
  confidence_penalty: '置信度惩罚',
  irreversibility_penalty: '不可逆惩罚',
  rollback_complexity: '回退复杂度',
};

/** 趋势方向符号 */
function trendArrow(dir: PostureComponent['trend_direction']): string {
  if (dir === 'worsening') return ' ↑';
  if (dir === 'improving') return ' ↓';
  if (dir === 'stable') return ' →';
  return '';
}

/** 贡献条颜色 */
function barColor(contribution: number): string {
  if (contribution >= 0.15) return 'bg-red-500';
  if (contribution >= 0.08) return 'bg-yellow-500';
  return 'bg-cyan-500';
}

/** 通用 Breakdown Tooltip */
function BreakdownTooltip({
  components,
  cnNames,
  explainSummary,
  riskIndex,
  scoreVersion,
}: {
  components: PostureComponent[];
  cnNames: Record<string, string>;
  explainSummary?: string | null;
  riskIndex?: number | null;
  scoreVersion?: string;
}) {
  return (
    <div className="absolute top-full mt-2 left-1/2 -translate-x-1/2 z-[9999] w-80 bg-gray-900/95 border border-gray-600/60 rounded-xl p-4 shadow-2xl backdrop-blur-md">
      {/* 解释摘要 */}
      {explainSummary && (
        <p className="text-xs text-gray-300 mb-3 leading-relaxed">
          {explainSummary}
        </p>
      )}

      {/* 组件分解 */}
      <div className="space-y-2">
        {components.map((comp) => {
          const pct = Math.round(comp.contribution * 100);
          const cnName = cnNames[comp.name] || comp.name;
          return (
            <div key={comp.name} className={`${!comp.available ? 'opacity-40' : ''}`}>
              <div className="flex items-center justify-between text-xs mb-0.5">
                <span className="text-gray-300">
                  {cnName}
                  <span className="text-gray-500">{trendArrow(comp.trend_direction)}</span>
                </span>
                <span className="text-gray-400 tabular-nums">
                  {comp.available ? `${(comp.normalized_value * 100).toFixed(0)}%` : '--'}
                  <span className="text-gray-600 ml-1">
                    (w:{(comp.effective_weight * 100).toFixed(0)}%)
                  </span>
                </span>
              </div>
              {/* 贡献条 */}
              <div className="h-1.5 bg-gray-700/60 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${barColor(comp.contribution)}`}
                  style={{ width: `${Math.min(100, pct * 3)}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* 底部信息 */}
      <div className="flex items-center justify-between mt-3 pt-2 border-t border-gray-700/50 text-xs text-gray-500">
        <span>
          Risk Index: <span className="text-gray-300 tabular-nums">
            {riskIndex != null ? riskIndex.toFixed(4) : '--'}
          </span>
        </span>
        <span>{scoreVersion || '--'}</span>
      </div>
    </div>
  );
}

/**
 * Hero 区域组件
 * 三栏布局：左侧项目信息 | 中间评分环形图（双 gauge）| 右侧关键上下文
 * 统一 Card_Style_System 面板样式
 */
export default function HeroSection({
  overview,
  postureScore,
  scoreResult,
  actionSafetyScore,
  actionSafetyResult,
  apiReachable,
}: HeroSectionProps) {
  const t = useTranslations('dashboard');
  const [showPostureBreakdown, setShowPostureBreakdown] = useState(false);
  const [showSafetyBreakdown, setShowSafetyBreakdown] = useState(false);

  const score = postureScore;
  const lastUpdated = getLastUpdated(overview);

  // 环形进度条参数（160px 尺寸）
  const radius = 68;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;

  const critical = overview.alert_by_severity?.critical ?? 0;
  const high = overview.alert_by_severity?.high ?? 0;

  // 评分低于 50 视为高风险，启用呼吸发光动效
  const isHighRisk = score < 50;

  // v2 态势评分组件数据
  const postureComponents = scoreResult?.posture_components ?? [];
  const postureRiskIndex = scoreResult?.risk_index;
  const postureExplainSummary = scoreResult?.explain_summary;
  const postureScoreVersion = scoreResult?.score_version;

  // 行动安全评分数据
  const hasSafetyScore = actionSafetyScore >= 0 && actionSafetyResult != null;
  const safetyComponents = actionSafetyResult?.posture_components ?? [];
  const safetyRiskIndex = actionSafetyResult?.risk_index;
  const safetyExplainSummary = actionSafetyResult?.explain_summary;
  const safetyScoreVersion = actionSafetyResult?.score_version;
  const safetyOffset = hasSafetyScore
    ? circumference - (actionSafetyScore / 100) * circumference
    : circumference;
  const isSafetyHighRisk = hasSafetyScore && actionSafetyScore < 50;

  return (
    <div className="relative z-20 bg-gray-900/80 border border-gray-700/50 rounded-2xl p-5 backdrop-blur-sm hover:border-cyan-500/40 transition-colors">
      {/* 项目名称 */}
      <h1 className="text-2xl font-bold text-white mb-4">
        {t('heroProjectName')}
      </h1>

      {/* 三栏布局：左侧项目信息 | 中间评分环形图 | 右侧关键上下文 */}
      <div className="flex flex-col lg:flex-row lg:items-center gap-6">
        {/* 左侧：运行状态 */}
        <div className="flex-1 min-w-0 space-y-3">
          {/* 运行状态 */}
          <div className="bg-gray-800/60 rounded-lg px-3 py-2">
            <span className="text-xs text-gray-400 block">{t('heroRunningStatus')}</span>
            <span className="flex items-center gap-1.5 mt-0.5">
              <span className={`w-2 h-2 rounded-full ${apiReachable ? 'bg-green-400 animate-pulse' : 'bg-gray-500'}`} />
              <span className={`text-sm font-medium ${apiReachable ? 'text-green-400' : 'text-gray-400'}`}>
                {apiReachable ? t('heroStatusOnline') : t('heroStatusOffline')}
              </span>
            </span>
          </div>
        </div>

        {/* 中间：双 gauge 并排 — 态势评分 + 行动安全 */}
        <div className="flex items-start gap-6 shrink-0">
          {/* 态势评分 gauge */}
          <div
            className="flex flex-col items-center gap-2 relative"
            onMouseEnter={() => setShowPostureBreakdown(true)}
            onMouseLeave={() => setShowPostureBreakdown(false)}
          >
            <span className="text-xs text-gray-400">{t('heroPostureScore')}</span>
            <div className="relative w-40 h-40">
              <svg className={`w-full h-full -rotate-90${isHighRisk ? ' animate-breathe-glow-ring' : ''}`} viewBox="0 0 160 160">
                <circle
                  cx="80" cy="80" r={radius}
                  fill="none" stroke="#374151" strokeWidth="8"
                />
                <circle
                  cx="80" cy="80" r={radius}
                  fill="none"
                  stroke={ringStroke(score)}
                  strokeWidth="8"
                  strokeLinecap="round"
                  strokeDasharray={circumference}
                  strokeDashoffset={offset}
                  className="transition-all duration-1000 ease-out"
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className={`text-3xl font-bold ${scoreColor(score)}${isHighRisk ? ' animate-breathe-glow' : ''}`}>
                  <CountUp end={Math.round(score)} />
                </span>
              </div>
            </div>

            {/* Posture Breakdown Tooltip */}
            {showPostureBreakdown && postureComponents.length > 0 && (
              <BreakdownTooltip
                components={postureComponents}
                cnNames={POSTURE_CN}
                explainSummary={postureExplainSummary}
                riskIndex={postureRiskIndex}
                scoreVersion={postureScoreVersion}
              />
            )}
          </div>

          {/* 行动安全 gauge — 仅在有数据时渲染 */}
          {hasSafetyScore && (
            <div
              className="flex flex-col items-center gap-2 relative"
              onMouseEnter={() => setShowSafetyBreakdown(true)}
              onMouseLeave={() => setShowSafetyBreakdown(false)}
            >
              <span className="text-xs text-gray-400">{t('heroActionSafety')}</span>
              <div className="relative w-40 h-40">
                <svg className={`w-full h-full -rotate-90${isSafetyHighRisk ? ' animate-breathe-glow-ring' : ''}`} viewBox="0 0 160 160">
                  <circle
                    cx="80" cy="80" r={radius}
                    fill="none" stroke="#374151" strokeWidth="8"
                  />
                  <circle
                    cx="80" cy="80" r={radius}
                    fill="none"
                    stroke={safetyRingStroke(actionSafetyScore)}
                    strokeWidth="8"
                    strokeLinecap="round"
                    strokeDasharray={circumference}
                    strokeDashoffset={safetyOffset}
                    className="transition-all duration-1000 ease-out"
                  />
                </svg>
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className={`text-3xl font-bold ${safetyScoreColor(actionSafetyScore)}${isSafetyHighRisk ? ' animate-breathe-glow' : ''}`}>
                    <CountUp end={Math.round(actionSafetyScore)} />
                  </span>
                </div>
              </div>

              {/* Safety Breakdown Tooltip */}
              {showSafetyBreakdown && safetyComponents.length > 0 && (
                <BreakdownTooltip
                  components={safetyComponents}
                  cnNames={ACTION_SAFETY_CN}
                  explainSummary={safetyExplainSummary}
                  riskIndex={safetyRiskIndex}
                  scoreVersion={safetyScoreVersion}
                />
              )}
            </div>
          )}
        </div>

        {/* 核心指标摘要 — 放在 gauge 下方 */}
        <div className="flex gap-4 text-xs text-gray-400 lg:hidden">
          <span>PCAP: <span className="text-white">{overview.pcap_total}</span></span>
          <span>Flow: <span className="text-white">{overview.flow_total}</span></span>
          <span>Alert: <span className="text-white">{overview.alert_total}</span></span>
        </div>

        {/* 右侧：关键上下文信息 */}
        <div className="flex-1 min-w-0 space-y-3">
          {/* 严重/高危告警 */}
          <div className="bg-gray-800/60 rounded-lg px-3 py-2">
            <span className="text-xs text-gray-400 block">{t('heroCriticalAlerts')}</span>
            <span className="text-sm font-medium text-red-400 mt-0.5 block">
              {critical} / {t('heroHighAlerts')}: {high}
            </span>
          </div>

          {/* 最后更新时间 */}
          <div className="bg-gray-800/60 rounded-lg px-3 py-2">
            <span className="text-xs text-gray-400 block">{t('heroLastUpdated')}</span>
            <span className="text-sm text-gray-200 mt-0.5 block truncate">
              {formatTime(lastUpdated)}
            </span>
          </div>

          {/* 核心指标摘要 — 桌面端在右侧 */}
          <div className="hidden lg:flex gap-3 text-xs text-gray-400">
            <span>PCAP: <span className="text-white">{overview.pcap_total}</span></span>
            <span>Flow: <span className="text-white">{overview.flow_total}</span></span>
            <span>Alert: <span className="text-white">{overview.alert_total}</span></span>
          </div>
        </div>
      </div>
    </div>
  );
}

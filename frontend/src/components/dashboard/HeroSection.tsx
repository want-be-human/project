'use client';

import { useTranslations } from 'next-intl';
import type { DashboardOverview } from '@/lib/api/types';
import CountUp from './CountUp';

interface HeroSectionProps {
  overview: DashboardOverview;
  postureScore: number;
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

/**
 * Hero 区域组件
 * 三栏布局：左侧项目信息 | 中间态势评分环形图（视觉锚点）| 右侧关键上下文
 * 统一 Card_Style_System 面板样式
 */
export default function HeroSection({ overview, postureScore, apiReachable }: HeroSectionProps) {
  const t = useTranslations('dashboard');

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

  return (
    <div className="bg-gray-900/80 border border-gray-700/50 rounded-2xl p-5 backdrop-blur-sm hover:border-cyan-500/40 transition-colors">
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

        {/* 中间：态势评分环形图（视觉锚点，160×160px） */}
        <div className="flex flex-col items-center gap-2 shrink-0">
          <span className="text-xs text-gray-400">{t('heroPostureScore')}</span>
          <div className="relative w-40 h-40">
            {/* 环形进度条 SVG，高风险时添加呼吸发光效果 */}
            <svg className={`w-full h-full -rotate-90${isHighRisk ? ' animate-breathe-glow-ring' : ''}`} viewBox="0 0 160 160">
              {/* 背景环 */}
              <circle
                cx="80" cy="80" r={radius}
                fill="none" stroke="#374151" strokeWidth="8"
              />
              {/* 进度环 */}
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
            {/* 中心评分数字，高风险时添加呼吸发光文字效果 */}
            <div className="absolute inset-0 flex items-center justify-center">
              <span className={`text-3xl font-bold ${scoreColor(score)}${isHighRisk ? ' animate-breathe-glow' : ''}`}>
                <CountUp end={Math.round(score)} />
              </span>
            </div>
          </div>

          {/* 核心指标摘要 */}
          <div className="flex gap-4 text-xs text-gray-400">
            <span>PCAP: <span className="text-white">{overview.pcap_total}</span></span>
            <span>Flow: <span className="text-white">{overview.flow_total}</span></span>
            <span>Alert: <span className="text-white">{overview.alert_total}</span></span>
          </div>
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
        </div>
      </div>
    </div>
  );
}

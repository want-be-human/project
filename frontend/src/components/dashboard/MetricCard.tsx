'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import CountUp from './CountUp';
import Sparkline from './Sparkline';

/** 变化方向类型 */
type ChangeDirection = 'up' | 'down' | 'flat';

interface MetricCardProps {
  /** 卡片标题 */
  title: string;
  /** 主值 */
  value: number;
  /** 副标题 */
  subtitle?: string;
  /** 迷你趋势线数据 */
  sparkData?: number[];
  /** 变化方向 */
  change?: ChangeDirection;
  /** 悬停提示文本 */
  tooltip?: string;
  /** 小数位数 */
  decimals?: number;
  /** 后缀（如 '%'） */
  suffix?: string;
}

/** 变化指示器：上升绿色箭头、下降红色箭头、持平灰色横线 */
function ChangeIndicator({ direction }: { direction: ChangeDirection }) {
  const t = useTranslations('dashboard');

  if (direction === 'up') {
    return (
      <span className="inline-flex items-center gap-0.5 text-xs text-green-400">
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
          <path d="M6 2L10 7H2L6 2Z" fill="currentColor" />
        </svg>
        {t('changeUp')}
      </span>
    );
  }

  if (direction === 'down') {
    return (
      <span className="inline-flex items-center gap-0.5 text-xs text-red-400">
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
          <path d="M6 10L2 5H10L6 10Z" fill="currentColor" />
        </svg>
        {t('changeDown')}
      </span>
    );
  }

  // 持平
  return (
    <span className="inline-flex items-center gap-0.5 text-xs text-gray-400">
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
        <rect x="2" y="5" width="8" height="2" rx="1" fill="currentColor" />
      </svg>
      {t('changeFlat')}
    </span>
  );
}

/**
 * 单张指标卡片组件
 * 包含主值（CountUp 动画）、Sparkline 趋势线、变化指示器和悬停提示
 */
export default function MetricCard({
  title,
  value,
  subtitle,
  sparkData,
  change,
  tooltip,
  decimals = 0,
  suffix,
}: MetricCardProps) {
  const [hovered, setHovered] = useState(false);

  // 判断是否为高风险状态（下降趋势表示指标恶化）
  const isHighRisk = change === 'down';

  return (
    <div
      className={`relative bg-gray-900/60 border border-gray-700/50 rounded-xl p-4 transition-colors hover:border-cyan-500/40${isHighRisk ? ' animate-breathe-glow-box' : ''}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* 悬停提示 */}
      {tooltip && hovered && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-10 max-w-xs px-3 py-2 text-xs text-gray-200 bg-gray-800 border border-gray-600 rounded-lg shadow-lg whitespace-normal">
          {tooltip}
        </div>
      )}

      {/* 标题行 */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-gray-400 truncate">{title}</span>
        {change && <ChangeIndicator direction={change} />}
      </div>

      {/* 主值 + 后缀，高风险时添加呼吸发光文字效果 */}
      <div className="flex items-end gap-2">
        <span className={`text-2xl font-bold text-white${isHighRisk ? ' animate-breathe-glow' : ''}`}>
          <CountUp end={value} decimals={decimals} />
          {suffix && <span className="text-lg text-gray-300">{suffix}</span>}
        </span>
      </div>

      {/* 副标题 */}
      {subtitle && (
        <p className="mt-1 text-xs text-gray-500">{subtitle}</p>
      )}

      {/* 迷你趋势线 */}
      {sparkData && sparkData.length > 1 && (
        <div className="mt-2">
          <Sparkline data={sparkData} width={120} height={24} />
        </div>
      )}
    </div>
  );
}

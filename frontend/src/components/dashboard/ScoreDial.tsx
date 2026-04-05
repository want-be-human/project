'use client';

import { useState } from 'react';
import type { PostureComponent } from '@/lib/api/types';
import CountUp from './CountUp';

/** ScoreDial 组件属性 */
interface ScoreDialProps {
  /** 评分值 (0-100)，-1 表示无数据 */
  score: number;
  /** 仪表盘标签文本 */
  label: string;
  /** 评分组件分解数据 */
  breakdown: PostureComponent[];
  /** 自然语言解释摘要 */
  explain?: string | null;
  /** SVG 尺寸 (px)，默认 200 */
  size?: number;
  /** 颜色策略：'posture' 绿色系，'safety' 蓝色系 */
  colorStrategy: 'posture' | 'safety';
  /** tooltip 出现方向：左圆盘用 'left'，右圆盘用 'right' */
  tooltipSide: 'left' | 'right';
  /** 评分算法版本号 */
  scoreVersion?: string;
  /** 归一化风险指数 */
  riskIndex?: number | null;
}

// ==================== 颜色策略 ====================

/** 态势评分文字颜色 */
function postureTextColor(score: number): string {
  if (score >= 80) return 'text-green-400';
  if (score >= 50) return 'text-yellow-400';
  return 'text-red-400';
}

/** 态势评分环形颜色 */
function postureRingColor(score: number): string {
  if (score >= 80) return '#4ade80';
  if (score >= 50) return '#facc15';
  return '#f87171';
}

/** 行动安全文字颜色（蓝色系区分） */
function safetyTextColor(score: number): string {
  if (score >= 80) return 'text-blue-400';
  if (score >= 50) return 'text-yellow-400';
  return 'text-red-400';
}

/** 行动安全环形颜色 */
function safetyRingColor(score: number): string {
  if (score >= 80) return '#60a5fa';
  if (score >= 50) return '#fbbf24';
  return '#f87171';
}

/** 根据策略获取颜色函数 */
function getTextColor(strategy: 'posture' | 'safety', score: number): string {
  return strategy === 'posture' ? postureTextColor(score) : safetyTextColor(score);
}

function getRingColor(strategy: 'posture' | 'safety', score: number): string {
  return strategy === 'posture' ? postureRingColor(score) : safetyRingColor(score);
}

// ==================== 组件名称映射 ====================

/** 态势评分组件中文名 */
const POSTURE_CN: Record<string, string> = {
  severity_pressure: '严重性压力',
  open_pressure: '开放告警压力',
  trend_pressure: '趋势压力',
  blast_radius: '爆炸半径',
  execution_risk: '执行风险',
};

/** 行动安全组件中文名 */
const ACTION_SAFETY_CN: Record<string, string> = {
  service_disruption_risk: '服务中断风险',
  reachability_drop: '可达性损失',
  impacted_ratio: '影响范围比例',
  confidence_penalty: '置信度惩罚',
  irreversibility_penalty: '不可逆惩罚',
  rollback_complexity: '回退复杂度',
};

/** 根据策略选择对应名称映射 */
function getCnNames(strategy: 'posture' | 'safety'): Record<string, string> {
  return strategy === 'posture' ? POSTURE_CN : ACTION_SAFETY_CN;
}

// ==================== 辅助函数 ====================

/** 趋势方向箭头符号 */
function trendArrow(dir: PostureComponent['trend_direction']): string {
  if (dir === 'worsening') return ' ↑';
  if (dir === 'improving') return ' ↓';
  if (dir === 'stable') return ' →';
  return '';
}

/** 贡献条颜色：高贡献红色、中等黄色、低贡献青色 */
function barColor(contribution: number): string {
  if (contribution >= 0.15) return 'bg-red-500';
  if (contribution >= 0.08) return 'bg-yellow-500';
  return 'bg-cyan-500';
}

// ==================== Breakdown Tooltip ====================

/** 评分分解详情浮层 */
function BreakdownTooltip({
  components,
  cnNames,
  explainSummary,
  riskIndex,
  scoreVersion,
  side,
}: {
  components: PostureComponent[];
  cnNames: Record<string, string>;
  explainSummary?: string | null;
  riskIndex?: number | null;
  scoreVersion?: string;
  side: 'left' | 'right';
}) {
  /* tooltip 定位：左圆盘→弹出到左方，右圆盘→弹出到右方 */
  const positionClass = side === 'left'
    ? 'right-full mr-4 top-1/2 -translate-y-1/2'
    : 'left-full ml-4 top-1/2 -translate-y-1/2';

  return (
    <div
      className={`absolute z-[9999] w-80 bg-gray-900/95 border border-gray-600/60 rounded-xl p-4 shadow-2xl backdrop-blur-md ${positionClass}`}
    >
      {/* 解释摘要 */}
      {explainSummary && (
        <p className="text-xs text-gray-300 mb-3 leading-relaxed">
          {explainSummary}
        </p>
      )}

      {/* 组件分解列表 */}
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

      {/* 底部：风险指数 + 版本号 */}
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

// ==================== ScoreDial 主组件 ====================

/**
 * 可复用圆盘仪表组件
 * 用于 Dashboard 首屏显示态势评分和行动安全度
 */
export default function ScoreDial({
  score,
  label,
  breakdown,
  explain,
  size = 200,
  colorStrategy,
  tooltipSide,
  scoreVersion,
  riskIndex,
}: ScoreDialProps) {
  const [showBreakdown, setShowBreakdown] = useState(false);

  /* 判断是否有有效数据 */
  const hasData = score >= 0;
  const displayScore = hasData ? Math.min(100, Math.max(0, score)) : 0;

  /* SVG 圆环参数：radius 按 size 比例计算（保持 68/160 的比例） */
  const radius = Math.round(size * 0.425);
  const circumference = 2 * Math.PI * radius;
  const offset = hasData
    ? circumference - (displayScore / 100) * circumference
    : circumference;

  /* 高风险状态：评分 < 50 且有数据时启用呼吸发光 */
  const isHighRisk = hasData && displayScore < 50;

  /* 名称映射 */
  const cnNames = getCnNames(colorStrategy);

  return (
    <div
      className="flex flex-col items-center gap-2 relative"
      onMouseEnter={() => setShowBreakdown(true)}
      onMouseLeave={() => setShowBreakdown(false)}
    >
      {/* 标签 */}
      <span className="text-xs text-gray-400 tracking-wide">{label}</span>

      {/* 圆环 SVG */}
      <div className="relative" style={{ width: size, height: size }}>
        <svg
          className={`w-full h-full -rotate-90${isHighRisk ? ' animate-breathe-glow-ring' : ''}`}
          viewBox={`0 0 ${size} ${size}`}
          aria-label={`${label}: ${hasData ? Math.round(displayScore) : '--'}`}
          role="img"
        >
          {/* 背景环 */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="#374151"
            strokeWidth="10"
          />
          {/* 进度环 */}
          {hasData && (
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={getRingColor(colorStrategy, displayScore)}
              strokeWidth="10"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={offset}
              className="transition-all duration-1000 ease-out"
            />
          )}
        </svg>

        {/* 中心数字 */}
        <div className="absolute inset-0 flex items-center justify-center">
          {hasData ? (
            <span
              className={`text-4xl font-bold ${getTextColor(colorStrategy, displayScore)}${isHighRisk ? ' animate-breathe-glow' : ''}`}
            >
              <CountUp end={Math.round(displayScore)} />
            </span>
          ) : (
            <span className="text-4xl font-bold text-gray-500">--</span>
          )}
        </div>
      </div>

      {/* 分解提示框（hover 时显示，需有分解数据） */}
      {showBreakdown && hasData && breakdown.length > 0 && (
        <BreakdownTooltip
          components={breakdown}
          cnNames={cnNames}
          explainSummary={explain}
          riskIndex={riskIndex}
          scoreVersion={scoreVersion}
          side={tooltipSide}
        />
      )}
    </div>
  );
}

'use client';

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
  /** SVG 尺寸 (px)，默认 280 */
  size?: number;
  /** 颜色策略：'posture' 绿色系，'safety' 蓝色系 */
  colorStrategy: 'posture' | 'safety';
  /** 评分算法版本号 */
  scoreVersion?: string;
  /** 归一化风险指数 */
  riskIndex?: number | null;
}

// ==================== 几何常量 ====================

const CX = 170;
const CY = 170;
const R = 145;
const START_ANGLE = 140;
const END_ANGLE = 400;
const ARC_RANGE = END_ANGLE - START_ANGLE; // 260°

// ==================== 几何工具函数 ====================

function scoreToAngle(v: number): number {
  return START_ANGLE + (v / 100) * ARC_RANGE;
}

function polarXY(angle: number, radius: number): { x: number; y: number } {
  const rad = ((angle - 90) * Math.PI) / 180;
  // 四舍五入到 2 位小数，避免 SSR/CSR 浮点精度差异导致 hydration mismatch
  return {
    x: Math.round((CX + radius * Math.cos(rad)) * 100) / 100,
    y: Math.round((CY + radius * Math.sin(rad)) * 100) / 100,
  };
}

function arcPath(a1: number, a2: number, radius: number): string {
  const p1 = polarXY(a1, radius);
  const p2 = polarXY(a2, radius);
  const largeArc = a2 - a1 > 180 ? 1 : 0;
  return `M ${p1.x} ${p1.y} A ${radius} ${radius} 0 ${largeArc} 1 ${p2.x} ${p2.y}`;
}

// ==================== 颜色策略 ====================

/** 态势评分文字颜色 */
function postureTextColor(score: number): string {
  if (score >= 80) return 'text-green-400';
  if (score >= 50) return 'text-yellow-400';
  return 'text-red-400';
}

/** 行动安全文字颜色 */
function safetyTextColor(score: number): string {
  if (score >= 80) return 'text-blue-400';
  if (score >= 50) return 'text-yellow-400';
  return 'text-red-400';
}

function getTextColor(strategy: 'posture' | 'safety', score: number): string {
  return strategy === 'posture' ? postureTextColor(score) : safetyTextColor(score);
}

/** 获取指针颜色（根据当前分值所在色区） */
function getNeedleColor(strategy: 'posture' | 'safety', score: number): string {
  if (score < 50) return '#f87171';
  if (score < 80) return '#facc15';
  return strategy === 'posture' ? '#4ade80' : '#60a5fa';
}

// ==================== 色区配置 ====================

interface Zone {
  from: number;
  to: number;
  color: string;
}

const POSTURE_ZONES: Zone[] = [
  { from: 0, to: 50, color: '#f87171' },
  { from: 50, to: 80, color: '#facc15' },
  { from: 80, to: 100, color: '#4ade80' },
];

const SAFETY_ZONES: Zone[] = [
  { from: 0, to: 50, color: '#f87171' },
  { from: 50, to: 80, color: '#fbbf24' },
  { from: 80, to: 100, color: '#60a5fa' },
];

function getZones(strategy: 'posture' | 'safety'): Zone[] {
  return strategy === 'posture' ? POSTURE_ZONES : SAFETY_ZONES;
}

// ==================== SVG Defs 组件 ====================

function DialDefs({ prefix }: { prefix: string }) {
  return (
    <defs>
      {/* 金属边框渐变 */}
      <linearGradient id={`${prefix}-metalRing`} x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stopColor="#ffffff" stopOpacity="0.8" />
        <stop offset="20%" stopColor="#888888" stopOpacity="0.5" />
        <stop offset="50%" stopColor="#333333" stopOpacity="0.8" />
        <stop offset="80%" stopColor="#666666" stopOpacity="0.5" />
        <stop offset="100%" stopColor="#aaaaaa" stopOpacity="0.8" />
      </linearGradient>

      {/* 表盘面径向渐变 */}
      <radialGradient id={`${prefix}-dialInner`} cx="50%" cy="50%" r="50%">
        <stop offset="60%" stopColor="#000000" />
        <stop offset="95%" stopColor="#0a0a0a" />
        <stop offset="100%" stopColor="#1a1a1a" />
      </radialGradient>

      {/* 中心帽渐变 */}
      <radialGradient id={`${prefix}-centerCap`} cx="50%" cy="50%" r="50%">
        <stop offset="0%" stopColor="#111" />
        <stop offset="80%" stopColor="#000" />
        <stop offset="100%" stopColor="#222" />
      </radialGradient>

      {/* 红色辉光滤镜 */}
      <filter id={`${prefix}-glowRed`} x="-20%" y="-20%" width="140%" height="140%">
        <feGaussianBlur stdDeviation="4" result="blur" />
        <feComposite in="SourceGraphic" in2="blur" operator="over" />
      </filter>

      {/* 投影滤镜 */}
      <filter id={`${prefix}-dropShadow`} x="-10%" y="-10%" width="120%" height="120%">
        <feDropShadow dx="0" dy="4" stdDeviation="6" floodColor="#000" floodOpacity="0.8" />
      </filter>
    </defs>
  );
}

// ==================== ScoreDial 主组件 ====================

export default function ScoreDial({
  score,
  label,
  size = 280,
  colorStrategy,
}: ScoreDialProps) {
  const hasData = score >= 0;
  const displayScore = hasData ? Math.min(100, Math.max(0, score)) : 0;
  const isHighRisk = hasData && displayScore < 50;
  const prefix = colorStrategy;
  const zones = getZones(colorStrategy);

  // ---- 刻度生成 ----
  const ticks: React.ReactNode[] = [];
  for (let val = 0; val <= 100; val += 5) {
    const isMajor = val % 10 === 0;
    const angle = scoreToAngle(val);
    const isRed = val <= 50;

    const p1 = polarXY(angle, R - 2);
    const p2 = polarXY(angle, R - (isMajor ? 14 : 7));

    ticks.push(
      <line
        key={`tick-${val}`}
        x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y}
        stroke={isRed ? '#ff2a2a' : '#ffffff'}
        strokeWidth={isMajor ? 2.5 : 1.5}
        opacity={isRed ? 1 : isMajor ? 0.9 : 0.4}
        filter={isRed && isMajor ? `url(#${prefix}-glowRed)` : 'none'}
      />,
    );

    // 大刻度数字
    if (isMajor) {
      const pText = polarXY(angle, R - 32);
      ticks.push(
        <text
          key={`text-${val}`}
          x={pText.x} y={pText.y}
          fill={isRed ? '#ff2a2a' : '#ffffff'}
          fontSize="13"
          fontWeight="500"
          fontFamily="sans-serif"
          textAnchor="middle"
          dominantBaseline="middle"
          filter={isRed ? `url(#${prefix}-glowRed)` : 'none'}
          opacity={0.9}
        >
          {val}
        </text>,
      );
    }
  }

  // ---- 色区弧线 ----
  const zoneArcs = zones.map((zone) => (
    <path
      key={`zone-${zone.from}`}
      d={arcPath(scoreToAngle(zone.from), scoreToAngle(zone.to), R - 2)}
      fill="none"
      stroke={zone.color}
      strokeWidth="4"
      opacity={0.7}
      filter={zone.from === 0 ? `url(#${prefix}-glowRed)` : 'none'}
    />
  ));

  // ---- 指针 ----
  const needleAngle = hasData ? scoreToAngle(displayScore) : scoreToAngle(0);
  const needleColor = hasData ? getNeedleColor(colorStrategy, displayScore) : '#333';
  const pTip = polarXY(needleAngle, R - 15);
  const pBase1 = polarXY(needleAngle - 2.5, R - 55);
  const pBase2 = polarXY(needleAngle + 2.5, R - 55);

  return (
    <div className="flex flex-col items-center gap-1">
      {/* 汽车仪表盘 SVG */}
      <div
        className="relative filter drop-shadow-2xl"
        style={{ width: size, height: size }}
      >
        <svg
          width="100%"
          height="100%"
          viewBox="0 0 340 340"
          aria-label={`${label}: ${hasData ? Math.round(displayScore) : '--'}`}
          role="img"
        >
          <DialDefs prefix={prefix} />

          {/* 1. 外圈金属边框 */}
          <circle
            cx={CX} cy={CY} r={R + 12}
            fill="#050505"
            stroke={`url(#${prefix}-metalRing)`}
            strokeWidth="2"
            opacity="0.85"
            filter={`url(#${prefix}-dropShadow)`}
          />
          {/* 2. 内环 */}
          <circle cx={CX} cy={CY} r={R + 10} fill="none" stroke="#000" strokeWidth="4" />

          {/* 3. 表盘面 */}
          <circle cx={CX} cy={CY} r={R} fill={`url(#${prefix}-dialInner)`} />

          {/* 4. 底部轨道弧 */}
          <path
            d={arcPath(START_ANGLE, END_ANGLE, R - 2)}
            fill="none"
            stroke="#333"
            strokeWidth="2"
          />

          {/* 5. 色区弧线 */}
          {zoneArcs}

          {/* 6. 刻度线 + 数字 */}
          {ticks}

          {/* 7. 指针 */}
          <polygon
            points={`${pTip.x},${pTip.y} ${pBase1.x},${pBase1.y} ${pBase2.x},${pBase2.y}`}
            fill={needleColor}
            filter={isHighRisk ? `url(#${prefix}-glowRed)` : 'none'}
            className={isHighRisk ? 'animate-breathe-glow-needle' : ''}
          />

          {/* 8. 中心帽 */}
          <circle cx={CX} cy={CY} r="12" fill={`url(#${prefix}-centerCap)`} />
        </svg>

        {/* 中央 HTML 覆盖层 */}
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <span className="text-xs text-gray-400 tracking-wider mb-1">{label}</span>
          {hasData ? (
            <span
              className={`text-5xl font-light tracking-wider ${getTextColor(colorStrategy, displayScore)}${isHighRisk ? ' animate-breathe-glow' : ''}`}
              style={{ textShadow: '0 0 10px rgba(255,255,255,0.2)' }}
            >
              <CountUp end={Math.round(displayScore)} />
            </span>
          ) : (
            <span className="text-5xl font-light text-gray-500">--</span>
          )}
        </div>
      </div>
    </div>
  );
}

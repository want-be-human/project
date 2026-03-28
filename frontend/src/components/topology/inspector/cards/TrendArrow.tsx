'use client';

import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

/** before→after 趋势指示器 */
interface TrendArrowProps {
  before: number;
  after: number;
  format?: (v: number) => string;
  /** true 表示数值上升为负面（如风险分值） */
  higherIsBad?: boolean;
}

export default function TrendArrow({ before, after, format, higherIsBad = true }: TrendArrowProps) {
  const fmt = format ?? ((v: number) => v.toFixed(2));
  const delta = after - before;
  const isUp = delta > 0.001;
  const isDown = delta < -0.001;

  // 颜色：higherIsBad 时上升为红、下降为绿；反之相反
  const color = isUp
    ? (higherIsBad ? 'text-red-600' : 'text-green-600')
    : isDown
      ? (higherIsBad ? 'text-green-600' : 'text-red-600')
      : 'text-gray-500';

  const Icon = isUp ? TrendingUp : isDown ? TrendingDown : Minus;

  return (
    <div className="flex items-center gap-1.5 text-sm">
      <span className="text-gray-400 line-through text-xs">{fmt(before)}</span>
      <Icon className={`w-3.5 h-3.5 ${color}`} />
      <span className={`font-bold ${color}`}>{fmt(after)}</span>
    </div>
  );
}

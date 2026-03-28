'use client';

import { useTranslations } from 'next-intl';

/** 严重度分布横条 */
interface SeverityBarProps {
  counts: { critical: number; high: number; medium: number; low: number };
}

// 颜色映射
const segments: Array<{ key: keyof SeverityBarProps['counts']; color: string; bg: string }> = [
  { key: 'critical', color: 'bg-red-600',    bg: 'bg-red-100 text-red-700' },
  { key: 'high',     color: 'bg-orange-500', bg: 'bg-orange-100 text-orange-700' },
  { key: 'medium',   color: 'bg-yellow-400', bg: 'bg-yellow-100 text-yellow-700' },
  { key: 'low',      color: 'bg-green-400',  bg: 'bg-green-100 text-green-700' },
];

export default function SeverityBar({ counts }: SeverityBarProps) {
  const t = useTranslations('topology');
  const total = counts.critical + counts.high + counts.medium + counts.low;
  if (total === 0) return <div className="text-xs text-gray-400 italic">{t('inspector_noAlerts')}</div>;

  // 严重度标签映射
  const labelMap: Record<string, string> = {
    critical: t('inspector_critical'),
    high: t('inspector_high'),
    medium: t('inspector_medium'),
    low: t('inspector_low'),
  };

  return (
    <div className="space-y-1.5">
      {/* 堆叠条 */}
      <div className="flex h-2 rounded-full overflow-hidden bg-gray-100">
        {segments.map(({ key, color }) => {
          const pct = (counts[key] / total) * 100;
          if (pct === 0) return null;
          return <div key={key} className={`${color}`} style={{ width: `${pct}%` }} />;
        })}
      </div>
      {/* 数字标注 */}
      <div className="flex gap-1.5 flex-wrap">
        {segments.map(({ key, bg }) => {
          if (counts[key] === 0) return null;
          return (
            <span key={key} className={`px-1.5 py-0.5 text-[10px] font-medium rounded ${bg}`}>
              {labelMap[key]} {counts[key]}
            </span>
          );
        })}
      </div>
    </div>
  );
}

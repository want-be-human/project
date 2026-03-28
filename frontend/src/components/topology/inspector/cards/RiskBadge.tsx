'use client';

import { useTranslations } from 'next-intl';

/** 风险等级标签（高/中/低） */
export default function RiskBadge({ risk }: { risk: number }) {
  const t = useTranslations('topology');
  const color =
    risk > 0.7 ? 'bg-red-100 text-red-700' :
    risk > 0.3 ? 'bg-yellow-100 text-yellow-700' :
    'bg-green-100 text-green-700';
  const label = risk > 0.7 ? t('riskHigh') : risk > 0.3 ? t('riskMedium') : t('riskLow');
  return (
    <span className={`px-1.5 py-0.5 text-xs font-medium rounded ${color}`}>
      {label}
    </span>
  );
}

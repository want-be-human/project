'use client';

import { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { useTranslations } from 'next-intl';
import type { DashboardDistributions } from '@/lib/api/types';

interface AlertDistributionChartProps {
  distributions: DashboardDistributions;
}

/** 告警类型 → 颜色映射 */
const TYPE_COLORS: Record<string, string> = {
  scan: '#3b82f6',       // 蓝
  bruteforce: '#a855f7', // 紫
  dos: '#ef4444',        // 红
  anomaly: '#eab308',    // 黄
  exfil: '#f97316',      // 橙
  unknown: '#6b7280',    // 灰
};

/** 告警类型 → i18n 键映射 */
const TYPE_I18N_KEYS: Record<string, string> = {
  scan: 'alertTypeScan',
  bruteforce: 'alertTypeBruteforce',
  dos: 'alertTypeDos',
  anomaly: 'alertTypeAnomaly',
  exfil: 'alertTypeExfil',
  unknown: 'alertTypeUnknown',
};

/**
 * 告警类型分布环形饼图
 * 使用 ECharts 渲染，深色主题
 */
export default function AlertDistributionChart({ distributions }: AlertDistributionChartProps) {
  const t = useTranslations('dashboard');

  // 构建饼图数据，翻译类型名称并映射颜色
  const { data, colors } = useMemo(() => {
    const d = distributions.items.map((item) => ({
      name: t(TYPE_I18N_KEYS[item.type] ?? 'alertTypeUnknown'),
      value: item.count,
    }));
    const c = distributions.items.map(
      (item) => TYPE_COLORS[item.type] ?? TYPE_COLORS.unknown,
    );
    return { data: d, colors: c };
  }, [distributions.items, t]);

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item' as const,
      backgroundColor: '#1f2937',
      borderColor: '#374151',
      textStyle: { color: '#e5e7eb', fontSize: 12 },
    },
    legend: {
      orient: 'vertical' as const,
      right: 8,
      top: 'center' as const,
      textStyle: { color: '#9ca3af', fontSize: 11 },
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
    },
    color: colors,
    series: [
      {
        type: 'pie' as const,
        radius: ['45%', '70%'],
        center: ['35%', '50%'],
        avoidLabelOverlap: false,
        itemStyle: { borderColor: '#111827', borderWidth: 2 },
        label: { show: false },
        emphasis: {
          label: { show: true, color: '#e5e7eb', fontSize: 13, fontWeight: 'bold' as const },
        },
        data,
      },
    ],
  };

  return (
    <div className="bg-gray-900/80 border border-gray-700/50 rounded-xl p-4 backdrop-blur-sm">
      {/* 标题 */}
      <h3 className="text-sm font-medium text-gray-200 mb-3">
        {t('chartAlertDistributionTitle')}
      </h3>

      {/* ECharts 环形饼图 */}
      <ReactECharts
        option={option}
        style={{ height: 260 }}
        opts={{ renderer: 'canvas' }}
        notMerge
      />
    </div>
  );
}

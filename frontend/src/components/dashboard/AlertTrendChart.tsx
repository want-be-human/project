'use client';

import { useState, useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { useTranslations } from 'next-intl';
import type { DashboardTrends } from '@/lib/api/types';
import { CHART_TOOLTIP_STYLE } from './chartStyles';
import DashboardCard from './DashboardCard';
import EmptyState from './EmptyState';

interface AlertTrendChartProps {
  trends: DashboardTrends;
}

/**
 * 告警趋势堆叠面积图
 * 使用 ECharts 渲染，支持 24h/7d 时间范围切换
 * 深色主题配色；无数据时保持完整卡片框架，内部显示空状态占位
 */
export default function AlertTrendChart({ trends }: AlertTrendChartProps) {
  const t = useTranslations('dashboard');
  const [range, setRange] = useState<'24h' | '7d'>('7d');

  // 空数据判断：无数据或所有天的告警总数为 0
  const isEmpty =
    trends.days.length === 0 ||
    trends.days.every((d) => d.low + d.medium + d.high + d.critical === 0);

  // 根据时间范围过滤数据：24h 只取最后一天，7d 取全部
  const days = useMemo(() => {
    if (range === '24h' && trends.days.length > 0) {
      return trends.days.slice(-1);
    }
    return trends.days;
  }, [range, trends.days]);

  // 构建堆叠面积图系列的通用配置
  const makeSeries = (name: string, data: number[], color: string) => ({
    name,
    type: 'line' as const,
    stack: 'alerts',
    areaStyle: { opacity: 0.3 },
    emphasis: { focus: 'series' as const },
    symbol: 'circle',
    symbolSize: 4,
    lineStyle: { width: 2 },
    itemStyle: { color },
    data,
  });

  // 图表配置项（仅在有数据时使用，空数据时 days 为空数组，计算无副作用）
  const option = useMemo(() => {
    if (isEmpty) return null;
    const dates = days.map((d) => d.date);
    const lowData = days.map((d) => d.low);
    const mediumData = days.map((d) => d.medium);
    const highData = days.map((d) => d.high);
    const criticalData = days.map((d) => d.critical);
    return {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis' as const,
        axisPointer: { type: 'cross' as const, label: { backgroundColor: '#374151' } },
        ...CHART_TOOLTIP_STYLE,
        formatter: (params: any) => {
          if (!Array.isArray(params) || params.length === 0) return '';
          const date = params[0].axisValue;
          let total = 0;
          const lines = params.map((p: any) => {
            total += p.value ?? 0;
            return `${p.marker} ${p.seriesName}: <b>${p.value}</b>`;
          });
          return `<b>${date}</b><br/>${lines.join('<br/>')}<br/>─────<br/>${t('metricAlertTotal')}: <b>${total}</b>`;
        },
      },
      legend: {
        data: [
          t('severityLow'),
          t('severityMedium'),
          t('severityHigh'),
          t('severityCritical'),
        ],
        textStyle: { color: '#9ca3af', fontSize: 11 },
        top: 0,
        right: 0,
      },
      grid: {
        left: 40,
        right: 16,
        top: 36,
        bottom: 24,
        containLabel: false,
      },
      xAxis: {
        type: 'category' as const,
        boundaryGap: false,
        data: dates,
        axisLine: { lineStyle: { color: '#374151' } },
        axisLabel: { color: '#9ca3af', fontSize: 11 },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value' as const,
        minInterval: 1,
        splitLine: { lineStyle: { color: '#374151', type: 'dashed' as const } },
        axisLine: { show: false },
        axisLabel: { color: '#9ca3af', fontSize: 11 },
      },
      series: [
        makeSeries(t('severityLow'), lowData, '#3b82f6'),
        makeSeries(t('severityMedium'), mediumData, '#eab308'),
        makeSeries(t('severityHigh'), highData, '#f97316'),
        makeSeries(t('severityCritical'), criticalData, '#ef4444'),
      ],
    };
  }, [isEmpty, days, t]);

  // 时间范围切换按钮（始终显示在标题栏右侧）
  const timeRangeButtons = (
    <div className="flex gap-1">
      {(['24h', '7d'] as const).map((r) => (
        <button
          key={r}
          onClick={() => setRange(r)}
          className={`px-2.5 py-0.5 text-xs rounded transition-colors ${
            range === r
              ? 'bg-cyan-600 text-white'
              : 'bg-gray-800 text-gray-400 hover:text-gray-200'
          }`}
        >
          {t(r === '24h' ? 'chartTimeRange24h' : 'chartTimeRange7d')}
        </button>
      ))}
    </div>
  );

  return (
    <DashboardCard title={t('chartAlertTrendTitle')} headerRight={timeRangeButtons}>
      {isEmpty ? (
        <EmptyState message={t('emptyAlertTrend')} />
      ) : (
        <div className="flex-1 min-h-0">
          <ReactECharts
            option={option!}
            style={{ height: '100%' }}
            opts={{ renderer: 'canvas' }}
            notMerge
          />
        </div>
      )}
    </DashboardCard>
  );
}

'use client';

import { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { useTranslations } from 'next-intl';
import type { PipelineSnapshot } from '@/lib/api/types';
import { CHART_TOOLTIP_STYLE } from './chartStyles';

interface PipelineStageChartProps {
  pipeline: PipelineSnapshot | null;
}

/** 阶段状态 → 颜色映射 */
const STATUS_COLORS: Record<string, string> = {
  success: '#22c55e', // 绿色
  failed: '#ef4444',  // 红色
  running: '#3b82f6', // 蓝色
  pending: '#6b7280', // 灰色
  skipped: '#6b7280', // 灰色
};

/**
 * 流水线阶段进度观察图
 * 使用 ECharts 水平条形图展示各阶段耗时和状态
 */
export default function PipelineStageChart({ pipeline }: PipelineStageChartProps) {
  const t = useTranslations('dashboard');

  // 从 pipeline.stages 提取阶段数据
  const { names, latencies, colors } = useMemo(() => {
    if (!pipeline?.stages?.length) {
      return { names: [], latencies: [], colors: [] };
    }
    // 反转顺序使第一个阶段显示在顶部
    const stages = [...pipeline.stages].reverse();
    return {
      names: stages.map((s) => s.stage_name ?? ''),
      latencies: stages.map((s) => s.latency_ms ?? 0),
      colors: stages.map((s) => STATUS_COLORS[s.status] ?? STATUS_COLORS.pending),
    };
  }, [pipeline]);

  // 无数据时显示提示
  if (!pipeline?.stages?.length) {
    return (
      <div className="bg-gray-900/80 border border-gray-700/50 hover:border-cyan-500/40 transition-colors rounded-2xl p-4 backdrop-blur-sm h-full flex flex-col">
        <h3 className="text-sm font-semibold text-gray-200 mb-3">
          {t('chartPipelineStageTitle')}
        </h3>
        <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
          {t('noData')}
        </div>
      </div>
    );
  }

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis' as const,
      axisPointer: { type: 'shadow' as const },
      ...CHART_TOOLTIP_STYLE,
      formatter: (params: any) => {
        const p = Array.isArray(params) ? params[0] : params;
        // 从反转后的索引还原原始阶段信息
        const idx = names.length - 1 - p.dataIndex;
        const stage = [...pipeline.stages][idx];
        const status = stage?.status ?? '';
        const ms = p.value ?? 0;
        return `<b>${p.name}</b><br/>${status} · ${ms} ms`;
      },
    },
    grid: {
      left: 8,
      right: 40,
      top: 8,
      bottom: 8,
      containLabel: true,
    },
    xAxis: {
      type: 'value' as const,
      axisLabel: {
        color: '#9ca3af',
        fontSize: 11,
        formatter: (v: number) => `${v} ms`,
      },
      splitLine: { lineStyle: { color: '#374151', type: 'dashed' as const } },
      axisLine: { show: false },
    },
    yAxis: {
      type: 'category' as const,
      data: names,
      axisLine: { lineStyle: { color: '#374151' } },
      axisLabel: { color: '#9ca3af', fontSize: 11 },
      axisTick: { show: false },
    },
    series: [
      {
        type: 'bar' as const,
        data: latencies.map((val, i) => ({
          value: val,
          itemStyle: { color: colors[i] },
        })),
        barMaxWidth: 20,
        label: {
          show: true,
          position: 'right' as const,
          color: '#9ca3af',
          fontSize: 11,
          formatter: (p: any) => `${p.value} ms`,
        },
      },
    ],
  };

  return (
    <div className="bg-gray-900/80 border border-gray-700/50 hover:border-cyan-500/40 transition-colors rounded-2xl p-4 backdrop-blur-sm h-full flex flex-col">
      <h3 className="text-sm font-semibold text-gray-200 mb-3">
        {t('chartPipelineStageTitle')}
      </h3>
      <div className="flex-1 min-h-0">
        <ReactECharts
          option={option}
          style={{ height: '100%' }}
          opts={{ renderer: 'canvas' }}
          notMerge
        />
      </div>
    </div>
  );
}

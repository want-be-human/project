'use client';

import type { DashboardTrends, DashboardDistributions, PipelineSnapshot } from '@/lib/api/types';
import AlertTrendChart from './AlertTrendChart';
import AlertDistributionChart from './AlertDistributionChart';
import PipelineStageChart from './PipelineStageChart';

interface TrendChartsProps {
  /** 告警趋势数据 */
  trends: DashboardTrends;
  /** 告警类型分布数据 */
  distributions: DashboardDistributions;
  /** 最后一次流水线运行快照 */
  pipeline: PipelineSnapshot | null;
}

/**
 * 图表区域容器组件
 * 组合 AlertTrendChart、AlertDistributionChart、PipelineStageChart
 * 布局：左侧告警趋势图占较大区域，右侧分布图和流水线图
 */
export default function TrendCharts({ trends, distributions, pipeline }: TrendChartsProps) {
  return (
    <div className="px-6 py-4">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 告警趋势堆叠面积图 — 占左侧两列 */}
        <div className="lg:col-span-2">
          <AlertTrendChart trends={trends} />
        </div>

        {/* 右侧：分布图 + 流水线阶段图 */}
        <div className="flex flex-col gap-6">
          <AlertDistributionChart distributions={distributions} />
          <PipelineStageChart pipeline={pipeline} />
        </div>
      </div>
    </div>
  );
}

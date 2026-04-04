import { getTranslations } from 'next-intl/server';
import { api } from '@/lib/api';
import type { DashboardSummary, AnalyticsOverview } from '@/lib/api/types';
import HeroSection from '@/components/dashboard/HeroSection';
import MetricCards from '@/components/dashboard/MetricCards';
import TrendCharts from '@/components/dashboard/TrendCharts';
import ClientDynamicWidgets from '@/components/dashboard/ClientDynamicWidgets';

/**
 * 安全态势总览首页（Server Component）
 * 通过 API 获取仪表盘聚合数据，传递给各子组件渲染
 */
export default async function DashboardPage() {
  const t = await getTranslations('dashboard');

  let data: DashboardSummary | null = null;
  let analyticsOverview: AnalyticsOverview | null = null;
  let error: string | null = null;
  let apiReachable = false;

  try {
    [data, analyticsOverview] = await Promise.all([
      api.getDashboardSummary(),
      api.getAnalyticsOverview(),
    ]);
    apiReachable = true;
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  // API 调用失败时展示错误提示
  if (!data) {
    return (
      <div className="relative min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="bg-gray-900/80 border border-red-700/50 rounded-2xl p-8 max-w-md text-center">
          <h2 className="text-xl font-bold text-red-400 mb-3">
            {t('error')}
          </h2>
          <p className="text-gray-400 text-sm">
            {error || t('noData')}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative min-h-screen bg-gray-950">
      {/* 微弱网格线背景，增强深色主题层次感 */}
      <div className="grid-background" aria-hidden="true" />
      {/* 主内容区域：z-10 确保内容层级高于粒子背景 */}
      <div className="relative z-10 flex flex-col gap-6 px-6 pt-6 pb-8">
        {/* A 层：Hero 区域 — 项目状态与态势评分 */}
        <HeroSection
          overview={data.overview}
          postureScore={analyticsOverview?.posture_score?.value ?? 0}
          scoreResult={analyticsOverview?.posture_score ?? null}
          apiReachable={apiReachable}
        />
        {/* B 层：六张核心指标卡片 */}
        <MetricCards overview={data.overview} sparklines={data.metric_sparklines} />
        {/* C 层：图表区域 — 告警趋势、分布、流水线阶段 */}
        <TrendCharts
          trends={data.trends}
          distributions={data.distributions}
          pipeline={data.overview.pipeline_last_run}
        />
        {/* D 层：3D 迷你拓扑 + 活动流（客户端动态加载） */}
        <ClientDynamicWidgets
          topologySnapshot={data.topology_snapshot}
          recentActivity={data.recent_activity}
        />
        {/* E 层：底部留白由 pb-8 提供 */}
      </div>
    </div>
  );
}

'use client';

import { useTranslations } from 'next-intl';
import type { DashboardOverview } from '@/lib/api/types';
import MetricCard from './MetricCard';

interface MetricCardsProps {
  overview: DashboardOverview;
}

/**
 * 计算趋势变化方向
 * 比较数组最后两个元素，返回 'up' | 'down' | 'flat'
 * 数据点不足 2 个时返回 'flat'
 *
 * 导出以便属性测试使用
 */
export function calcChange(trend: number[]): 'up' | 'down' | 'flat' {
  if (trend.length < 2) return 'flat';
  const last = trend[trend.length - 1];
  const prev = trend[trend.length - 2];
  if (last > prev) return 'up';
  if (last < prev) return 'down';
  return 'flat';
}

/**
 * 六张指标卡片容器组件
 * 展示 PCAP、Flow、Alert、开放告警、场景通过率、Dry-Run 六类核心指标
 */
export default function MetricCards({ overview }: MetricCardsProps) {
  const t = useTranslations('dashboard');

  /** 格式化严重程度分布为副标题文本 */
  const severitySubtitle = () => {
    const s = overview.alert_by_severity;
    if (!s || Object.keys(s).length === 0) return t('metricAlertSeverity');
    const parts: string[] = [];
    if (s.critical) parts.push(`${t('severityCritical')}:${s.critical}`);
    if (s.high) parts.push(`${t('severityHigh')}:${s.high}`);
    if (s.medium) parts.push(`${t('severityMedium')}:${s.medium}`);
    if (s.low) parts.push(`${t('severityLow')}:${s.low}`);
    return parts.length > 0 ? parts.join(' / ') : t('metricAlertSeverity');
  };

  /** 格式化平均中断风险为副标题文本 */
  const dryrunSubtitle = () => {
    const risk = overview.dryrun_avg_disruption_risk;
    return `${t('metricDryrunAvgRisk')}: ${(risk * 100).toFixed(1)}%`;
  };

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 px-6 py-4">
      {/* PCAP 文件 */}
      <MetricCard
        title={t('metricPcapTitle')}
        value={overview.pcap_total}
        subtitle={`${t('metricPcap24h')}: ${overview.pcap_24h_count}`}
        sparkData={overview.pcap_trend}
        change={calcChange(overview.pcap_trend)}
        tooltip={t('metricPcapTooltip')}
      />

      {/* 流量记录 */}
      <MetricCard
        title={t('metricFlowTitle')}
        value={overview.flow_total}
        subtitle={`${t('metricFlow24h')}: ${overview.flow_24h_count}`}
        sparkData={overview.flow_trend}
        change={calcChange(overview.flow_trend)}
        tooltip={t('metricFlowTooltip')}
      />

      {/* 安全告警 */}
      <MetricCard
        title={t('metricAlertTitle')}
        value={overview.alert_total}
        subtitle={severitySubtitle()}
        tooltip={t('metricAlertTooltip')}
      />

      {/* 开放告警 */}
      <MetricCard
        title={t('metricOpenAlertTitle')}
        value={overview.alert_open_count}
        sparkData={overview.alert_open_trend}
        change={calcChange(overview.alert_open_trend)}
        tooltip={t('metricOpenAlertTooltip')}
      />

      {/* 场景通过率 */}
      <MetricCard
        title={t('metricScenarioTitle')}
        value={overview.scenario_pass_rate * 100}
        suffix="%"
        decimals={1}
        tooltip={t('metricScenarioTooltip')}
      />

      {/* Dry-Run 推演 */}
      <MetricCard
        title={t('metricDryrunTitle')}
        value={overview.dryrun_total}
        subtitle={dryrunSubtitle()}
        tooltip={t('metricDryrunTooltip')}
      />
    </div>
  );
}

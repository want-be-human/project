'use client';

import { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { BarChart3, Layout, AlertTriangle, Shield, Layers } from 'lucide-react';
import type { GraphNode, GraphEdge, GraphResponse, DryRunResult } from '@/lib/api/types';
import type { LayoutMode } from '@/components/topology/layouts/types';
import type { DryRunViewMode } from '@/app/(main)/topology/page';
import type { ViewLevel } from '@/components/topology/optimization/types';
import InfoCard from './cards/InfoCard';
import StatGrid from './cards/StatGrid';
import SeverityBar from './cards/SeverityBar';
import MiniNodeList from './cards/MiniNodeList';
import DetailRow from './cards/DetailRow';

interface GlobalPanelProps {
  graph: GraphResponse;
  currentTime: number;
  layoutMode: LayoutMode;
  viewMode?: DryRunViewMode;
  dryRunResult?: DryRunResult | null;
  removedNodeIds?: Set<string>;
  removedEdgeIds?: Set<string>;
  affectedNodeIds?: Set<string>;
  affectedEdgeIds?: Set<string>;
  alertSeverityMap?: Record<string, 'low' | 'medium' | 'high' | 'critical'>;
  onSelectNode?: (node: GraphNode) => void;
  onSelectEdge?: (edge: GraphEdge) => void;
  /** 当前视图层级（来自优化层） */
  viewLevel?: ViewLevel;
  /** 当前簇数量 */
  clusterCount?: number;
  /** 展开的簇数量 */
  expandedClusterCount?: number;
}

export default function GlobalPanel({
  graph, currentTime, layoutMode, viewMode, dryRunResult,
  removedNodeIds, removedEdgeIds, affectedNodeIds, affectedEdgeIds,
  alertSeverityMap, onSelectNode, onSelectEdge,
  viewLevel, clusterCount, expandedClusterCount,
}: GlobalPanelProps) {
  const t = useTranslations('topology');

  // 当前时间滑块下的活跃边数
  const activeEdgeCount = useMemo(() => {
    if (!currentTime) return graph.edges.length;
    return graph.edges.filter(e =>
      (e.activeIntervals ?? []).some(([s, end]) => {
        const st = new Date(s).getTime();
        const et = new Date(end).getTime();
        return currentTime >= st && currentTime <= et;
      })
    ).length;
  }, [graph.edges, currentTime]);

  // Top 5 风险节点
  const topRiskNodes = useMemo(() =>
    [...graph.nodes].sort((a, b) => b.risk - a.risk).slice(0, 5),
    [graph.nodes]
  );

  // Top 5 权重边
  const topWeightEdges = useMemo(() =>
    [...graph.edges].sort((a, b) => b.weight - a.weight).slice(0, 5),
    [graph.edges]
  );

  // 全图告警严重度分布
  const severityCounts = useMemo(() => {
    const counts = { critical: 0, high: 0, medium: 0, low: 0 };
    if (!alertSeverityMap) return counts;
    const seen = new Set<string>();
    for (const e of graph.edges) {
      for (const aid of e.alert_ids ?? []) {
        if (seen.has(aid)) continue;
        seen.add(aid);
        const sev = alertSeverityMap[aid];
        if (sev && sev in counts) counts[sev as keyof typeof counts]++;
      }
    }
    return counts;
  }, [graph.edges, alertSeverityMap]);

  const totalAlerts = severityCounts.critical + severityCounts.high + severityCounts.medium + severityCounts.low;

  // 布局模式描述映射
  const layoutDescMap: Record<string, string> = {
    circle: t('inspector_layoutCircleDesc'),
    dag: t('inspector_layoutDagDesc'),
    'clustered-subnet': t('inspector_layoutClusterDesc'),
  };

  // 布局模式名称映射
  const layoutNameMap: Record<string, string> = {
    circle: t('layoutCircle'),
    dag: t('layoutDag'),
    'clustered-subnet': t('layoutCluster'),
  };

  return (
    <div className="space-y-3">
      {/* 头部 */}
      <div className="flex items-center gap-2">
        <BarChart3 className="w-5 h-5 text-indigo-600" />
        <h3 className="font-bold text-gray-900">{t('inspector_globalOverview')}</h3>
      </div>

      {/* 图统计 */}
      <InfoCard title={t('inspector_graphStats')} icon={<BarChart3 className="w-3.5 h-3.5" />}>
        <StatGrid
          columns={3}
          items={[
            { label: t('nodes'), value: graph.nodes.length, color: 'text-blue-700' },
            { label: t('edges'), value: graph.edges.length, color: 'text-purple-700' },
            { label: t('inspector_activeEdges'), value: activeEdgeCount, color: 'text-green-700' },
          ]}
        />
      </InfoCard>

      {/* 布局信息 */}
      <InfoCard title={t('inspector_layoutInfo')} icon={<Layout className="w-3.5 h-3.5" />}>
        <div className="flex items-center gap-2 text-sm">
          <span className="px-2 py-0.5 text-xs font-medium rounded bg-indigo-50 text-indigo-700 border border-indigo-100">
            {layoutNameMap[layoutMode] ?? layoutMode}
          </span>
        </div>
        <div className="text-xs text-gray-500 mt-1">
          {layoutDescMap[layoutMode] ?? ''}
        </div>
        {viewMode && dryRunResult && (
          <div className="flex items-center gap-2 mt-2 text-sm">
            <span className="text-gray-500">{t('inspector_viewMode')}</span>
            <span className="px-2 py-0.5 text-xs font-medium rounded bg-amber-50 text-amber-700 border border-amber-100">
              {t(`viewMode_${viewMode}`)}
            </span>
          </div>
        )}
      </InfoCard>

      {/* 大图优化信息 */}
      {viewLevel && (
        <InfoCard title={t('inspector_optimizationInfo')} icon={<Layers className="w-3.5 h-3.5" />}>
          <div className="space-y-1">
            <DetailRow
              label={t('inspector_viewLevel')}
              value={t(`viewLevel_${viewLevel}`)}
            />
            {clusterCount !== undefined && clusterCount > 0 && (
              <>
                <DetailRow
                  label={t('inspector_clusterCount')}
                  value={String(clusterCount)}
                />
                <DetailRow
                  label={t('inspector_expandedClusters')}
                  value={String(expandedClusterCount ?? 0)}
                />
              </>
            )}
          </div>
        </InfoCard>
      )}

      {/* Top 风险节点 */}
      <InfoCard title={t('inspector_topRiskNodes')}>
        <MiniNodeList
          items={topRiskNodes.map(n => ({ id: n.id, label: n.label, value: n.risk }))}
          onSelect={(id) => {
            const node = graph.nodes.find(n => n.id === id);
            if (node) onSelectNode?.(node);
          }}
        />
      </InfoCard>

      {/* Top 风险边 */}
      <InfoCard title={t('inspector_topRiskEdges')}>
        <MiniNodeList
          items={topWeightEdges.map(e => ({
            id: e.id,
            label: `${e.source.replace('ip:', '')} → ${e.target.replace('ip:', '')}`,
            value: e.risk ?? e.weight,
          }))}
          onSelect={(id) => {
            const edge = graph.edges.find(e => e.id === id);
            if (edge) onSelectEdge?.(edge);
          }}
          formatValue={v => String(Math.round(v))}
        />
      </InfoCard>

      {/* 告警分布 */}
      <InfoCard title={t('inspector_alertDistribution')} icon={<AlertTriangle className="w-3.5 h-3.5" />}>
        <div className="flex items-center gap-2 mb-1">
          <span className="text-sm text-gray-700">{t('inspector_totalAlerts')}</span>
          <span className="px-1.5 py-0.5 text-xs font-bold rounded bg-red-100 text-red-700">
            {totalAlerts}
          </span>
        </div>
        <SeverityBar counts={severityCounts} />
      </InfoCard>

      {/* Dry-Run 摘要 */}
      {dryRunResult && (
        <InfoCard title={t('inspector_dryRunSummary')} icon={<Shield className="w-3.5 h-3.5" />}>
          <StatGrid
            columns={2}
            items={[
              { label: t('inspector_removedNodes'), value: removedNodeIds?.size ?? 0, color: 'text-red-600' },
              { label: t('inspector_removedEdges'), value: removedEdgeIds?.size ?? 0, color: 'text-red-600' },
              { label: t('inspector_affectedNodes'), value: affectedNodeIds?.size ?? 0, color: 'text-amber-600' },
              { label: t('inspector_affectedEdges'), value: affectedEdgeIds?.size ?? 0, color: 'text-amber-600' },
            ]}
          />
          <div className="mt-2 space-y-1">
            <DetailRow
              label={t('disruptionRisk')}
              value={`${((dryRunResult.impact.service_disruption_risk || 0) * 100).toFixed(0)}%`}
            />
            <DetailRow
              label={t('reachabilityDrop')}
              value={`${((dryRunResult.impact.reachability_drop || 0) * 100).toFixed(0)}%`}
            />
            {dryRunResult.impact.confidence !== undefined && (
              <DetailRow
                label={t('inspector_confidence')}
                value={`${(dryRunResult.impact.confidence * 100).toFixed(0)}%`}
              />
            )}
          </div>
          {/* 警告（可折叠） */}
          {(dryRunResult.impact.warnings ?? []).length > 0 && (
            <div className="mt-2 space-y-1">
              <div className="text-[10px] text-gray-500 uppercase tracking-wider">{t('dryRunWarnings')}</div>
              {dryRunResult.impact.warnings!.map((w, i) => (
                <div key={i} className="text-xs text-amber-700 bg-amber-50 rounded p-1.5 border border-amber-100">
                  {w}
                </div>
              ))}
            </div>
          )}
        </InfoCard>
      )}
    </div>
  );
}

'use client';

import { useTranslations } from 'next-intl';
import { ArrowRight, Locate, AlertTriangle, Shield, Activity } from 'lucide-react';
import Link from 'next/link';
import type { GraphEdge, GraphResponse, DryRunResult } from '@/lib/api/types';
import InfoCard from './cards/InfoCard';
import DetailRow from './cards/DetailRow';
import RiskBadge from './cards/RiskBadge';
import TrendArrow from './cards/TrendArrow';
import TagList from './cards/TagList';
import SeverityBar from './cards/SeverityBar';

interface EdgePanelProps {
  edge: GraphEdge;
  graph: GraphResponse;
  dryRunResult?: DryRunResult | null;
  removedEdgeIds?: Set<string>;
  affectedEdgeIds?: Set<string>;
  originalWeight?: number;
  altPaths?: Array<{ from: string; to: string; path: string[] }>;
  alertSeverityMap?: Record<string, 'low' | 'medium' | 'high' | 'critical'>;
  onLocateNode?: (nodeId: string) => void;
}

/** 判定边的 dry-run 状态 */
type EdgeDryRunStatus = 'severed' | 'degraded' | 'rerouted' | 'normal';

function getEdgeStatus(
  edgeId: string,
  edge: GraphEdge,
  removedEdgeIds?: Set<string>,
  affectedEdgeIds?: Set<string>,
  originalWeight?: number,
  altPaths?: Array<{ from: string; to: string; path: string[] }>,
): EdgeDryRunStatus {
  if (removedEdgeIds?.has(edgeId) || edge.weight === 0) return 'severed';
  // 检查是否在替代路径中
  const inAltPath = altPaths?.some(p =>
    p.from === edge.source || p.from === edge.target ||
    p.to === edge.source || p.to === edge.target
  );
  if (inAltPath) return 'rerouted';
  if (affectedEdgeIds?.has(edgeId) && originalWeight !== undefined && edge.weight < originalWeight) return 'degraded';
  return 'normal';
}

/** 状态标签样式 */
const statusStyles: Record<EdgeDryRunStatus, { bg: string; label: string }> = {
  severed:  { bg: 'bg-red-100 text-red-700 border-red-200',       label: 'inspector_severed' },
  degraded: { bg: 'bg-amber-100 text-amber-700 border-amber-200', label: 'inspector_degraded' },
  rerouted: { bg: 'bg-blue-100 text-blue-700 border-blue-200',    label: 'inspector_rerouted' },
  normal:   { bg: 'bg-green-100 text-green-700 border-green-200', label: 'inspector_normal' },
};

export default function EdgePanel({
  edge, graph, dryRunResult,
  removedEdgeIds, affectedEdgeIds, originalWeight,
  altPaths, alertSeverityMap, onLocateNode,
}: EdgePanelProps) {
  const t = useTranslations('topology');

  const hasDryRun = !!dryRunResult;
  const status = hasDryRun
    ? getEdgeStatus(edge.id, edge, removedEdgeIds, affectedEdgeIds, originalWeight, altPaths)
    : null;

  // 告警严重度分布
  const severityCounts = { critical: 0, high: 0, medium: 0, low: 0 };
  if (alertSeverityMap) {
    for (const aid of edge.alert_ids ?? []) {
      const sev = alertSeverityMap[aid];
      if (sev && sev in severityCounts) {
        severityCounts[sev as keyof typeof severityCounts]++;
      }
    }
  }

  // 匹配的替代路径
  const matchedAltPaths = altPaths?.filter(p =>
    p.from === edge.source || p.from === edge.target ||
    p.to === edge.source || p.to === edge.target
  ) ?? [];

  return (
    <div className="space-y-3">
      {/* 头部 */}
      <div className="flex items-center gap-2">
        <ArrowRight className="w-5 h-5 text-purple-600" />
        <h3 className="font-bold text-gray-900">{t('edge')}</h3>
        {/* dry-run 状态标签 */}
        {status && status !== 'normal' && (
          <span className={`ml-auto px-2 py-0.5 text-[10px] font-semibold rounded border ${statusStyles[status].bg}`}>
            {t(statusStyles[status].label)}
          </span>
        )}
      </div>

      {/* 端点 */}
      <InfoCard title={t('inspector_endpoints')}>
        <div className="flex items-center gap-2 text-sm">
          <button
            onClick={() => onLocateNode?.(edge.source)}
            className="font-mono text-xs text-blue-700 hover:underline truncate"
            title={t('locateNode')}
          >
            {edge.source}
          </button>
          <ArrowRight className="w-3.5 h-3.5 text-gray-400 shrink-0" />
          <button
            onClick={() => onLocateNode?.(edge.target)}
            className="font-mono text-xs text-blue-700 hover:underline truncate"
            title={t('locateNode')}
          >
            {edge.target}
          </button>
        </div>
      </InfoCard>

      {/* 协议与服务 */}
      <InfoCard title={t('inspector_protocolService')}>
        <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">{t('protocols')}</div>
        <TagList
          items={(edge.protocols ?? []).map(p => ({ label: p }))}
          color="blue"
        />
        {(edge.services ?? []).length > 0 && (
          <>
            <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1 mt-2">{t('services')}</div>
            <TagList
              items={(edge.services ?? []).map(s => ({ label: `${s.proto}/${s.port}` }))}
              color="purple"
            />
          </>
        )}
      </InfoCard>

      {/* 指标 */}
      <InfoCard title={t('inspector_metrics')} icon={<Activity className="w-3.5 h-3.5" />}>
        {/* 权重 */}
        <div className="flex justify-between items-center text-sm">
          <span className="text-gray-500">{t('weight')}</span>
          {originalWeight !== undefined ? (
            <TrendArrow before={originalWeight} after={edge.weight} higherIsBad={false} format={v => String(Math.round(v))} />
          ) : (
            <span className="font-bold text-gray-900">{edge.weight}</span>
          )}
        </div>
        {/* 边风险 */}
        {edge.risk !== undefined && (
          <div className="flex justify-between items-center text-sm">
            <span className="text-gray-500">{t('inspector_edgeRisk')}</span>
            <RiskBadge risk={edge.risk} />
          </div>
        )}
        {/* 活跃时段 */}
        {(edge.activeIntervals ?? []).length > 0 && (
          <div className="mt-1">
            <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">{t('activeIntervals')}</div>
            <div className="space-y-0.5">
              {edge.activeIntervals.map(([start, end], i) => (
                <div key={i} className="text-xs bg-blue-50 px-2 py-1 rounded border border-blue-100 font-mono text-blue-800">
                  {new Date(start).toLocaleTimeString()} — {new Date(end).toLocaleTimeString()}
                </div>
              ))}
            </div>
          </div>
        )}
      </InfoCard>

      {/* 告警摘要 */}
      <InfoCard title={t('inspector_alertSummary')} icon={<AlertTriangle className="w-3.5 h-3.5" />}>
        <div className="flex items-center gap-2 mb-1">
          <span className="text-sm text-gray-700">{t('inspector_alertCount')}</span>
          <span className="px-1.5 py-0.5 text-xs font-bold rounded bg-red-100 text-red-700">
            {(edge.alert_ids ?? []).length}
          </span>
        </div>
        <SeverityBar counts={severityCounts} />
        {/* 告警 ID 链接 */}
        {(edge.alert_ids ?? []).length > 0 && (
          <div className="mt-2 space-y-0.5">
            {(edge.alert_ids ?? []).slice(0, 5).map(aid => (
              <Link
                key={aid}
                href={`/alerts/${aid}`}
                className="block text-xs bg-red-50 px-2 py-1 rounded border border-red-100 font-mono text-red-700 hover:bg-red-100 transition-colors"
              >
                {aid.substring(0, 12)}...
              </Link>
            ))}
          </div>
        )}
      </InfoCard>

      {/* Dry-Run 影响 */}
      {hasDryRun && status && status !== 'normal' && (
        <InfoCard title={t('inspector_dryRunImpact')} icon={<Shield className="w-3.5 h-3.5" />}>
          {/* 状态说明 */}
          <div className={`px-2 py-1.5 rounded border text-xs font-medium ${statusStyles[status].bg}`}>
            {t(`inspector_${status}Desc`)}
          </div>
          {/* 替代路径 */}
          {matchedAltPaths.length > 0 && (
            <div className="mt-1">
              <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">{t('dryRunAltPaths')}</div>
              {matchedAltPaths.map((p, i) => (
                <div key={i} className="text-[10px] font-mono bg-green-50 text-green-800 rounded p-1.5 border border-green-100">
                  {p.path.join(' → ')}
                </div>
              ))}
            </div>
          )}
          {/* 动作来源 */}
          {dryRunResult?.alert_id && (
            <div className="mt-1 text-xs text-gray-500">
              {t('inspector_actionSource')}{' '}
              <Link href={`/alerts/${dryRunResult.alert_id}`} className="text-blue-600 hover:underline font-mono">
                {dryRunResult.alert_id.substring(0, 12)}...
              </Link>
            </div>
          )}
        </InfoCard>
      )}
    </div>
  );
}

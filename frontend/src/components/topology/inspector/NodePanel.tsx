'use client';

import { useTranslations } from 'next-intl';
import { Globe, Router, Locate, AlertTriangle, Shield } from 'lucide-react';
import type { GraphNode, GraphEdge, GraphResponse, DryRunResult } from '@/lib/api/types';
import { useNodeMetrics } from './hooks/useNodeMetrics';
import InfoCard from './cards/InfoCard';
import DetailRow from './cards/DetailRow';
import RiskBadge from './cards/RiskBadge';
import TrendArrow from './cards/TrendArrow';
import StatGrid from './cards/StatGrid';
import TagList from './cards/TagList';
import SeverityBar from './cards/SeverityBar';
import MiniNodeList from './cards/MiniNodeList';

interface NodePanelProps {
  node: GraphNode;
  graph: GraphResponse;
  dryRunResult?: DryRunResult | null;
  removedNodeIds?: Set<string>;
  affectedNodeIds?: Set<string>;
  originalRisk?: number;
  alertSeverityMap?: Record<string, 'low' | 'medium' | 'high' | 'critical'>;
  onLocateNode?: (nodeId: string) => void;
  onSelectNode?: (node: GraphNode) => void;
  onSelectEdge?: (edge: GraphEdge) => void;
}

/** 从节点 ID 提取 /24 子网（如 ip:192.168.1.10 → 192.168.1.0/24） */
function extractSubnet(nodeId: string): string | null {
  const m = nodeId.match(/^ip:(\d+\.\d+\.\d+)\.\d+$/);
  if (m) return `${m[1]}.0/24`;
  const sm = nodeId.match(/^subnet:(.+)$/);
  if (sm) return sm[1];
  return null;
}

/** 格式化 ISO 时间为可读字符串 */
function fmtTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString();
}

export default function NodePanel({
  node, graph, dryRunResult,
  removedNodeIds, affectedNodeIds, originalRisk,
  alertSeverityMap, onLocateNode, onSelectNode,
}: NodePanelProps) {
  const t = useTranslations('topology');
  const metrics = useNodeMetrics(node.id, graph);

  const isRemoved = removedNodeIds?.has(node.id);
  const isAffected = affectedNodeIds?.has(node.id) && !isRemoved;
  const subnet = extractSubnet(node.id);

  // 告警严重度分布
  const severityCounts = { critical: 0, high: 0, medium: 0, low: 0 };
  if (metrics && alertSeverityMap) {
    for (const aid of metrics.alertIds) {
      const sev = alertSeverityMap[aid];
      if (sev && sev in severityCounts) {
        severityCounts[sev as keyof typeof severityCounts]++;
      }
    }
  }

  // 节点类型图标
  const TypeIcon = node.type === 'gateway' || node.type === 'router' ? Router : Globe;
  const iconColor = node.type === 'gateway' || node.type === 'router' ? 'text-green-600' : 'text-blue-600';

  // 类型标签颜色
  const typeTagColor: Record<string, string> = {
    gateway: 'bg-green-50 text-green-700',
    router: 'bg-green-50 text-green-700',
    server: 'bg-cyan-50 text-cyan-700',
    subnet: 'bg-purple-50 text-purple-700',
    host: 'bg-blue-50 text-blue-700',
  };

  return (
    <div className="space-y-3">
      {/* 头部：图标 + 标签 + 定位按钮 */}
      <div className="flex items-center gap-2">
        <TypeIcon className={`w-5 h-5 ${iconColor}`} />
        <h3 className="font-bold text-gray-900 truncate flex-grow">{node.label}</h3>
        {onLocateNode && (
          <button
            onClick={() => onLocateNode(node.id)}
            className="p-1 text-gray-400 hover:text-blue-600 transition-colors shrink-0"
            title={t('locateNode')}
          >
            <Locate className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* 被移除 / 受影响状态横幅 */}
      {isRemoved && (
        <div className="p-2.5 bg-red-50 border border-red-200 rounded-lg flex items-center gap-1.5">
          <AlertTriangle className="w-3.5 h-3.5 text-red-600 shrink-0" />
          <span className="text-xs font-semibold text-red-800">{t('nodeRemoved')}</span>
        </div>
      )}
      {isAffected && (
        <div className="p-2.5 bg-amber-50 border border-amber-200 rounded-lg flex items-center gap-1.5">
          <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
          <span className="text-xs font-semibold text-amber-800">{t('nodeAffected')}</span>
        </div>
      )}

      {/* 基本信息 */}
      <InfoCard title={t('inspector_basicInfo')} icon={<Globe className="w-3.5 h-3.5" />}>
        <DetailRow label="ID" value={node.id} mono />
        <div className="flex justify-between items-center text-sm">
          <span className="text-gray-500">{t('inspectorType')}</span>
          <span className={`px-1.5 py-0.5 text-xs font-medium rounded ${typeTagColor[node.type] ?? 'bg-gray-50 text-gray-700'}`}>
            {node.type}
          </span>
        </div>
        {subnet && <DetailRow label={t('inspector_subnet')} value={subnet} mono />}
      </InfoCard>

      {/* 风险评估 */}
      <InfoCard title={t('inspector_riskAssessment')} icon={<Shield className="w-3.5 h-3.5" />}>
        <div className="flex justify-between items-center">
          <span className="text-sm text-gray-500">{t('riskScore')}</span>
          <div className="flex items-center gap-2">
            <RiskBadge risk={node.risk} />
            {originalRisk !== undefined ? (
              <TrendArrow before={originalRisk} after={node.risk} higherIsBad />
            ) : (
              <span className="text-sm font-bold text-gray-900">{node.risk.toFixed(2)}</span>
            )}
          </div>
        </div>
        {/* dry-run 可达性影响 */}
        {isAffected && dryRunResult?.impact && (
          <div className="mt-1 space-y-1 text-xs text-amber-900 bg-amber-50 rounded p-2">
            <div>{t('reachabilityDrop')} <b>{((dryRunResult.impact.reachability_drop || 0) * 100).toFixed(0)}%</b></div>
            <div>{t('disruptionRisk')} <b>{((dryRunResult.impact.service_disruption_risk || 0) * 100).toFixed(0)}%</b></div>
          </div>
        )}
      </InfoCard>

      {/* 连接度统计 */}
      {metrics && (
        <InfoCard title={t('inspector_connectivity')}>
          <StatGrid
            columns={3}
            items={[
              { label: t('inspector_inDegree'), value: metrics.inDegree },
              { label: t('inspector_outDegree'), value: metrics.outDegree },
              { label: t('inspector_neighbors'), value: metrics.totalNeighbors },
            ]}
          />
          {/* Top-N 高风险邻居 */}
          {metrics.topRiskNeighbors.length > 0 && (
            <div className="mt-2">
              <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">
                {t('inspector_topRiskNeighbors')}
              </div>
              <MiniNodeList
                items={metrics.topRiskNeighbors.map(({ node: n }) => ({
                  id: n.id,
                  label: n.label,
                  value: n.risk,
                }))}
                onSelect={(id) => {
                  const target = graph.nodes.find(n => n.id === id);
                  if (target) onSelectNode?.(target);
                }}
              />
            </div>
          )}
        </InfoCard>
      )}

      {/* 协议与服务 */}
      {metrics && (
        <InfoCard title={t('inspector_protocolService')}>
          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">{t('protocols')}</div>
          <TagList
            items={Object.entries(metrics.protocolCounts).map(([p, c]) => ({ label: p, count: c }))}
            color="blue"
          />
          {metrics.servicePorts.length > 0 && (
            <>
              <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1 mt-2">{t('services')}</div>
              <TagList
                items={metrics.servicePorts.map(s => ({ label: `${s.proto}/${s.port}`, count: s.count }))}
                color="purple"
              />
            </>
          )}
        </InfoCard>
      )}

      {/* 活动时间线 */}
      {metrics && (
        <InfoCard title={t('inspector_activityTimeline')}>
          <DetailRow label={t('inspector_firstSeen')} value={fmtTime(metrics.firstSeen)} />
          <DetailRow label={t('inspector_lastSeen')} value={fmtTime(metrics.lastSeen)} />
          <DetailRow label={t('inspector_cumulativeWeight')} value={String(metrics.cumulativeWeight)} />
        </InfoCard>
      )}

      {/* 告警摘要 */}
      {metrics && (
        <InfoCard title={t('inspector_alertSummary')} icon={<AlertTriangle className="w-3.5 h-3.5" />}>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm text-gray-700">{t('inspector_alertCount')}</span>
            <span className="px-1.5 py-0.5 text-xs font-bold rounded bg-red-100 text-red-700">
              {metrics.alertIds.length}
            </span>
          </div>
          <SeverityBar counts={severityCounts} />
        </InfoCard>
      )}

      {/* Dry-Run 影响详情 */}
      {dryRunResult && (isRemoved || isAffected) && (
        <InfoCard title={t('inspector_dryRunImpact')} icon={<AlertTriangle className="w-3.5 h-3.5" />}>
          {/* 节点相关警告 */}
          {dryRunResult.impact.warnings?.map((w, i) =>
            w.toLowerCase().includes(node.label.toLowerCase()) && (
              <div key={i} className="text-xs text-amber-700 italic bg-amber-50 rounded p-1.5">
                {w}
              </div>
            )
          )}
          {/* 可达性详情 */}
          {dryRunResult.impact.reachability_detail && (
            <div className="space-y-1 text-xs">
              <DetailRow label={t('pairDrop')} value={`${(dryRunResult.impact.reachability_detail.pair_reachability_drop * 100).toFixed(0)}%`} />
              <DetailRow label={t('serviceDrop')} value={`${(dryRunResult.impact.reachability_detail.service_reachability_drop * 100).toFixed(0)}%`} />
              <DetailRow label={t('subnetDrop')} value={`${(dryRunResult.impact.reachability_detail.subnet_reachability_drop * 100).toFixed(0)}%`} />
            </div>
          )}
        </InfoCard>
      )}
    </div>
  );
}

'use client';

import { GraphNode, GraphEdge, DryRunResult } from '@/lib/api/types';
import { X, Globe, Router, ArrowRight, ShieldAlert, AlertTriangle, Locate } from 'lucide-react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';

interface SideInspectorProps {
  selectedNode: GraphNode | null;
  selectedEdge: GraphEdge | null;
  dryRunResult?: DryRunResult | null;
  impactedNodeIds?: Set<string>;
  impactedEdgeIds?: Set<string>;
  /** Original risk/weight values before dry-run deltas were applied */
  originalValues?: { nodeRisks: Record<string, number>; edgeWeights: Record<string, number> };
  onClose: () => void;
  onLocateNode?: (nodeId: string) => void;
}

export default function SideInspector({ selectedNode, selectedEdge, dryRunResult, impactedNodeIds, impactedEdgeIds, originalValues, onClose, onLocateNode }: SideInspectorProps) {
  const t = useTranslations('topology');
  const hasSelection = selectedNode || selectedEdge;
  const nodeIsImpacted = selectedNode && impactedNodeIds?.has(selectedNode.id);
  const edgeIsImpacted = selectedEdge && impactedEdgeIds?.has(selectedEdge.id);

  return (
    <div className="w-80 border-l border-gray-200 bg-white flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 shrink-0">
        <h2 className="font-medium text-gray-900 text-sm">{t('inspectorTitle')}</h2>
        {hasSelection && (
          <button onClick={onClose} className="p-1 text-gray-400 hover:text-gray-700">
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      <div className="flex-grow overflow-y-auto p-4">
        {!hasSelection && (
          <div className="text-sm text-gray-400 text-center py-12">
            {t('inspectorPrompt')}
          </div>
        )}

        {/* Node Inspector */}
        {selectedNode && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              {selectedNode.type === 'gateway' ? (
                <Router className="w-5 h-5 text-green-600" />
              ) : (
                <Globe className="w-5 h-5 text-blue-600" />
              )}
              <h3 className="font-bold text-gray-900">{selectedNode.label}</h3>
              {onLocateNode && (
                <button
                  onClick={() => onLocateNode(selectedNode.id)}
                  className="ml-auto p-1 text-gray-400 hover:text-blue-600 transition-colors"
                  title={t('locateNode')}
                >
                  <Locate className="w-4 h-4" />
                </button>
              )}
            </div>

            <div className="space-y-2">
              <DetailRow label={t('inspectorId')} value={selectedNode.id} mono />
              <DetailRow label={t('inspectorType')} value={selectedNode.type} />
              {originalValues?.nodeRisks[selectedNode.id] !== undefined ? (
                <div className="flex justify-between items-center text-sm">
                  <span className="text-gray-500">{t('riskScore')}</span>
                  <div className="flex items-center gap-2">
                    <RiskBadge risk={selectedNode.risk} />
                    <span className="text-gray-400 line-through text-xs">{originalValues.nodeRisks[selectedNode.id].toFixed(2)}</span>
                    <span className="text-green-600 font-bold">&rarr; {selectedNode.risk.toFixed(2)}</span>
                  </div>
                </div>
              ) : (
                <DetailRow label={t('riskScore')} value={selectedNode.risk.toFixed(2)}>
                  <RiskBadge risk={selectedNode.risk} />
                </DetailRow>
              )}
            </div>

            {/* Dry-run impact info */}
            {nodeIsImpacted && dryRunResult && (
              <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                <div className="flex items-center gap-1.5 text-amber-800 font-semibold text-xs mb-2">
                  <AlertTriangle className="w-3.5 h-3.5" /> {t('dryRunImpact')}
                </div>
                <div className="space-y-1 text-xs text-amber-900">
                  <div>{t('reachabilityDrop')} <b>{((dryRunResult.impact.reachability_drop || 0) * 100).toFixed(0)}%</b></div>
                  <div>{t('disruptionRisk')} <b>{((dryRunResult.impact.service_disruption_risk || 0) * 100).toFixed(0)}%</b></div>
                  {dryRunResult.impact.warnings?.map((w, i) =>
                    w.toLowerCase().includes(selectedNode.label.toLowerCase()) && (
                      <div key={i} className="text-amber-700 italic">⚠ {w}</div>
                    )
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Edge Inspector */}
        {selectedEdge && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <ArrowRight className="w-5 h-5 text-purple-600" />
              <h3 className="font-bold text-gray-900">{t('edge')}</h3>
            </div>

            <div className="space-y-2">
              <DetailRow label={t('source')} value={selectedEdge.source} mono />
              <DetailRow label={t('target')} value={selectedEdge.target} mono />
              {originalValues?.edgeWeights[selectedEdge.id] !== undefined ? (
                <div className="flex justify-between items-center text-sm">
                  <span className="text-gray-500">{t('weight')}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-gray-400 line-through text-xs">{originalValues.edgeWeights[selectedEdge.id]}</span>
                    <span className={`font-bold ${selectedEdge.weight === 0 ? 'text-red-600' : 'text-green-600'}`}>
                      &rarr; {selectedEdge.weight}{selectedEdge.weight === 0 && ` ${t('severed')}`}
                    </span>
                  </div>
                </div>
              ) : (
                <DetailRow label={t('weight')} value={String(selectedEdge.weight)} />
              )}
              <DetailRow label={t('protocols')} value={(selectedEdge.protocols ?? []).join(', ') || '—'} />
            </div>

            {/* Services */}
            {(selectedEdge.services ?? []).length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">{t('services')}</h4>
                <div className="space-y-1">
                  {(selectedEdge.services ?? []).map((s, i) => (
                    <div key={i} className="text-sm bg-gray-50 px-2 py-1 rounded border border-gray-100 font-mono">
                      {s.proto}/{s.port}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Active Intervals */}
            {selectedEdge.activeIntervals.length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">{t('activeIntervals')}</h4>
                <div className="space-y-1">
                  {selectedEdge.activeIntervals.map(([start, end], i) => (
                    <div key={i} className="text-xs bg-blue-50 px-2 py-1 rounded border border-blue-100 font-mono text-blue-800">
                      {new Date(start).toLocaleTimeString()} — {new Date(end).toLocaleTimeString()}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Alert IDs */}
            {(selectedEdge.alert_ids ?? []).length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
                  <ShieldAlert className="w-3.5 h-3.5 inline mr-1" />
                  {t('relatedAlerts')} ({selectedEdge.alert_ids.length})
                </h4>
                <div className="space-y-1">
                  {(selectedEdge.alert_ids ?? []).map(aid => (
                    <Link
                      key={aid}
                      href={`/alerts/${aid}`}
                      className="block text-xs bg-red-50 px-2 py-1.5 rounded border border-red-100 font-mono text-red-700 hover:bg-red-100 transition-colors"
                    >
                      {aid.substring(0, 8)}... →
                    </Link>
                  ))}
                </div>
              </div>
            )}
            {(selectedEdge.alert_ids ?? []).length === 0 && (
              <div className="text-xs text-gray-400 italic">{t('noAlerts')}</div>
            )}

            {/* Dry-run impact info */}
            {edgeIsImpacted && dryRunResult && (
              <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg">
                <div className="flex items-center gap-1.5 text-amber-800 font-semibold text-xs mb-2">
                  <AlertTriangle className="w-3.5 h-3.5" /> {t('dryRunImpact')}
                </div>
                <div className="space-y-1 text-xs text-amber-900">
                  <div>{t('edgeImpacted')}</div>
                  <div>{t('impactedNodesLabel')} <b>{dryRunResult.impact.impacted_nodes_count || 0}</b></div>
                  <div>{t('disruptionRisk')} <b>{((dryRunResult.impact.service_disruption_risk || 0) * 100).toFixed(0)}%</b></div>
                  {dryRunResult.alternative_paths?.map((p, i) => (
                    (p.from === selectedEdge.source || p.from === selectedEdge.target ||
                     p.to === selectedEdge.source || p.to === selectedEdge.target) && (
                      <div key={i} className="mt-1 font-mono text-[10px] bg-amber-100 rounded p-1">
                        {t('alt')} {p.path.join(' → ')}
                      </div>
                    )
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Helper components ──

function DetailRow({
  label,
  value,
  mono,
  children,
}: {
  label: string;
  value: string;
  mono?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex justify-between items-center text-sm">
      <span className="text-gray-500">{label}</span>
      <div className="flex items-center gap-2">
        {children}
        <span className={`text-gray-900 ${mono ? 'font-mono text-xs' : ''}`}>{value}</span>
      </div>
    </div>
  );
}

function RiskBadge({ risk }: { risk: number }) {
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

'use client';

import { GraphNode, GraphEdge, DryRunResult } from '@/lib/api/types';
import { X, Globe, Router, ArrowRight, ShieldAlert, AlertTriangle } from 'lucide-react';
import Link from 'next/link';

interface SideInspectorProps {
  selectedNode: GraphNode | null;
  selectedEdge: GraphEdge | null;
  dryRunResult?: DryRunResult | null;
  impactedNodeIds?: Set<string>;
  impactedEdgeIds?: Set<string>;
  onClose: () => void;
}

export default function SideInspector({ selectedNode, selectedEdge, dryRunResult, impactedNodeIds, impactedEdgeIds, onClose }: SideInspectorProps) {
  const hasSelection = selectedNode || selectedEdge;
  const nodeIsImpacted = selectedNode && impactedNodeIds?.has(selectedNode.id);
  const edgeIsImpacted = selectedEdge && impactedEdgeIds?.has(selectedEdge.id);

  return (
    <div className="w-80 border-l border-gray-200 bg-white flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 shrink-0">
        <h2 className="font-medium text-gray-900 text-sm">Inspector</h2>
        {hasSelection && (
          <button onClick={onClose} className="p-1 text-gray-400 hover:text-gray-700">
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      <div className="flex-grow overflow-y-auto p-4">
        {!hasSelection && (
          <div className="text-sm text-gray-400 text-center py-12">
            Click a node or edge in the 3D view to inspect details.
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
            </div>

            <div className="space-y-2">
              <DetailRow label="ID" value={selectedNode.id} mono />
              <DetailRow label="Type" value={selectedNode.type} />
              <DetailRow label="Risk Score" value={selectedNode.risk.toFixed(2)}>
                <RiskBadge risk={selectedNode.risk} />
              </DetailRow>
            </div>

            {/* Dry-run impact info */}
            {nodeIsImpacted && dryRunResult && (
              <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                <div className="flex items-center gap-1.5 text-amber-800 font-semibold text-xs mb-2">
                  <AlertTriangle className="w-3.5 h-3.5" /> Dry-Run Impact
                </div>
                <div className="space-y-1 text-xs text-amber-900">
                  <div>Reachability drop: <b>{((dryRunResult.impact.reachability_drop || 0) * 100).toFixed(0)}%</b></div>
                  <div>Disruption risk: <b>{((dryRunResult.impact.service_disruption_risk || 0) * 100).toFixed(0)}%</b></div>
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
              <h3 className="font-bold text-gray-900">Edge</h3>
            </div>

            <div className="space-y-2">
              <DetailRow label="Source" value={selectedEdge.source} mono />
              <DetailRow label="Target" value={selectedEdge.target} mono />
              <DetailRow label="Weight" value={String(selectedEdge.weight)} />
              <DetailRow label="Protocols" value={(selectedEdge.protocols ?? []).join(', ') || '—'} />
            </div>

            {/* Services */}
            {(selectedEdge.services ?? []).length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Services</h4>
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
                <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Active Intervals</h4>
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
                  Related Alerts ({selectedEdge.alert_ids.length})
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
              <div className="text-xs text-gray-400 italic">No alerts on this edge.</div>
            )}

            {/* Dry-run impact info */}
            {edgeIsImpacted && dryRunResult && (
              <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg">
                <div className="flex items-center gap-1.5 text-amber-800 font-semibold text-xs mb-2">
                  <AlertTriangle className="w-3.5 h-3.5" /> Dry-Run Impact
                </div>
                <div className="space-y-1 text-xs text-amber-900">
                  <div>This edge is <b>affected</b> by the simulated action plan.</div>
                  <div>Impacted nodes: <b>{dryRunResult.impact.impacted_nodes_count || 0}</b></div>
                  <div>Disruption risk: <b>{((dryRunResult.impact.service_disruption_risk || 0) * 100).toFixed(0)}%</b></div>
                  {dryRunResult.alternative_paths?.map((p, i) => (
                    (p.from === selectedEdge.source || p.from === selectedEdge.target ||
                     p.to === selectedEdge.source || p.to === selectedEdge.target) && (
                      <div key={i} className="mt-1 font-mono text-[10px] bg-amber-100 rounded p-1">
                        Alt: {p.path.join(' → ')}
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
  const color =
    risk > 0.7 ? 'bg-red-100 text-red-700' :
    risk > 0.3 ? 'bg-yellow-100 text-yellow-700' :
    'bg-green-100 text-green-700';
  const label = risk > 0.7 ? 'High' : risk > 0.3 ? 'Medium' : 'Low';
  return (
    <span className={`px-1.5 py-0.5 text-xs font-medium rounded ${color}`}>
      {label}
    </span>
  );
}

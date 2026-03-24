'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { wsClient } from '@/lib/ws';
import { DryRunResult } from '@/lib/api/types';
import { Play, AlertTriangle, ArrowRight, Activity, Map, ExternalLink, RefreshCw } from 'lucide-react';
import clsx from 'clsx';
import { useTranslations } from 'next-intl';

interface DryRunPanelProps {
  alertId: string;
  planId: string;
  onDryRunCompleted?: () => Promise<void>;
}

interface DryRunCreatedEvent {
  dry_run_id: string;
  alert_id: string;
  risk: number;
}

// 仅对 compiled plan 生效，不支持手工 plan 路径
export default function DryRunPanel({ alertId, planId, onDryRunCompleted }: DryRunPanelProps) {
  const t = useTranslations('twin');
  const router = useRouter();
  const [result, setResult] = useState<DryRunResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const processedDryRunIds = useRef<Set<string>>(new Set());

  // 订阅 twin.dryrun.created 的 WebSocket 事件
  // 事件载荷较轻：{ dry_run_id, alert_id, risk }
  // 按 alertId 匹配后，再通过 dry_run_id 拉取完整 DryRunResult
  useEffect(() => {
    const unsub = wsClient.onEvent('twin.dryrun.created', async (payload: DryRunCreatedEvent) => {
      if (payload.alert_id !== alertId) return;
      if (processedDryRunIds.current.has(payload.dry_run_id)) return;
      processedDryRunIds.current.add(payload.dry_run_id);
      setRefreshing(true);
      try {
        const full = await api.getDryRun(payload.dry_run_id);
        setResult(full);
        onDryRunCompleted?.();
      } catch (e) {
        console.error('Failed to fetch dry-run detail:', e);
      } finally {
        setRefreshing(false);
      }
    });
    return unsub;
  }, [alertId]);

  const handleDryRun = async () => {
    setLoading(true);
    try {
      const res = await api.dryRunPlan(planId, { mode: 'ip' });
      setResult(res);
      onDryRunCompleted?.();
    } catch (e) {
      console.error(e);
      alert(t('dryRunFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleOpenTopology = () => {
    if (result) {
      router.push(`/topology?highlightAlertId=${alertId}&dryRunId=${result.id}`);
    }
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden" id="dryrun-panel">
      <div className="bg-gray-50 px-4 py-3 border-b border-gray-100 flex justify-between items-center">
        <h3 className="font-semibold text-gray-900 flex items-center gap-2">
          <Activity className="w-5 h-5 text-indigo-600" /> {t('dryRunTitle')}
        </h3>
        <div className="flex items-center gap-2">
          {refreshing && (
            <span className="flex items-center gap-1 text-xs text-indigo-500">
              <RefreshCw className="w-3 h-3 animate-spin" /> {t('refreshing')}
            </span>
          )}
          {result && (
            <span className="text-xs text-gray-500 font-mono">ID: {result.id}</span>
          )}
        </div>
      </div>

      <div className="p-4">
        {!result ? (
          <div className="text-center py-6">
            <p className="text-gray-500 mb-4 text-sm">
              {t('dryRunPrompt')}
            </p>
            <button
              onClick={handleDryRun}
              disabled={loading}
              className="px-6 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded shadow-sm font-medium flex items-center gap-2 mx-auto disabled:opacity-50"
            >
              {loading ? (
                <span className="animate-pulse">{t('simulating')}</span>
              ) : (
                <>
                  <Play className="w-4 h-4" /> {t('runSimulation')}
                </>
              )}
            </button>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Impact Metrics */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="p-3 bg-red-50 rounded border border-red-100 text-center">
                <div className="text-xs text-red-600 uppercase font-bold tracking-wider mb-1">{t('disruptionRisk')}</div>
                <div className="text-2xl font-bold text-red-700">
                  {((result.impact.service_disruption_risk || 0) * 100).toFixed(0)}%
                </div>
              </div>
              <div className="p-3 bg-orange-50 rounded border border-orange-100 text-center">
                <div className="text-xs text-orange-600 uppercase font-bold tracking-wider mb-1">{t('reachabilityDrop')}</div>
                <div className="text-2xl font-bold text-orange-700">
                  {((result.impact.reachability_drop || 0) * 100).toFixed(0)}%
                </div>
              </div>
              <div className="p-3 bg-gray-50 rounded border border-gray-100 text-center">
                <div className="text-xs text-gray-500 uppercase font-bold tracking-wider mb-1">{t('impactedNodes')}</div>
                <div className="text-2xl font-bold text-gray-700">
                  {result.impact.impacted_nodes_count || 0}
                </div>
              </div>
              <div className="p-3 bg-gray-50 rounded border border-gray-100 flex items-center justify-center">
                 <button 
                  onClick={handleOpenTopology}
                  className="flex flex-col items-center text-indigo-600 hover:text-indigo-800 transition-colors"
                >
                  <ExternalLink className="w-5 h-5 mb-1" />
                  <span className="text-xs font-semibold">{t('viewInTopology')}</span>
                </button>
              </div>
            </div>

            {/* Warnings */}
            {result.impact.warnings && result.impact.warnings.length > 0 && (
              <div className="bg-amber-50 border border-amber-200 rounded p-3">
                <h4 className="flex items-center gap-2 text-amber-800 font-semibold text-sm mb-2">
                  <AlertTriangle className="w-4 h-4" /> {t('warnings')}
                </h4>
                <ul className="list-disc pl-5 text-sm text-amber-900 space-y-1">
                  {result.impact.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Explanations */}
             {result.explain && result.explain.length > 0 && (
               <div>
                  <h4 className="text-sm font-semibold text-gray-700 mb-2">{t('analysis')}</h4>
                  <ul className="space-y-1 text-sm text-gray-600">
                     {result.explain.map((text, i) => (
                       <li key={i} className="flex gap-2">
                         <span className="text-indigo-400">•</span> {text}
                       </li>
                     ))}
                  </ul>
               </div>
             )}

            {/* Alternative Paths */}
            {result.alternative_paths && result.alternative_paths.length > 0 && (
              <div>
                <h4 className="flex items-center gap-2 text-sm font-semibold text-gray-700 mb-3">
                  <Map className="w-4 h-4 text-gray-500" /> {t('altPaths')}
                </h4>
                <div className="space-y-2">
                  {result.alternative_paths.map((pathObj, i) => (
                    <div key={i} className="bg-gray-50 border border-gray-200 rounded p-2 text-xs font-mono overflow-x-auto">
                      <div className="flex items-center gap-2 text-gray-500 mb-1">
                        <span>{pathObj.from}</span>
                        <ArrowRight className="w-3 h-3" />
                        <span>{pathObj.to}</span>
                      </div>
                      <div className="flex items-center gap-1 text-gray-800">
                         {t('path')} {pathObj.path.join(' → ')}
                      </div>
                    </div>
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

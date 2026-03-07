'use client';

import { useState } from 'react';
import { DryRunResult } from '@/lib/api/types';
import { AlertTriangle, X, Activity, ArrowRight, Loader2 } from 'lucide-react';
import { useTranslations } from 'next-intl';

interface DryRunOverlayProps {
  result: DryRunResult | null;
  loading: boolean;
}

export default function DryRunOverlay({ result, loading }: DryRunOverlayProps) {
  const t = useTranslations('topology');
  const [collapsed, setCollapsed] = useState(false);

  if (loading) {
    return (
      <div className="absolute top-2 left-2 z-10 bg-white/95 backdrop-blur rounded-lg shadow-lg border border-indigo-200 p-3 w-64">
        <div className="flex items-center gap-2 text-indigo-600 text-sm">
          <Loader2 className="w-4 h-4 animate-spin" /> {t('dryRunLoading')}
        </div>
      </div>
    );
  }

  if (!result) return null;

  if (collapsed) {
    return (
      <button
        onClick={() => setCollapsed(false)}
        className="absolute top-2 left-2 z-10 bg-indigo-600 text-white rounded-lg shadow-lg px-3 py-2 text-xs font-semibold flex items-center gap-2 hover:bg-indigo-700"
      >
        <Activity className="w-4 h-4" /> {t('dryRunTitle')}
      </button>
    );
  }

  return (
    <div className="absolute top-2 left-2 z-10 bg-white/95 backdrop-blur rounded-lg shadow-lg border border-indigo-200 w-72">
      <div className="flex items-center justify-between px-3 py-2 border-b border-indigo-100 bg-indigo-50/50 rounded-t-lg">
        <span className="text-sm font-semibold text-indigo-800 flex items-center gap-1.5">
          <Activity className="w-4 h-4" /> {t('dryRunTitle')}
        </span>
        <button onClick={() => setCollapsed(true)} className="text-gray-400 hover:text-gray-600">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="p-3 space-y-3 text-xs">
        {/* Key Metrics */}
        <div className="grid grid-cols-3 gap-2">
          <div className="text-center p-2 bg-red-50 rounded border border-red-100">
            <div className="text-[10px] text-red-500 font-bold uppercase">{t('risk')}</div>
            <div className="text-lg font-bold text-red-700">
              {((result.impact.service_disruption_risk || 0) * 100).toFixed(0)}%
            </div>
          </div>
          <div className="text-center p-2 bg-orange-50 rounded border border-orange-100">
            <div className="text-[10px] text-orange-500 font-bold uppercase">{t('drop')}</div>
            <div className="text-lg font-bold text-orange-700">
              {((result.impact.reachability_drop || 0) * 100).toFixed(0)}%
            </div>
          </div>
          <div className="text-center p-2 bg-gray-50 rounded border border-gray-100">
            <div className="text-[10px] text-gray-500 font-bold uppercase">{t('nodes')}</div>
            <div className="text-lg font-bold text-gray-700">
              {result.impact.impacted_nodes_count || 0}
            </div>
          </div>
        </div>

        {/* Warnings */}
        {result.impact.warnings && result.impact.warnings.length > 0 && (
          <div className="bg-amber-50 border border-amber-200 rounded p-2">
            <div className="flex items-center gap-1 text-amber-800 font-bold mb-1">
              <AlertTriangle className="w-3 h-3" /> {t('dryRunWarnings')}
            </div>
            <ul className="list-disc pl-4 text-amber-900 space-y-0.5">
              {result.impact.warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          </div>
        )}

        {/* Explanations */}
        {result.explain && result.explain.length > 0 && (
          <div>
            <div className="font-bold text-gray-600 mb-1">{t('dryRunAnalysis')}</div>
            <ul className="space-y-0.5 text-gray-600">
              {result.explain.map((txt, i) => (
                <li key={i} className="flex gap-1">
                  <span className="text-indigo-400 shrink-0">•</span> {txt}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Alternative Paths */}
        {result.alternative_paths && result.alternative_paths.length > 0 && (
          <div>
            <div className="font-bold text-gray-600 mb-1">{t('dryRunAltPaths')}</div>
            {result.alternative_paths.map((p, i) => (
              <div key={i} className="bg-gray-50 rounded border border-gray-200 p-1.5 mb-1 font-mono text-[10px]">
                <div className="text-gray-500 flex items-center gap-1">
                  {p.from} <ArrowRight className="w-3 h-3" /> {p.to}
                </div>
                <div className="text-gray-800">{p.path.join(' → ')}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

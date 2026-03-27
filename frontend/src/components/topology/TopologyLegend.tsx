'use client';

import { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { useTranslations } from 'next-intl';

const NODE_COLORS = [
  { color: '#3b82f6', labelKey: 'hostLowRisk' },
  { color: '#06b6d4', labelKey: 'server' },
  { color: '#22c55e', labelKey: 'gateway' },
  { color: '#8b5cf6', labelKey: 'subnetNode' },
  { color: '#f97316', labelKey: 'highRisk' },
  { color: '#eab308', labelKey: 'mediumRisk' },
  { color: '#6ee7b7', labelKey: 'minimalRisk' },
  { color: '#ef4444', labelKey: 'highlighted' },
  { color: '#dc2626', labelKey: 'removedNode' },
  { color: '#f59e0b', labelKey: 'affectedNode' },
];

const EDGE_COLORS = [
  { color: '#ef4444', labelKey: 'alertEdge' },
  { color: '#f97316', labelKey: 'edgeWithAlerts' },
  { color: '#9ca3af', labelKey: 'normalEdge' },
  { color: '#22c55e', labelKey: 'altPathEdge', dashed: true },
  { color: '#dc2626', labelKey: 'removedEdge', dashed: true },
  { color: '#f59e0b', labelKey: 'affectedEdge', dashed: true },
];

export default function TopologyLegend() {
  const t = useTranslations('topology');
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="absolute top-2 right-2 z-10 bg-white/90 backdrop-blur rounded-lg shadow-md border border-gray-200 text-xs w-48">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-3 py-2 font-semibold text-gray-700 hover:bg-gray-50 rounded-t-lg"
      >
        {t('legendTitle')}
        {collapsed ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronUp className="w-3.5 h-3.5" />}
      </button>

      {!collapsed && (
        <div className="px-3 pb-2 space-y-2">
          {/* Node colors */}
          <div>
            <div className="text-[10px] uppercase tracking-wide text-gray-400 mb-1">{t('nodes')}</div>
            <ul className="space-y-0.5">
              {NODE_COLORS.map((item) => (
                <li key={item.labelKey} className="flex items-center gap-1.5">
                  <span
                    className="inline-block w-3 h-3 rounded-full shrink-0"
                    style={{ backgroundColor: item.color }}
                  />
                  <span className="text-gray-600">{t(item.labelKey)}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Edge colors */}
          <div>
            <div className="text-[10px] uppercase tracking-wide text-gray-400 mb-1">{t('edges')}</div>
            <ul className="space-y-0.5">
              {EDGE_COLORS.map((item) => (
                <li key={item.labelKey} className="flex items-center gap-1.5">
                  <span
                    className={`inline-block w-5 h-0.5 shrink-0 rounded ${item.dashed ? 'border-t border-dashed' : ''}`}
                    style={item.dashed ? { borderColor: item.color } : { backgroundColor: item.color }}
                  />
                  <span className="text-gray-600">{t(item.labelKey)}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Risk heat gradient */}
          <div>
            <div className="text-[10px] uppercase tracking-wide text-gray-400 mb-1">{t('riskHeatLegend')}</div>
            <div className="flex items-center gap-1.5">
              <div className="h-2 flex-grow rounded-full" style={{ background: 'linear-gradient(to right, #22c55e, #eab308, #ef4444)' }} />
              <span className="text-[10px] text-gray-500">0 → 1</span>
            </div>
          </div>

          {/* Arrow legend */}
          <div className="flex items-center gap-1.5 text-gray-500">
            <span className="text-[10px]">▸</span>
            <span>{t('arrowLegend')}</span>
          </div>
        </div>
      )}
    </div>
  );
}

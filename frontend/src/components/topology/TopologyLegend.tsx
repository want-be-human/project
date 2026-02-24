'use client';

import { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

const NODE_COLORS = [
  { color: '#3b82f6', label: 'Host (low risk)' },
  { color: '#06b6d4', label: 'Server' },
  { color: '#22c55e', label: 'Gateway / Router' },
  { color: '#8b5cf6', label: 'Subnet' },
  { color: '#f97316', label: 'High risk (≥0.7)' },
  { color: '#eab308', label: 'Medium risk (≥0.4)' },
  { color: '#6ee7b7', label: 'Minimal risk (<0.2)' },
  { color: '#ef4444', label: 'Highlighted (alert)' },
];

const EDGE_COLORS = [
  { color: '#ef4444', label: 'Alert-highlighted edge' },
  { color: '#f97316', label: 'Edge with alerts' },
  { color: '#9ca3af', label: 'Normal edge' },
];

export default function TopologyLegend() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="absolute top-2 right-2 z-10 bg-white/90 backdrop-blur rounded-lg shadow-md border border-gray-200 text-xs w-48">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-3 py-2 font-semibold text-gray-700 hover:bg-gray-50 rounded-t-lg"
      >
        Legend
        {collapsed ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronUp className="w-3.5 h-3.5" />}
      </button>

      {!collapsed && (
        <div className="px-3 pb-2 space-y-2">
          {/* Node colors */}
          <div>
            <div className="text-[10px] uppercase tracking-wide text-gray-400 mb-1">Nodes</div>
            <ul className="space-y-0.5">
              {NODE_COLORS.map((item) => (
                <li key={item.label} className="flex items-center gap-1.5">
                  <span
                    className="inline-block w-3 h-3 rounded-full shrink-0"
                    style={{ backgroundColor: item.color }}
                  />
                  <span className="text-gray-600">{item.label}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Edge colors */}
          <div>
            <div className="text-[10px] uppercase tracking-wide text-gray-400 mb-1">Edges</div>
            <ul className="space-y-0.5">
              {EDGE_COLORS.map((item) => (
                <li key={item.label} className="flex items-center gap-1.5">
                  <span
                    className="inline-block w-5 h-0.5 shrink-0 rounded"
                    style={{ backgroundColor: item.color }}
                  />
                  <span className="text-gray-600">{item.label}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}

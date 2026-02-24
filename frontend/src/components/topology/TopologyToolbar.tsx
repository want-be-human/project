'use client';

import { RefreshCw, Crosshair } from 'lucide-react';

interface TopologyToolbarProps {
  mode: 'ip' | 'subnet';
  onModeChange: (mode: 'ip' | 'subnet') => void;
  highlightAlertId: string | null;
  onRefresh: () => void;
  loading?: boolean;
}

export default function TopologyToolbar({
  mode,
  onModeChange,
  highlightAlertId,
  onRefresh,
  loading,
}: TopologyToolbarProps) {
  return (
    <div className="flex items-center gap-3 px-4 py-2 border-b border-gray-200 bg-white shrink-0">
      {/* Mode toggle */}
      <div className="flex rounded-lg border border-gray-200 overflow-hidden text-sm">
        <button
          className={`px-3 py-1.5 font-medium transition-colors ${
            mode === 'ip'
              ? 'bg-blue-600 text-white'
              : 'bg-white text-gray-600 hover:bg-gray-50'
          }`}
          onClick={() => onModeChange('ip')}
        >
          IP
        </button>
        <button
          className={`px-3 py-1.5 font-medium transition-colors ${
            mode === 'subnet'
              ? 'bg-blue-600 text-white'
              : 'bg-white text-gray-600 hover:bg-gray-50'
          }`}
          onClick={() => onModeChange('subnet')}
        >
          Subnet
        </button>
      </div>

      {/* Refresh */}
      <button
        onClick={onRefresh}
        disabled={loading}
        className="p-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 disabled:opacity-50 transition-colors"
        title="Refresh topology"
      >
        <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
      </button>

      {/* Spacer */}
      <div className="flex-grow" />

      {/* Highlight indicator */}
      {highlightAlertId && (
        <div
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-red-50 border border-red-200 text-red-700 text-xs font-medium relative group cursor-default"
        >
          <Crosshair className="w-3.5 h-3.5" />
          <span>Highlighting alert</span>
          <span className="font-mono">{highlightAlertId.substring(0, 8)}...</span>
          {/* Full ID tooltip on hover */}
          <div className="absolute top-full right-0 mt-1 px-3 py-1.5 bg-gray-900 text-white text-xs font-mono rounded shadow-lg whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50">
            {highlightAlertId}
          </div>
        </div>
      )}
    </div>
  );
}

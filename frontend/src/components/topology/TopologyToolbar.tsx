'use client';

import { RefreshCw, Crosshair, Layout, Eye, EyeOff, ArrowRight, Thermometer, Box, MonitorUp, RotateCcw } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { LayoutMode } from './layouts/types';
import type { CameraPreset } from './CameraController';

interface TopologyToolbarProps {
  mode: 'ip' | 'subnet';
  onModeChange: (mode: 'ip' | 'subnet') => void;
  highlightAlertId: string | null;
  onRefresh: () => void;
  loading?: boolean;
  startTime?: string;
  endTime?: string;
  onStartTimeChange?: (value: string) => void;
  onEndTimeChange?: (value: string) => void;
  // ── New props ──
  layoutMode?: LayoutMode;
  onLayoutModeChange?: (mode: LayoutMode) => void;
  showLabels?: boolean;
  onShowLabelsChange?: (v: boolean) => void;
  showArrows?: boolean;
  onShowArrowsChange?: (v: boolean) => void;
  riskHeatEnabled?: boolean;
  onRiskHeatChange?: (v: boolean) => void;
  onCameraPreset?: (preset: CameraPreset) => void;
}

const LAYOUT_OPTIONS: { value: LayoutMode; labelKey: string }[] = [
  { value: 'circle', labelKey: 'layoutCircle' },
  { value: 'force', labelKey: 'layoutForce' },
  { value: 'dag', labelKey: 'layoutDag' },
  { value: 'clustered-subnet', labelKey: 'layoutCluster' },
];

export default function TopologyToolbar({
  mode,
  onModeChange,
  highlightAlertId,
  onRefresh,
  loading,
  startTime,
  endTime,
  onStartTimeChange,
  onEndTimeChange,
  layoutMode = 'circle',
  onLayoutModeChange,
  showLabels = true,
  onShowLabelsChange,
  showArrows = false,
  onShowArrowsChange,
  riskHeatEnabled = false,
  onRiskHeatChange,
  onCameraPreset,
}: TopologyToolbarProps) {
  const t = useTranslations('topology');
  return (
    <div className="flex items-center gap-3 px-4 py-2 border-b border-gray-200 bg-white shrink-0 flex-wrap">
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
          {t('ip')}
        </button>
        <button
          className={`px-3 py-1.5 font-medium transition-colors ${
            mode === 'subnet'
              ? 'bg-blue-600 text-white'
              : 'bg-white text-gray-600 hover:bg-gray-50'
          }`}
          onClick={() => onModeChange('subnet')}
        >
          {t('subnet')}
        </button>
      </div>

      {/* ── Layout mode selector ── */}
      {onLayoutModeChange && (
        <div className="flex items-center gap-1.5">
          <Layout className="w-3.5 h-3.5 text-gray-400" />
          <select
            value={layoutMode}
            onChange={(e) => onLayoutModeChange(e.target.value as LayoutMode)}
            className="text-xs border border-gray-200 rounded px-2 py-1.5 bg-white text-gray-700 cursor-pointer focus:outline-none focus:ring-1 focus:ring-blue-400"
          >
            {LAYOUT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {t(opt.labelKey)}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* ── Visual toggles ── */}
      <div className="flex items-center gap-1 border-l border-gray-200 pl-3">
        {/* Labels */}
        {onShowLabelsChange && (
          <button
            onClick={() => onShowLabelsChange(!showLabels)}
            className={`p-1.5 rounded transition-colors text-xs ${showLabels ? 'bg-blue-50 text-blue-600' : 'text-gray-400 hover:bg-gray-50'}`}
            title={t('toggleLabels')}
          >
            {showLabels ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
          </button>
        )}
        {/* Arrows */}
        {onShowArrowsChange && (
          <button
            onClick={() => onShowArrowsChange(!showArrows)}
            className={`p-1.5 rounded transition-colors text-xs ${showArrows ? 'bg-blue-50 text-blue-600' : 'text-gray-400 hover:bg-gray-50'}`}
            title={t('toggleArrows')}
          >
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        )}
        {/* Risk Heat */}
        {onRiskHeatChange && (
          <button
            onClick={() => onRiskHeatChange(!riskHeatEnabled)}
            className={`p-1.5 rounded transition-colors text-xs ${riskHeatEnabled ? 'bg-orange-50 text-orange-600' : 'text-gray-400 hover:bg-gray-50'}`}
            title={t('toggleHeat')}
          >
            <Thermometer className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {/* ── Camera presets ── */}
      {onCameraPreset && (
        <div className="flex items-center gap-1 border-l border-gray-200 pl-3">
          <button onClick={() => onCameraPreset('top')} className="px-1.5 py-1 text-[10px] text-gray-500 hover:bg-gray-100 rounded font-medium" title={t('cameraTop')}>
            {t('cameraTop')}
          </button>
          <button onClick={() => onCameraPreset('front')} className="px-1.5 py-1 text-[10px] text-gray-500 hover:bg-gray-100 rounded font-medium" title={t('cameraFront')}>
            {t('cameraFront')}
          </button>
          <button onClick={() => onCameraPreset('side')} className="px-1.5 py-1 text-[10px] text-gray-500 hover:bg-gray-100 rounded font-medium" title={t('cameraSide')}>
            {t('cameraSide')}
          </button>
          <button onClick={() => onCameraPreset('fit')} className="p-1.5 text-gray-400 hover:bg-gray-100 rounded" title={t('cameraFit')}>
            <Box className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Time range */}
      {onStartTimeChange && onEndTimeChange && (
        <div className="flex items-center gap-2 text-sm border-l border-gray-200 pl-3">
          <label className="text-gray-500 font-medium text-xs">{t('from')}</label>
          <input
            type="datetime-local"
            value={startTime || ''}
            onChange={(e) => onStartTimeChange(e.target.value)}
            className="border border-gray-200 rounded px-2 py-1 text-xs w-44"
          />
          <label className="text-gray-500 font-medium text-xs">{t('to')}</label>
          <input
            type="datetime-local"
            value={endTime || ''}
            onChange={(e) => onEndTimeChange(e.target.value)}
            className="border border-gray-200 rounded px-2 py-1 text-xs w-44"
          />
        </div>
      )}

      {/* Refresh */}
      <button
        onClick={onRefresh}
        disabled={loading}
        className="p-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 disabled:opacity-50 transition-colors"
        title={t('refreshTitle')}
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
          <span>{t('highlightingAlert')}</span>
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

'use client';

import { useState } from 'react';
import { RefreshCw, Crosshair, Eye, EyeOff, ArrowRight, Thermometer, Box, MonitorUp, Layers, Maximize2, Minimize2, Filter, Settings } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { LayoutMode } from './layouts/types';
import type { CameraPreset } from './CameraController';
import type { ViewLevel, EdgeFilterConfig } from './optimization/types';

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
  // ── 布局与视觉 ──
  layoutMode?: LayoutMode;
  onLayoutModeChange?: (mode: LayoutMode) => void;
  showLabels?: boolean;
  onShowLabelsChange?: (v: boolean) => void;
  showArrows?: boolean;
  onShowArrowsChange?: (v: boolean) => void;
  riskHeatEnabled?: boolean;
  onRiskHeatChange?: (v: boolean) => void;
  onCameraPreset?: (preset: CameraPreset) => void;
  // ── 大图优化层 ──
  viewLevel?: ViewLevel;
  onViewLevelChange?: (level: ViewLevel) => void;
  onExpandAll?: () => void;
  onCollapseAll?: () => void;
  edgeFilter?: EdgeFilterConfig;
  onEdgeFilterChange?: (config: Partial<EdgeFilterConfig>) => void;
}

const PRIMARY_LAYOUT_OPTIONS: { value: LayoutMode; labelKey: string }[] = [
  { value: 'clustered-subnet', labelKey: 'layoutCluster' },
  { value: 'force',            labelKey: 'layoutForce'   },
  { value: 'dag',              labelKey: 'layoutDag'     },
];

const ADVANCED_LAYOUT_OPTIONS: { value: LayoutMode; labelKey: string }[] = [
  { value: 'circle', labelKey: 'layoutCircle' },
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
  layoutMode = 'clustered-subnet',
  onLayoutModeChange,
  showLabels = true,
  onShowLabelsChange,
  showArrows = false,
  onShowArrowsChange,
  riskHeatEnabled = false,
  onRiskHeatChange,
  onCameraPreset,
  viewLevel,
  onViewLevelChange,
  onExpandAll,
  onCollapseAll,
  edgeFilter,
  onEdgeFilterChange,
}: TopologyToolbarProps) {
  const t = useTranslations('topology');
  const [showAdvanced, setShowAdvanced] = useState(false);

  return (
    <div className="flex flex-col border-b border-gray-200 bg-white shrink-0">
      {/* ── 主工具栏行 ── */}
      <div className="flex items-center gap-3 px-4 py-2 flex-wrap">
        {/* Mode toggle */}
        <div className="flex rounded-lg border border-gray-200 overflow-hidden text-sm">
          <button
            className={`px-3 py-1.5 font-medium transition-colors ${
              mode === 'ip' ? 'bg-blue-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'
            }`}
            onClick={() => onModeChange('ip')}
          >
            {t('ip')}
          </button>
          <button
            className={`px-3 py-1.5 font-medium transition-colors ${
              mode === 'subnet' ? 'bg-blue-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'
            }`}
            onClick={() => onModeChange('subnet')}
          >
            {t('subnet')}
          </button>
        </div>

        {/* 主视图切换（3 个布局） */}
        {onLayoutModeChange && (
          <div className="flex rounded-lg border border-gray-200 overflow-hidden text-xs">
            {PRIMARY_LAYOUT_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                className={`px-3 py-1.5 font-medium transition-colors ${
                  layoutMode === opt.value
                    ? 'bg-blue-600 text-white'
                    : 'bg-white text-gray-600 hover:bg-gray-50'
                }`}
                onClick={() => onLayoutModeChange(opt.value)}
              >
                {t(opt.labelKey)}
              </button>
            ))}
          </div>
        )}

        {/* 可视化开关：标签 + 热力 */}
        <div className="flex items-center gap-1 border-l border-gray-200 pl-3">
          {onShowLabelsChange && (
            <button
              onClick={() => onShowLabelsChange(!showLabels)}
              className={`p-1.5 rounded transition-colors text-xs ${showLabels ? 'bg-blue-50 text-blue-600' : 'text-gray-400 hover:bg-gray-50'}`}
              title={t('toggleLabels')}
            >
              {showLabels ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
            </button>
          )}
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

        {/* 相机预设：fit + top */}
        {onCameraPreset && (
          <div className="flex items-center gap-1 border-l border-gray-200 pl-3">
            <button
              onClick={() => onCameraPreset('fit')}
              className="p-1.5 text-gray-400 hover:bg-gray-100 rounded"
              title={t('cameraFit')}
            >
              <Box className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => onCameraPreset('top')}
              className="p-1.5 text-gray-400 hover:bg-gray-100 rounded"
              title={t('cameraTop')}
            >
              <MonitorUp className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* 时间范围 */}
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

        {/* 刷新 */}
        <button
          onClick={onRefresh}
          disabled={loading}
          className="p-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 disabled:opacity-50 transition-colors"
          title={t('refreshTitle')}
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>

        {/* 占位间隔 */}
        <div className="flex-grow" />

        {/* 高亮指示 */}
        {highlightAlertId && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-red-50 border border-red-200 text-red-700 text-xs font-medium relative group cursor-default">
            <Crosshair className="w-3.5 h-3.5" />
            <span>{t('highlightingAlert')}</span>
            <span className="font-mono">{highlightAlertId.substring(0, 8)}...</span>
            <div className="absolute top-full right-0 mt-1 px-3 py-1.5 bg-gray-900 text-white text-xs font-mono rounded shadow-lg whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50">
              {highlightAlertId}
            </div>
          </div>
        )}

        {/* 高级分析折叠按钮 */}
        <button
          onClick={() => setShowAdvanced(v => !v)}
          className={`p-1.5 rounded-lg border text-xs transition-colors ${
            showAdvanced
              ? 'bg-blue-50 text-blue-600 border-blue-200'
              : 'border-gray-200 text-gray-500 hover:bg-gray-50'
          }`}
          title={t('advancedAnalysis')}
        >
          <Settings className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* ── 高级分析面板 ── */}
      {showAdvanced && (
        <div className="flex items-center gap-3 px-4 py-2 border-t border-gray-100 bg-gray-50 flex-wrap text-xs">
          {/* circle 布局备用入口 */}
          {onLayoutModeChange && ADVANCED_LAYOUT_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              className={`px-2 py-1 rounded border text-[10px] font-medium transition-colors ${
                layoutMode === opt.value
                  ? 'bg-blue-50 text-blue-600 border-blue-200'
                  : 'border-gray-200 text-gray-500 hover:bg-gray-100'
              }`}
              onClick={() => onLayoutModeChange(opt.value)}
            >
              {t(opt.labelKey)}
            </button>
          ))}

          {/* front / side 相机预设 */}
          {onCameraPreset && (
            <div className="flex items-center gap-1 border-l border-gray-200 pl-3">
              <button
                onClick={() => onCameraPreset('front')}
                className="px-1.5 py-1 text-[10px] text-gray-500 hover:bg-gray-200 rounded font-medium"
                title={t('cameraFront')}
              >
                {t('cameraFront')}
              </button>
              <button
                onClick={() => onCameraPreset('side')}
                className="px-1.5 py-1 text-[10px] text-gray-500 hover:bg-gray-200 rounded font-medium"
                title={t('cameraSide')}
              >
                {t('cameraSide')}
              </button>
            </div>
          )}

          {/* 箭头开关 */}
          {onShowArrowsChange && (
            <button
              onClick={() => onShowArrowsChange(!showArrows)}
              className={`p-1.5 rounded transition-colors border ${showArrows ? 'bg-blue-50 text-blue-600 border-blue-200' : 'text-gray-400 border-gray-200 hover:bg-gray-100'}`}
              title={t('toggleArrows')}
            >
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          )}

          {/* 视图层级切换 */}
          {onViewLevelChange && viewLevel && (
            <div className="flex items-center gap-1 border-l border-gray-200 pl-3">
              <Layers className="w-3.5 h-3.5 text-gray-400" />
              <div className="flex rounded-lg border border-gray-200 overflow-hidden text-[10px]">
                <button
                  className={`px-2 py-1 font-medium transition-colors ${viewLevel === 'subnet' ? 'bg-purple-50 text-purple-600' : 'text-gray-500 hover:bg-gray-100'}`}
                  onClick={() => onViewLevelChange('subnet')}
                >
                  {t('viewLevelSubnet')}
                </button>
                <button
                  className={`px-2 py-1 font-medium transition-colors ${viewLevel === 'host' ? 'bg-purple-50 text-purple-600' : 'text-gray-500 hover:bg-gray-100'}`}
                  onClick={() => onViewLevelChange('host')}
                >
                  {t('viewLevelHost')}
                </button>
              </div>
              {viewLevel === 'subnet' && (
                <>
                  <button onClick={onExpandAll} className="p-1 text-gray-400 hover:bg-gray-200 rounded" title={t('expandAll')}>
                    <Maximize2 className="w-3 h-3" />
                  </button>
                  <button onClick={onCollapseAll} className="p-1 text-gray-400 hover:bg-gray-200 rounded" title={t('collapseAll')}>
                    <Minimize2 className="w-3 h-3" />
                  </button>
                </>
              )}
            </div>
          )}

          {/* 边过滤滑块 */}
          {onEdgeFilterChange && edgeFilter && (
            <div className="flex items-center gap-1.5 border-l border-gray-200 pl-3">
              <Filter className="w-3.5 h-3.5 text-gray-400" />
              <label className="text-[10px] text-gray-500">{t('edgeMinRisk')}</label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={edgeFilter.minRisk}
                onChange={(e) => onEdgeFilterChange({ minRisk: parseFloat(e.target.value) })}
                className="w-14 h-1 accent-blue-500"
                title={`${(edgeFilter.minRisk * 100).toFixed(0)}%`}
              />
              <span className="text-[10px] text-gray-400 w-6">{(edgeFilter.minRisk * 100).toFixed(0)}%</span>
              <label className="text-[10px] text-gray-500">{t('edgeMinWeight')}</label>
              <input
                type="range"
                min="0"
                max="50"
                step="1"
                value={edgeFilter.minWeight}
                onChange={(e) => onEdgeFilterChange({ minWeight: parseInt(e.target.value) })}
                className="w-14 h-1 accent-blue-500"
                title={String(edgeFilter.minWeight)}
              />
              <span className="text-[10px] text-gray-400 w-4">{edgeFilter.minWeight}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

'use client';

import { useState } from 'react';
import { RefreshCw, Crosshair, RotateCcw, Layers, Maximize2, Minimize2, Filter, Settings } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { LayoutMode } from './layouts/types';
import type { CameraPreset } from './CameraController';
import type { ViewLevel, EdgeFilterConfig } from './optimization/types';

// ── 语义视图模式（主切换） ──
export type TopologyViewMode = 'overview' | 'analysis' | 'explain';

// 视图模式 → 布局映射
export const VIEW_MODE_LAYOUT: Record<TopologyViewMode, LayoutMode> = {
  overview: 'clustered-subnet',
  analysis: 'force',
  explain:  'dag',
};

// 视图模式 → 标签/箭头策略
export const VIEW_MODE_LABELS: Record<TopologyViewMode, { showLabels: boolean; showArrows: boolean; riskHeatEnabled: boolean }> = {
  overview: { showLabels: true,  showArrows: false, riskHeatEnabled: false },
  analysis: { showLabels: true,  showArrows: false, riskHeatEnabled: false },
  explain:  { showLabels: true,  showArrows: true,  riskHeatEnabled: false },
};

interface TopologyToolbarProps {
  // 主视图模式
  viewMode: TopologyViewMode;
  onViewModeChange: (mode: TopologyViewMode) => void;
  // 时间范围
  startTime?: string;
  endTime?: string;
  onStartTimeChange?: (value: string) => void;
  onEndTimeChange?: (value: string) => void;
  // 刷新
  onRefresh: () => void;
  loading?: boolean;
  // 相机
  onCameraPreset?: (preset: CameraPreset) => void;
  // 告警高亮指示
  highlightAlertId: string | null;
  // dry-run 状态指示（有值时显示 badge）
  dryRunActive?: boolean;
  // ── 高级面板（优化层） ──
  viewLevel?: ViewLevel;
  onViewLevelChange?: (level: ViewLevel) => void;
  onExpandAll?: () => void;
  onCollapseAll?: () => void;
  edgeFilter?: EdgeFilterConfig;
  onEdgeFilterChange?: (config: Partial<EdgeFilterConfig>) => void;
  // 高级：手动覆盖布局（circle 等）
  layoutMode?: LayoutMode;
  onLayoutModeChange?: (mode: LayoutMode) => void;
}

const VIEW_MODES: { value: TopologyViewMode; labelKey: string; descKey: string }[] = [
  { value: 'overview', labelKey: 'viewOverview', descKey: 'viewOverviewDesc' },
  { value: 'analysis', labelKey: 'viewAnalysis', descKey: 'viewAnalysisDesc' },
  { value: 'explain',  labelKey: 'viewExplain',  descKey: 'viewExplainDesc'  },
];

export default function TopologyToolbar({
  viewMode,
  onViewModeChange,
  startTime,
  endTime,
  onStartTimeChange,
  onEndTimeChange,
  onRefresh,
  loading,
  onCameraPreset,
  highlightAlertId,
  dryRunActive,
  viewLevel,
  onViewLevelChange,
  onExpandAll,
  onCollapseAll,
  edgeFilter,
  onEdgeFilterChange,
  layoutMode,
  onLayoutModeChange,
}: TopologyToolbarProps) {
  const t = useTranslations('topology');
  const [showAdvanced, setShowAdvanced] = useState(false);

  // 当前视图模式对应的布局（用于高级面板中显示当前覆盖状态）
  const defaultLayout = VIEW_MODE_LAYOUT[viewMode];
  const isLayoutOverridden = layoutMode !== undefined && layoutMode !== defaultLayout;

  return (
    <div className="flex flex-col border-b border-gray-200 bg-white shrink-0">
      {/* ── 主工具栏行 ── */}
      <div className="flex items-center gap-3 px-4 py-2 flex-wrap">

        {/* 主视图模式切换 */}
        <div className="flex rounded-lg border border-gray-200 overflow-hidden text-xs">
          {VIEW_MODES.map((opt) => (
            <button
              key={opt.value}
              className={`px-3 py-1.5 font-medium transition-colors ${
                viewMode === opt.value
                  ? 'bg-blue-600 text-white'
                  : 'bg-white text-gray-600 hover:bg-gray-50'
              }`}
              onClick={() => onViewModeChange(opt.value)}
              title={t(opt.descKey)}
            >
              {t(opt.labelKey)}
            </button>
          ))}
        </div>

        {/* 时间范围 */}
        {onStartTimeChange && onEndTimeChange && (
          <div className="flex items-center gap-2 border-l border-gray-200 pl-3">
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

        {/* 适配全图（唯一一级相机入口） */}
        {onCameraPreset && (
          <button
            onClick={() => onCameraPreset('fit')}
            className="p-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 transition-colors"
            title={t('resetView')}
          >
            <RotateCcw className="w-4 h-4" />
          </button>
        )}

        {/* 占位间隔 */}
        <div className="flex-grow" />

        {/* dry-run 状态指示 */}
        {dryRunActive && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-50 border border-amber-200 text-amber-700 text-xs font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
            {t('dryRunActive')}
          </div>
        )}

        {/* 告警高亮指示 */}
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

        {/* 高级分析折叠按钮（有覆盖时高亮提示） */}
        <button
          onClick={() => setShowAdvanced(v => !v)}
          className={`p-1.5 rounded-lg border text-xs transition-colors ${
            showAdvanced || isLayoutOverridden
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

          {/* 布局覆盖（circle + 当前视图模式默认布局标注） */}
          {onLayoutModeChange && (
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-gray-400">{t('layoutOverride')}</span>
              <div className="flex rounded border border-gray-200 overflow-hidden text-[10px]">
                {(['clustered-subnet', 'force', 'dag', 'circle'] as LayoutMode[]).map((l) => {
                  const isDefault = l === defaultLayout;
                  const isActive = (layoutMode ?? defaultLayout) === l;
                  return (
                    <button
                      key={l}
                      className={`px-2 py-1 font-medium transition-colors ${
                        isActive
                          ? 'bg-blue-600 text-white'
                          : 'text-gray-500 hover:bg-gray-100'
                      }`}
                      onClick={() => onLayoutModeChange(l)}
                      title={isDefault ? t('defaultForMode') : undefined}
                    >
                      {l === 'clustered-subnet' ? t('layoutCluster')
                        : l === 'force' ? t('layoutForce')
                        : l === 'dag'   ? t('layoutDag')
                        : t('layoutCircle')}
                      {isDefault && <span className="ml-0.5 opacity-50">*</span>}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* 相机：front / side / top */}
          {onCameraPreset && (
            <div className="flex items-center gap-1 border-l border-gray-200 pl-3">
              <span className="text-[10px] text-gray-400">{t('cameraAngle')}</span>
              {(['top', 'front', 'side'] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => onCameraPreset(p)}
                  className="px-1.5 py-1 text-[10px] text-gray-500 hover:bg-gray-200 rounded font-medium"
                >
                  {t(`camera${p.charAt(0).toUpperCase() + p.slice(1)}` as any)}
                </button>
              ))}
            </div>
          )}

          {/* 视图层级 + 展开/折叠 */}
          {onViewLevelChange && viewLevel && (
            <div className="flex items-center gap-1 border-l border-gray-200 pl-3">
              <Layers className="w-3.5 h-3.5 text-gray-400" />
              <div className="flex rounded border border-gray-200 overflow-hidden text-[10px]">
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
                type="range" min="0" max="1" step="0.05"
                value={edgeFilter.minRisk}
                onChange={(e) => onEdgeFilterChange({ minRisk: parseFloat(e.target.value) })}
                className="w-14 h-1 accent-blue-500"
                title={`${(edgeFilter.minRisk * 100).toFixed(0)}%`}
              />
              <span className="text-[10px] text-gray-400 w-6">{(edgeFilter.minRisk * 100).toFixed(0)}%</span>
              <label className="text-[10px] text-gray-500">{t('edgeMinWeight')}</label>
              <input
                type="range" min="0" max="50" step="1"
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

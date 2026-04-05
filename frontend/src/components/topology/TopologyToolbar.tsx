'use client';

import { RefreshCw, Crosshair, RotateCcw, Layers, Maximize2, Minimize2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { LayoutMode } from './layouts/types';
import type { CameraPreset } from './CameraController';
import type { ViewLevel } from './optimization/types';

interface TopologyToolbarProps {
  // 布局模式
  layoutMode: LayoutMode;
  onLayoutModeChange: (mode: LayoutMode) => void;
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
  // dry-run 状态指示
  dryRunActive?: boolean;
  // 视图层级
  viewLevel?: ViewLevel;
  onViewLevelChange?: (level: ViewLevel) => void;
  onExpandAll?: () => void;
  onCollapseAll?: () => void;
}

const LAYOUTS: { value: LayoutMode; labelKey: string }[] = [
  { value: 'circle', labelKey: 'layoutCircle' },
  { value: 'dag', labelKey: 'layoutDag' },
  { value: 'clustered-subnet', labelKey: 'layoutCluster' },
];

export default function TopologyToolbar({
  layoutMode,
  onLayoutModeChange,
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
}: TopologyToolbarProps) {
  const t = useTranslations('topology');

  return (
    <div className="flex flex-col border-b border-gray-200 bg-white shrink-0">
      <div className="flex items-center gap-3 px-4 py-2 flex-wrap">

        {/* 布局模式切换 */}
        <div className="flex rounded-lg border border-gray-200 overflow-hidden text-xs">
          {LAYOUTS.map((l) => (
            <button
              key={l.value}
              className={`px-3 py-1.5 font-medium transition-colors ${
                layoutMode === l.value
                  ? 'bg-blue-600 text-white'
                  : 'bg-white text-gray-600 hover:bg-gray-50'
              }`}
              onClick={() => onLayoutModeChange(l.value)}
            >
              {t(l.labelKey)}
            </button>
          ))}
        </div>

        {/* 子网/主机切换 + 展开/折叠 */}
        {onViewLevelChange && viewLevel && (
          <div className="flex items-center gap-1 border-l border-gray-200 pl-3">
            <Layers className="w-3.5 h-3.5 text-gray-400" />
            <div className="flex rounded border border-gray-200 overflow-hidden text-xs">
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

        {/* 重置视角 */}
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
      </div>
    </div>
  );
}

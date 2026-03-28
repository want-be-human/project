'use client';

import { X } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { GraphNode, GraphEdge, GraphResponse, DryRunResult } from '@/lib/api/types';
import type { LayoutMode } from '@/components/topology/layouts/types';
import type { DryRunViewMode } from '@/app/(main)/topology/page';
import type { ViewLevel } from '@/components/topology/optimization/types';
import NodePanel from './NodePanel';
import EdgePanel from './EdgePanel';
import GlobalPanel from './GlobalPanel';

export interface SideInspectorProps {
  // 选中状态
  selectedNode: GraphNode | null;
  selectedEdge: GraphEdge | null;

  // 全图数据（用于计算度数、邻居、聚合统计）
  displayGraph: GraphResponse | null;
  // 时间滑块位置
  currentTime: number;
  // 布局与视图模式
  layoutMode: LayoutMode;
  viewMode?: DryRunViewMode;

  // Dry-run 相关
  dryRunResult?: DryRunResult | null;
  removedNodeIds?: Set<string>;
  removedEdgeIds?: Set<string>;
  affectedNodeIds?: Set<string>;
  affectedEdgeIds?: Set<string>;
  originalValues?: { nodeRisks: Record<string, number>; edgeWeights: Record<string, number> };

  // 替代路径
  altPaths?: Array<{ from: string; to: string; path: string[] }>;
  // 告警严重度映射
  alertSeverityMap?: Record<string, 'low' | 'medium' | 'high' | 'critical'>;

  // 大图优化层
  viewLevel?: ViewLevel;
  clusterCount?: number;
  expandedClusterCount?: number;

  // 回调
  onClose: () => void;
  onLocateNode?: (nodeId: string) => void;
  onSelectNode?: (node: GraphNode) => void;
  onSelectEdge?: (edge: GraphEdge) => void;
}

export default function SideInspector({
  selectedNode, selectedEdge, displayGraph, currentTime,
  layoutMode, viewMode, dryRunResult,
  removedNodeIds, removedEdgeIds, affectedNodeIds, affectedEdgeIds,
  originalValues, altPaths, alertSeverityMap,
  viewLevel, clusterCount, expandedClusterCount,
  onClose, onLocateNode, onSelectNode, onSelectEdge,
}: SideInspectorProps) {
  const t = useTranslations('topology');
  const hasSelection = selectedNode || selectedEdge;

  // 面板标题：根据模式切换
  const title = selectedNode
    ? t('inspector_nodeTitle')
    : selectedEdge
      ? t('inspector_edgeTitle')
      : t('inspector_globalOverview');

  return (
    <div className="w-96 border-l border-gray-200 bg-white flex flex-col overflow-hidden">
      {/* 头部 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 shrink-0">
        <h2 className="font-medium text-gray-900 text-sm">{title}</h2>
        {hasSelection && (
          <button onClick={onClose} className="p-1 text-gray-400 hover:text-gray-700">
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* 滚动内容区 */}
      <div className="flex-grow overflow-y-auto p-3">
        {/* 节点研判面板 */}
        {selectedNode && displayGraph && (
          <NodePanel
            node={selectedNode}
            graph={displayGraph}
            dryRunResult={dryRunResult}
            removedNodeIds={removedNodeIds}
            affectedNodeIds={affectedNodeIds}
            originalRisk={originalValues?.nodeRisks[selectedNode.id]}
            alertSeverityMap={alertSeverityMap}
            onLocateNode={onLocateNode}
            onSelectNode={onSelectNode}
          />
        )}

        {/* 边研判面板 */}
        {selectedEdge && displayGraph && (
          <EdgePanel
            edge={selectedEdge}
            graph={displayGraph}
            dryRunResult={dryRunResult}
            removedEdgeIds={removedEdgeIds}
            affectedEdgeIds={affectedEdgeIds}
            originalWeight={originalValues?.edgeWeights[selectedEdge.id]}
            altPaths={altPaths}
            alertSeverityMap={alertSeverityMap}
            onLocateNode={onLocateNode}
          />
        )}

        {/* 全局总览面板（未选中任何对象时） */}
        {!hasSelection && displayGraph && (
          <GlobalPanel
            graph={displayGraph}
            currentTime={currentTime}
            layoutMode={layoutMode}
            viewMode={viewMode}
            dryRunResult={dryRunResult}
            removedNodeIds={removedNodeIds}
            removedEdgeIds={removedEdgeIds}
            affectedNodeIds={affectedNodeIds}
            affectedEdgeIds={affectedEdgeIds}
            alertSeverityMap={alertSeverityMap}
            onSelectNode={onSelectNode}
            onSelectEdge={onSelectEdge}
            viewLevel={viewLevel}
            clusterCount={clusterCount}
            expandedClusterCount={expandedClusterCount}
          />
        )}

        {/* 无图数据时的空状态 */}
        {!displayGraph && (
          <div className="text-sm text-gray-400 text-center py-12">
            {t('inspectorPrompt')}
          </div>
        )}
      </div>
    </div>
  );
}

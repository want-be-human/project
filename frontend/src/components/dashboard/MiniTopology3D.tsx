'use client';

import { useRef, useEffect, useMemo, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import dynamic from 'next/dynamic';
import type { TopologySnapshot } from '@/lib/api/types';
import type { ForceGraphMethods } from 'react-force-graph-3d';

/**
 * 风险等级颜色映射函数
 * - risk < 0.4 → 绿色（低风险）
 * - 0.4 ≤ risk < 0.7 → 黄色（中风险）
 * - risk ≥ 0.7 → 红色（高风险）
 *
 * 导出以便属性测试使用
 */
export function getRiskColor(risk: number): string {
  if (risk < 0.4) return '#22c55e';
  if (risk < 0.7) return '#eab308';
  return '#ef4444';
}

/**
 * 根据风险值计算节点大小
 * 高风险节点（risk >= 0.7）额外放大以增强视觉突出度
 */
function getNodeSize(risk: number): number {
  if (risk >= 0.7) return 4 + risk * 8 + 6;
  return 4 + risk * 8;
}

/** 图节点类型 */
interface GraphNode {
  id: string;
  label: string;
  risk: number;
}

/** 图边类型 */
interface GraphLink {
  source: string;
  target: string;
  risk: number;
}

interface MiniTopology3DProps {
  snapshot: TopologySnapshot;
}

// 使用 dynamic import 加载 ForceGraph3D，禁用 SSR
// react-force-graph-3d 依赖浏览器 API（WebGL/Canvas），无法在服务端渲染
const ForceGraph3D = dynamic(() => import('react-force-graph-3d'), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-full text-gray-500 text-sm">
      加载 3D 拓扑中...
    </div>
  ),
});

/**
 * 迷你 3D 拓扑组件
 * 基于 Dashboard API 返回的 topology_snapshot 数据渲染 3D 力导向图
 * 支持自动旋转、悬停高亮、点击导航至完整拓扑页
 */
export default function MiniTopology3D({ snapshot }: MiniTopology3DProps) {
  const t = useTranslations('dashboard');
  const router = useRouter();
  const graphRef = useRef<ForceGraphMethods | undefined>(undefined);

  // 从 snapshot 构建图数据
  const graphData = useMemo(() => {
    const nodes: GraphNode[] = (snapshot.top_risk_nodes ?? []).map((n) => ({
      id: n.id,
      label: n.label,
      risk: n.risk,
    }));

    const nodeIds = new Set(nodes.map((n) => n.id));

    // 只保留两端节点都存在的边
    const links: GraphLink[] = (snapshot.top_risk_edges ?? [])
      .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
      .map((e) => ({
        source: e.source,
        target: e.target,
        risk: e.risk,
      }));

    return { nodes, links };
  }, [snapshot]);

  // 自动旋转：通过 requestAnimationFrame 控制相机轨道旋转
  useEffect(() => {
    const fg = graphRef.current;
    if (!fg) return;

    let angle = 0;
    let frameId: number;
    const distance = 200;

    const rotate = () => {
      angle += 0.002;
      const x = distance * Math.sin(angle);
      const z = distance * Math.cos(angle);
      fg.cameraPosition({ x, y: 60, z });
      frameId = requestAnimationFrame(rotate);
    };

    // 等待力导向图稳定后开始旋转
    const timer = setTimeout(() => {
      frameId = requestAnimationFrame(rotate);
    }, 1500);

    return () => {
      clearTimeout(timer);
      if (frameId) cancelAnimationFrame(frameId);
    };
  }, [graphData]);

  // 点击导航至完整拓扑页
  const handleClick = useCallback(() => {
    router.push('/topology');
  }, [router]);

  // 节点标签：悬停时显示节点信息
  const nodeLabel = useCallback(
    (node: GraphNode) =>
      `<div style="background:rgba(0,0,0,0.8);padding:4px 8px;border-radius:4px;color:#fff;font-size:12px;">
        <b>${node.label}</b><br/>
        Risk: ${(node.risk * 100).toFixed(0)}%
      </div>`,
    [],
  );

  // 无数据时显示提示
  const hasData = graphData.nodes.length > 0;

  // 检查是否存在高风险节点，用于容器发光效果
  const hasHighRiskNodes = graphData.nodes.some((n) => n.risk >= 0.7);

  return (
    <div className="bg-gray-900/80 border border-gray-700/50 rounded-xl p-4 backdrop-blur-sm">
      {/* 标题栏 */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-white">{t('topoTitle')}</h3>
        <button
          onClick={handleClick}
          className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors"
        >
          {t('topoViewFull')} →
        </button>
      </div>

      {/* 图例 */}
      <div className="flex items-center gap-3 mb-2 text-xs text-gray-400">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-red-500" />
          {t('topoRiskHigh')}
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-yellow-500" />
          {t('topoRiskMedium')}
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-green-500" />
          {t('topoRiskLow')}
        </span>
        <span className="ml-auto text-gray-500">
          {t('topoNodes')}: {snapshot.node_count} | {t('topoEdges')}: {snapshot.edge_count}
        </span>
      </div>

      {/* 3D 图或无数据提示，存在高风险节点时添加呼吸发光边框 */}
      <div className={`h-[280px] rounded-lg overflow-hidden bg-gray-950/50${hasHighRiskNodes ? ' animate-breathe-glow-box' : ''}`}>
        {hasData ? (
          <ForceGraph3D
            ref={graphRef as React.MutableRefObject<ForceGraphMethods | undefined>}
            graphData={graphData}
            width={undefined}
            height={280}
            backgroundColor="rgba(0,0,0,0)"
            showNavInfo={false}
            enableNavigationControls={false}
            enableNodeDrag={false}
            nodeVal={(node: any) => getNodeSize(node.risk)}
            nodeColor={(node: any) => getRiskColor(node.risk)}
            nodeLabel={(node: any) => nodeLabel(node)}
            nodeOpacity={0.9}
            linkColor={() => 'rgba(100,116,139,0.4)'}
            linkWidth={(link: any) => link.risk >= 0.7 ? 1.5 : 0.5}
            /* 边脉冲流动粒子动效：高风险边粒子更多、颜色为红色 */
            linkDirectionalParticles={(link: any) => link.risk >= 0.7 ? 3 : 1}
            linkDirectionalParticleSpeed={0.004}
            linkDirectionalParticleWidth={1.5}
            linkDirectionalParticleColor={(link: any) => link.risk >= 0.7 ? '#ef4444' : '#06b6d4'}
            onNodeClick={handleClick as any}
            onBackgroundClick={handleClick}
            warmupTicks={50}
            cooldownTicks={0}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-gray-500 text-sm">
            {t('noData')}
          </div>
        )}
      </div>
    </div>
  );
}

'use client';

import { useRef, useEffect, useMemo, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import dynamic from 'next/dynamic';
import type { TopologySnapshot } from '@/lib/api/types';
import type { ForceGraphMethods } from 'react-force-graph-3d';
import { useContainerSize } from './useContainerSize';

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

/** 目标旋转速度（弧度/帧） */
export const TARGET_SPEED = 0.002;

/** 旋转速度渐入期时长（毫秒） */
export const RAMP_DURATION = 1000;

/**
 * 计算旋转速度（导出以便属性测试使用）
 * 在渐入期内速度从 0 线性增加到 TARGET_SPEED
 * @param elapsed 自旋转开始以来经过的毫秒数
 * @returns 当前旋转速度（弧度/帧）
 */
export function computeRotationSpeed(elapsed: number): number {
  const speedFactor = Math.min(Math.max(elapsed / RAMP_DURATION, 0), 1);
  return TARGET_SPEED * speedFactor;
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

/** 旋转状态：等待初始化 | 正在旋转 | resize 暂停中 */
type RotationState = 'waiting' | 'rotating' | 'paused';

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
 *
 * 使用"尺寸驱动的重新居中"方案：
 * - ResizeObserver 追踪容器真实尺寸
 * - 容器尺寸变化时自动 zoomToFit + 重算旋转半径
 * - resize 期间暂停旋转，fit 完成后恢复
 */
export default function MiniTopology3D({ snapshot }: MiniTopology3DProps) {
  const t = useTranslations('dashboard');
  const router = useRouter();
  const graphRef = useRef<ForceGraphMethods | undefined>(undefined);

  // ── 容器尺寸追踪（防抖 200ms） ──
  const { containerRef, width: containerWidth, height: containerHeight } = useContainerSize(200);

  // ── 旋转相关 refs（多个 effect 共享，避免闭包过期） ──
  const orbitDistanceRef = useRef(120);                           // 旋转轨道半径
  const rotationStateRef = useRef<RotationState>('waiting');      // 旋转状态机
  const rotateStartTimeRef = useRef(0);                           // 旋转开始时间戳
  const angleRef = useRef(0);                                     // 当前旋转角度
  const frameIdRef = useRef<number>(0);                           // requestAnimationFrame ID
  const initialFitDoneRef = useRef(false);                        // 首次 zoomToFit 是否完成
  const prefersReducedMotionRef = useRef(false);                  // 用户是否偏好减少动画

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

  // ── 旋转函数（稳定引用，全部通过 ref 读取可变状态） ──
  const rotate = useCallback(() => {
    const fg = graphRef.current;
    if (!fg || rotationStateRef.current !== 'rotating') return;

    const elapsed = Date.now() - rotateStartTimeRef.current;
    const currentSpeed = computeRotationSpeed(elapsed);

    angleRef.current += currentSpeed;
    const x = orbitDistanceRef.current * Math.sin(angleRef.current);
    const z = orbitDistanceRef.current * Math.cos(angleRef.current);
    fg.cameraPosition({ x, y: 30, z });
    frameIdRef.current = requestAnimationFrame(rotate);
  }, []);

  // ── 从 ForceGraph3D 读取当前相机水平距离的工具函数 ──
  const readOrbitDistance = useCallback(() => {
    const fg = graphRef.current;
    if (!fg) return 120;
    // cameraPosition 无参数调用为 getter，类型定义要求参数，使用断言绕过
    const pos = (fg.cameraPosition as unknown as () => { x: number; y: number; z: number })();
    return Math.sqrt(pos.x * pos.x + pos.z * pos.z) || 120;
  }, []);

  // ── Effect A：初始稳定 + 首次 zoomToFit + 开始旋转 ──
  // 依赖 graphData：当图数据变化时重新走初始化流程
  useEffect(() => {
    const fg = graphRef.current;
    if (!fg) return;

    // 重置状态（graphData 变化时重新初始化）
    initialFitDoneRef.current = false;
    rotationStateRef.current = 'waiting';
    if (frameIdRef.current) {
      cancelAnimationFrame(frameIdRef.current);
      frameIdRef.current = 0;
    }

    // 检测用户是否偏好减少动画
    prefersReducedMotionRef.current =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // 等待力导向图稳定后，先 zoomToFit 居中，再开始旋转
    const stabilizeTimer = setTimeout(() => {
      fg.zoomToFit(400, 40);

      // zoomToFit 动画完成后（400ms + 100ms 余量）获取相机距离
      const postFitTimer = setTimeout(() => {
        orbitDistanceRef.current = readOrbitDistance();
        initialFitDoneRef.current = true;

        // 若用户不偏好减少动画，启动自动旋转
        if (!prefersReducedMotionRef.current) {
          rotateStartTimeRef.current = Date.now();
          rotationStateRef.current = 'rotating';
          frameIdRef.current = requestAnimationFrame(rotate);
        }
      }, 500);

      // 将内层 timer 加入清理
      timerRefs.push(postFitTimer);
    }, 1500);

    // 收集所有需要清理的 timer
    const timerRefs: ReturnType<typeof setTimeout>[] = [stabilizeTimer];

    return () => {
      timerRefs.forEach((t) => clearTimeout(t));
      if (frameIdRef.current) {
        cancelAnimationFrame(frameIdRef.current);
        frameIdRef.current = 0;
      }
    };
  }, [graphData, rotate, readOrbitDistance]);

  // ── Effect B：容器尺寸变化时重新居中 ──
  // 依赖 containerWidth/containerHeight：防抖后的真实尺寸
  useEffect(() => {
    const fg = graphRef.current;

    // 守卫：尺寸未测量、图未挂载、首次 fit 未完成 → 跳过
    if (!fg || containerWidth === 0 || containerHeight === 0) return;
    if (!initialFitDoneRef.current) return;

    // 1. 若正在旋转 → 暂停
    const wasRotating = rotationStateRef.current === 'rotating';
    if (wasRotating) {
      rotationStateRef.current = 'paused';
      if (frameIdRef.current) {
        cancelAnimationFrame(frameIdRef.current);
        frameIdRef.current = 0;
      }
    }

    // 2. 重新 zoomToFit，padding 随容器较小维度自适应
    const padding = Math.min(60, Math.max(20, Math.min(containerWidth, containerHeight) * 0.05));
    fg.zoomToFit(400, padding);

    // 3. zoomToFit 动画完成后（500ms）重算旋转半径并恢复旋转
    const resumeTimer = setTimeout(() => {
      orbitDistanceRef.current = readOrbitDistance();

      // 仅在之前正在旋转时才恢复（保持速度连续性，不重置 rotateStartTime）
      if (wasRotating) {
        rotationStateRef.current = 'rotating';
        frameIdRef.current = requestAnimationFrame(rotate);
      }
    }, 500);

    return () => clearTimeout(resumeTimer);
  }, [containerWidth, containerHeight, rotate, readOrbitDistance]);

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

  // ── 计算传递给 ForceGraph3D 的显式尺寸 ──
  // 首帧（0x0）传 undefined → ForceGraph3D 用自身默认尺寸
  // 测量完成后传真实像素值 → 触发 renderer.setSize() 更新画布
  const fgWidth = containerWidth > 0 ? containerWidth : undefined;
  const fgHeight = containerHeight > 0 ? containerHeight : undefined;

  // min-h-0：允许拓扑卡片被 Grid 行高约束，防止 min-h-[200px] 撑高整行
  return (
    <div className="bg-gray-900/80 border border-gray-700/50 rounded-2xl p-4 backdrop-blur-sm h-full flex flex-col min-h-0">
      {/* 标题栏 */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-200">{t('topoTitle')}</h3>
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
          {t('topoNodes')}: {snapshot.node_count} | {t('topoEdges')}: {snapshot.edge_count} | {t('topoHighRisk')}: {graphData.nodes.filter((n) => n.risk >= 0.7).length}
        </span>
      </div>

      {/* 3D 图或无数据提示，存在高风险节点时添加呼吸发光边框 */}
      {/* ref={containerRef}：ResizeObserver 追踪此容器的真实尺寸 */}
      <div
        ref={containerRef}
        className={`flex-1 min-h-[200px] rounded-lg overflow-hidden bg-gray-950/50${hasHighRiskNodes ? ' animate-breathe-glow-box' : ''}`}
      >
        {hasData ? (
          <ForceGraph3D
            ref={graphRef as React.MutableRefObject<ForceGraphMethods | undefined>}
            graphData={graphData}
            width={fgWidth}
            height={fgHeight}
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
            linkDirectionalParticleColor={(link: any) => link.risk >= 0.7 ? '#c172721a' : '#06b6d4'}
            onNodeClick={handleClick as any}
            onBackgroundClick={handleClick}
            warmupTicks={50}
            cooldownTicks={0}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-gray-500 text-sm">
            {t('emptyTopology')}
          </div>
        )}
      </div>
    </div>
  );
}

'use client';

import { useRef, useMemo, useState, useEffect } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls, Text, Line } from '@react-three/drei';
import * as THREE from 'three';
import { GraphNode, GraphEdge } from '@/lib/api/types';
import CanvasErrorBoundary from './CanvasErrorBoundary';
import { computeLayout, type LayoutMode, type LayoutResult } from './layouts';
import ArrowHead from './ArrowHead';
import RiskHeatDisk from './RiskHeatDisk';
import CameraController, { type CameraPreset } from './CameraController';
import {
  useOptimization,
  computeBoundingBox,
  computeCameraLimits,
  computeGridParams,
  computeNodeLOD,
  shouldShowLabel,
  type OptimizedNode,
  type OptimizedEdge,
  type NodeLOD,
  type CameraLimits,
  type GridParams,
} from './optimization';

// ── 类型定义 ──
export interface Topology3DProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  currentTime: number;       // Unix 毫秒时间戳
  highlightAlertId?: string | null;
  // 三类影响集合（替代旧的 impactedNodeIds / impactedEdgeIds）
  removedNodeIds?: Set<string>;
  removedEdgeIds?: Set<string>;
  affectedNodeIds?: Set<string>;
  affectedEdgeIds?: Set<string>;
  altPathNodeIds?: Set<string>;
  layoutMode?: LayoutMode;
  topologyViewMode?: 'overview' | 'analysis' | 'explain';
  showLabels?: boolean;
  showArrows?: boolean;
  riskHeatEnabled?: boolean;
  cameraPreset?: CameraPreset;
  onCameraPresetDone?: () => void;
  focusNodeId?: string | null;
  onFocusDone?: () => void;
  altPaths?: Array<{ from: string; to: string; path: string[] }>;
  onSelectNode?: (node: GraphNode | null) => void;
  onSelectEdge?: (edge: GraphEdge | null) => void;
}

// ── 动画位置包装：在旧坐标与新坐标之间做线性插值 ──
function AnimatedGroup({
  targetPosition,
  children,
}: {
  targetPosition: [number, number, number];
  children: React.ReactNode;
}) {
  const ref = useRef<THREE.Group>(null);
  const current = useRef(new THREE.Vector3(...targetPosition));

  useEffect(() => {
    // 首次挂载时直接吸附到目标坐标
    current.current.set(...targetPosition);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useFrame((_, delta) => {
    if (!ref.current) return;
    const target = new THREE.Vector3(...targetPosition);
    current.current.lerp(target, Math.min(1, 6 * delta));
    ref.current.position.copy(current.current);
  });

  return <group ref={ref}>{children}</group>;
}

// ── 脉冲环（可配色） ──
function PulsingRing({ color }: { color: string }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (ref.current) {
      const s = 1 + Math.sin(clock.getElapsedTime() * 3) * 0.15;
      ref.current.scale.set(s, s, s);
    }
  });
  return (
    <mesh ref={ref} rotation={[Math.PI / 2, 0, 0]}>
      <ringGeometry args={[0.85, 1.05, 32]} />
      <meshBasicMaterial color={color} side={THREE.DoubleSide} transparent opacity={0.7} />
    </mesh>
  );
}

// ── 告警高亮节点的呼吸脉冲 ──
function BreathingPulse() {
  const ref = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (!ref.current) return;
    const t = clock.getElapsedTime();
    const s = 1.1 + Math.sin(t * 2) * 0.2;
    ref.current.scale.set(s, s, s);
    (ref.current.material as THREE.MeshBasicMaterial).opacity =
      0.25 + Math.sin(t * 2) * 0.15;
  });
  return (
    <mesh ref={ref} rotation={[Math.PI / 2, 0, 0]}>
      <ringGeometry args={[0.7, 1.2, 32]} />
      <meshBasicMaterial color="#ef4444" side={THREE.DoubleSide} transparent opacity={0.3} depthWrite={false} />
    </mesh>
  );
}

// ── 节点球体（支持 removed / affected / altPath 三类视觉语义 + LOD） ──
function NodeSphere({
  node,
  position,
  highlighted,
  removed,
  affected,
  altPath,
  selected,
  dimmed,
  showLabel,
  riskHeatEnabled,
  lodLevel,
  onClick,
}: {
  node: GraphNode;
  position: [number, number, number];
  highlighted: boolean;
  removed: boolean;     // 被移除：红色半透明
  affected: boolean;    // 受波及：橙色脉冲
  altPath: boolean;     // 替代路径：绿色
  selected: boolean;
  dimmed: boolean;
  showLabel: boolean;
  riskHeatEnabled: boolean;
  lodLevel: NodeLOD;
  onClick: () => void;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const [hovered, setHovered] = useState(false);

  const color = useMemo(() => {
    if (highlighted) return '#ef4444';
    if (removed) return '#dc2626';      // 红色：被移除
    if (affected) return '#f59e0b';     // 橙色：受波及
    if (altPath) return '#22c55e';      // 绿色：替代路径
    if (node.type === 'cluster') return '#a78bfa';  // 紫色：聚合簇节点
    if (node.type === 'gateway' || node.type === 'router') return '#22c55e';
    if (node.type === 'subnet') return '#8b5cf6';
    if (node.type === 'server') return '#06b6d4';
    if (node.risk >= 0.7) return '#f97316';
    if (node.risk >= 0.4) return '#eab308';
    if (node.risk >= 0.2) return '#3b82f6';
    return '#6ee7b7';
  }, [node, highlighted, removed, affected, altPath]);

  // 基于状态的自发光
  const emissiveColor = highlighted
    ? '#ef4444'
    : removed
      ? '#dc2626'
      : affected
        ? '#f59e0b'
        : riskHeatEnabled && node.risk >= 0.4
          ? color
          : '#000000';
  const emissiveVal = highlighted
    ? 0.4
    : removed
      ? 0.2
      : affected
        ? 0.3
        : riskHeatEnabled
          ? node.risk * 0.5
          : 0;

  // 被移除节点：缩小 + 半透明；簇节点：放大
  const isCluster = node.type === 'cluster';
  const clusterScale = isCluster ? 1.6 : 1;
  const scale = (removed ? 0.7 : selected ? 1.4 : hovered ? 1.2 : 1) * clusterScale;
  const opacity = removed ? 0.3 : dimmed ? 0.25 : isCluster ? 0.7 : 0.9;

  // dot 级别：极小球体，无任何装饰
  if (lodLevel === 'dot') {
    return (
      <AnimatedGroup targetPosition={position}>
        <mesh onClick={(e) => { e.stopPropagation(); onClick(); }}>
          <sphereGeometry args={[0.15, 4, 4]} />
          <meshBasicMaterial color={color} transparent opacity={dimmed ? 0.15 : 0.6} />
        </mesh>
      </AnimatedGroup>
    );
  }

  // LOD 控制：标签显示策略
  // - cluster 节点：medium+ 始终显示（总览必要信息）
  // - 高风险节点（≥0.7）：medium+ 显示（风险优先）
  // - 普通节点：仅 full LOD 显示，且需要 showLabel 全局开关
  const showLabelByLOD = isCluster
    ? (lodLevel === 'full' || lodLevel === 'medium')
    : node.risk >= 0.7
      ? (lodLevel === 'full' || lodLevel === 'medium')
      : showLabel && lodLevel === 'full';
  const showEffects = lodLevel === 'full';

  return (
    <AnimatedGroup targetPosition={position}>
      <mesh
        ref={meshRef}
        onClick={(e) => { e.stopPropagation(); onClick(); }}
        onPointerOver={() => setHovered(true)}
        onPointerOut={() => setHovered(false)}
        scale={scale}
      >
        <sphereGeometry args={[0.5 + node.risk * 0.4, isCluster ? 12 : 16, isCluster ? 12 : 16]} />
        <meshStandardMaterial
          color={color}
          emissive={emissiveColor}
          emissiveIntensity={emissiveVal}
          transparent
          opacity={opacity}
          wireframe={isCluster}
        />
      </mesh>
      {/* 簇节点：额外半透明内球 */}
      {isCluster && (
        <mesh scale={scale * 0.85}>
          <sphereGeometry args={[0.5 + node.risk * 0.4, 12, 12]} />
          <meshStandardMaterial color={color} transparent opacity={0.3} />
        </mesh>
      )}
      {/* 选中环 */}
      {selected && (
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.9, 1.1, 32]} />
          <meshBasicMaterial color="#ffffff" side={THREE.DoubleSide} />
        </mesh>
      )}
      {/* 被移除节点：红色脉冲环 */}
      {showEffects && removed && !selected && <PulsingRing color="#dc2626" />}
      {/* 受波及节点：橙色脉冲环 */}
      {showEffects && affected && !removed && !selected && <PulsingRing color="#f59e0b" />}
      {/* 告警高亮呼吸脉冲 */}
      {showEffects && highlighted && <BreathingPulse />}
      {/* 风险热力圆盘 */}
      {showEffects && riskHeatEnabled && <RiskHeatDisk risk={node.risk} />}
      {/* 标签 */}
      {showLabelByLOD && (
        <Text
          position={[0, 1.2, 0]}
          fontSize={0.4}
          color={removed ? '#dc2626' : '#374151'}
          anchorX="center"
          anchorY="bottom"
        >
          {node.label}
        </Text>
      )}
    </AnimatedGroup>
  );
}

// ── Dry-run 影响边的动画虚线（流动虚线） ──
function FlowingDashLine({
  from,
  to,
  color,
  lineWidth,
}: {
  from: [number, number, number];
  to: [number, number, number];
  color: string;
  lineWidth: number;
}) {
  return (
    <Line
      points={[from, to]}
      color={color}
      lineWidth={lineWidth}
      transparent
      opacity={0.5}
      dashed
      dashSize={0.3}
      gapSize={0.15}
      frustumCulled={false}
    />
  );
}

// ── 边线（支持 removed / affected 两类视觉语义） ──
function EdgeLine({
  edge,
  from,
  to,
  active,
  highlighted,
  removed,
  affected,
  dimmed,
  showArrow,
  onClick,
}: {
  edge: GraphEdge;
  from: [number, number, number];
  to: [number, number, number];
  active: boolean;
  highlighted: boolean;
  removed: boolean;     // 被移除：红色静态虚线
  affected: boolean;    // 受波及：橙色流动虚线
  dimmed: boolean;
  showArrow: boolean;
  onClick: () => void;
}) {
  const [hovered, setHovered] = useState(false);

  const color = useMemo(() => {
    if (highlighted) return '#ef4444';
    if (removed) return '#dc2626';      // 红色
    if (affected) return '#f59e0b';     // 橙色
    if ((edge.alert_ids ?? []).length > 0) return '#f97316';
    return '#9ca3af';
  }, [edge, highlighted, removed, affected]);

  const baseOpacity = removed
    ? 0.2
    : active
      ? (highlighted ? 1 : affected ? 0.5 : 0.8)
      : 0.08;
  const opacity = dimmed ? baseOpacity * 0.2 : baseOpacity;
  const lineWidth = highlighted ? 3 : (removed || affected) ? 2.5 : hovered ? 2.5 : active ? 1.5 : 0.5;

  const { position: cylPos, rotation: cylRot, length } = useMemo(() => {
    const a = new THREE.Vector3(...from);
    const b = new THREE.Vector3(...to);
    const dir = new THREE.Vector3().subVectors(b, a);
    const len = dir.length();
    const mid = new THREE.Vector3().addVectors(a, b).multiplyScalar(0.5);
    const up = new THREE.Vector3(0, 1, 0);
    const quat = new THREE.Quaternion().setFromUnitVectors(up, dir.clone().normalize());
    const euler = new THREE.Euler().setFromQuaternion(quat);
    return { position: mid.toArray() as [number, number, number], rotation: euler, length: len };
  }, [from, to]);

  const mid: [number, number, number] = [
    (from[0] + to[0]) / 2,
    (from[1] + to[1]) / 2,
    (from[2] + to[2]) / 2,
  ];

  return (
    <group>
      {/* 被移除边：红色静态虚线 */}
      {removed ? (
        <Line
          points={[from, to]}
          color={color}
          lineWidth={1.5}
          transparent
          opacity={0.2}
          dashed
          dashSize={0.2}
          gapSize={0.2}
          frustumCulled={false}
        />
      ) : affected ? (
        /* 受波及边：橙色流动虚线 */
        <FlowingDashLine from={from} to={to} color={color} lineWidth={lineWidth} />
      ) : (
        /* 普通边：实线 */
        <Line
          points={[from, to]}
          color={color}
          lineWidth={lineWidth}
          transparent
          opacity={opacity}
          frustumCulled={false}
        />
      )}
      {/* 箭头头部 */}
      {showArrow && active && !removed && <ArrowHead from={from} to={to} color={color} opacity={opacity} />}
      {/* 用于点击检测的不可见圆柱 */}
      <mesh
        position={cylPos}
        rotation={cylRot}
        onClick={(e) => { e.stopPropagation(); onClick(); }}
        onPointerOver={() => setHovered(true)}
        onPointerOut={() => setHovered(false)}
      >
        <cylinderGeometry args={[0.15, 0.15, length, 6]} />
        <meshBasicMaterial transparent opacity={0} />
      </mesh>
      {/* 状态标签 */}
      {active && removed && (
        <Text position={[mid[0], mid[1] + 0.5, mid[2]]} fontSize={0.3} color="#dc2626">
          ✕ 已移除
        </Text>
      )}
      {active && affected && !removed && (
        <Text position={[mid[0], mid[1] + 0.5, mid[2]]} fontSize={0.3} color="#f59e0b">
          ⚠ 受波及
        </Text>
      )}
      {active && highlighted && !removed && !affected && (
        <Text position={[mid[0], mid[1] + 0.5, mid[2]]} fontSize={0.3} color="#ef4444">
          {`${(edge.protocols ?? []).join(',')} w=${edge.weight}`}
        </Text>
      )}
    </group>
  );
}

// ── Dry-run 的替代路径线（绿色虚线） ──
function AltPathLines({
  altPaths,
  positions,
}: {
  altPaths: Array<{ from: string; to: string; path: string[] }>;
  positions: LayoutResult;
}) {
  return (
    <>
      {altPaths.map((ap, ai) => {
        const pathNodes = ap.path;
        return pathNodes.slice(0, -1).map((nodeId, si) => {
          const next = pathNodes[si + 1];
          const from = positions[nodeId];
          const to = positions[next];
          if (!from || !to) return null;
          // 略微上移，避免与真实边出现 Z-fighting
          const f: [number, number, number] = [from[0], from[1] + 0.3, from[2]];
          const t: [number, number, number] = [to[0], to[1] + 0.3, to[2]];
          return (
            <Line
              key={`alt-${ai}-${si}`}
              points={[f, t]}
              color="#22c55e"
              lineWidth={2}
              transparent
              opacity={0.6}
              dashed
              dashSize={0.25}
              gapSize={0.15}
              frustumCulled={false}
            />
          );
        });
      })}
    </>
  );
}

// ── 场景 ──
function Scene({
  nodes,
  edges,
  currentTime,
  highlightAlertId,
  removedNodeIds,
  removedEdgeIds,
  affectedNodeIds,
  affectedEdgeIds,
  altPathNodeIds,
  layoutMode = 'circle',
  topologyViewMode = 'overview',
  showLabels = true,
  showArrows = false,
  riskHeatEnabled = false,
  cameraPreset,
  onCameraPresetDone,
  focusNodeId,
  onFocusDone,
  onSelectNode,
  onSelectEdge,
  altPaths,
}: Topology3DProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const { camera } = useThree();

  // 消费优化层
  const { optimizedGraph, toggleCluster, setCameraDistance } = useOptimization();

  // 使用优化后的节点/边（如果可用），否则回退到原始数据
  const displayNodes = optimizedGraph?.nodes ?? nodes;
  const displayEdges = (optimizedGraph?.edges ?? edges) as (GraphEdge & { visibility?: string; isMerged?: boolean })[];

  const positions = useMemo(
    () => computeLayout(layoutMode, { nodes: displayNodes, edges: displayEdges }),
    [displayNodes, displayEdges, layoutMode],
  );

  // 基于布局坐标计算包围盒、相机限制、网格参数
  const boundingBox = useMemo(() => computeBoundingBox(positions), [positions]);
  const cameraLimits = useMemo(
    () => computeCameraLimits(boundingBox, { viewMode: topologyViewMode }),
    [boundingBox, topologyViewMode],
  );
  const gridParams = useMemo(() => computeGridParams(boundingBox), [boundingBox]);

  // 每帧回报相机距离（节流：每 3 帧一次）
  const frameCounter = useRef(0);
  useFrame(() => {
    frameCounter.current++;
    if (frameCounter.current % 3 !== 0) return;
    const dist = camera.position.distanceTo(new THREE.Vector3(...boundingBox.center));
    setCameraDistance(dist);
  });

  // 计算每个节点的 LOD
  const nodeLODs = useMemo(() => {
    const camPos = camera.position.toArray() as [number, number, number];
    const totalVisible = displayNodes.length;
    const lods = new Map<string, NodeLOD>();
    for (const node of displayNodes) {
      const pos = positions[node.id];
      if (!pos) { lods.set(node.id, 'hidden'); continue; }
      const isCluster = (node as OptimizedNode).cluster?.isCluster ?? false;
      lods.set(node.id, computeNodeLOD(pos, camPos, totalVisible, isCluster));
    }
    return lods;
  }, [displayNodes, positions, camera.position.x, camera.position.y, camera.position.z]);

  // 决定哪些边显示箭头
  const arrowEdgeIds = useMemo(() => {
    // DAG 模式：默认全部显示箭头
    if (layoutMode === 'dag' || showArrows) return null; // null = 全部显示
    // 选中节点时，仅显示其相关边的箭头
    if (selectedNodeId) {
      return new Set(
        displayEdges
          .filter(e => e.source === selectedNodeId || e.target === selectedNodeId)
          .map(e => e.id),
      );
    }
    // 选中边时，仅显示该边箭头
    if (selectedEdgeId) return new Set([selectedEdgeId]);
    return new Set<string>(); // 空集 = 不显示箭头
  }, [layoutMode, showArrows, selectedNodeId, selectedEdgeId, displayEdges]);

  const shouldShowArrow = (edgeId: string) =>
    arrowEdgeIds === null || arrowEdgeIds.has(edgeId);

  const highlightedEdgeIds = useMemo(() => {
    if (!highlightAlertId) return new Set<string>();
    return new Set(
      displayEdges.filter(e => (e.alert_ids ?? []).includes(highlightAlertId)).map(e => e.id),
    );
  }, [displayEdges, highlightAlertId]);

  const highlightedNodeIds = useMemo(() => {
    if (!highlightAlertId) return new Set<string>();
    const nodeIds = new Set<string>();
    displayEdges.forEach(e => {
      if ((e.alert_ids ?? []).includes(highlightAlertId)) {
        nodeIds.add(e.source);
        nodeIds.add(e.target);
      }
    });
    return nodeIds;
  }, [displayEdges, highlightAlertId]);

  // 变暗策略：有选中项时，弱化无关元素
  const hasSelection = selectedNodeId !== null || selectedEdgeId !== null;

  const isNodeDimmed = (nodeId: string) => {
    if (!hasSelection) return false;
    if (selectedNodeId === nodeId) return false;
    if (selectedEdgeId) {
      const edge = displayEdges.find(e => e.id === selectedEdgeId);
      if (edge && (edge.source === nodeId || edge.target === nodeId)) return false;
    }
    if (selectedNodeId) {
      // 直接邻居不做变暗
      const isNeighbour = displayEdges.some(
        e =>
          (e.source === selectedNodeId && e.target === nodeId) ||
          (e.target === selectedNodeId && e.source === nodeId),
      );
      if (isNeighbour) return false;
    }
    return true;
  };

  const isEdgeDimmed = (edge: GraphEdge) => {
    if (!hasSelection) return false;
    if (selectedEdgeId === edge.id) return false;
    if (selectedNodeId) {
      return edge.source !== selectedNodeId && edge.target !== selectedNodeId;
    }
    return true;
  };

  const isEdgeActive = (edge: GraphEdge) => {
    if (currentTime === 0) return true;
    return edge.activeIntervals.some(([start, end]) => {
      const s = new Date(start).getTime();
      const e = new Date(end).getTime();
      return currentTime >= s && currentTime <= e;
    });
  };

  return (
    <>
      <ambientLight intensity={0.6} />
      <directionalLight position={[10, 10, 5]} intensity={0.8} />
      <pointLight position={[-10, -10, -5]} intensity={0.3} />

      {/* 边 */}
      {displayEdges.map(edge => {
        // 优化层标记为 hidden 的边不渲染
        if (edge.visibility === 'hidden') return null;
        const from = positions[edge.source];
        const to = positions[edge.target];
        if (!from || !to) return null;
        return (
          <EdgeLine
            key={edge.id}
            edge={edge}
            from={from}
            to={to}
            active={isEdgeActive(edge)}
            highlighted={highlightedEdgeIds.has(edge.id)}
            removed={removedEdgeIds?.has(edge.id) ?? false}
            affected={affectedEdgeIds?.has(edge.id) ?? false}
            dimmed={isEdgeDimmed(edge) || edge.visibility === 'dimmed'}
            showArrow={shouldShowArrow(edge.id)}
            onClick={() => {
              setSelectedEdgeId(edge.id);
              setSelectedNodeId(null);
              onSelectEdge?.(edge);
            }}
          />
        );
      })}

      {/* 节点 */}
      {displayNodes.map(node => {
        const pos = positions[node.id];
        if (!pos) return null;
        const lod = nodeLODs.get(node.id) ?? 'full';
        // hidden 级别不进行渲染
        if (lod === 'hidden') return null;
        const optNode = node as OptimizedNode;
        const isCluster = optNode.cluster?.isCluster ?? false;
        return (
          <NodeSphere
            key={node.id}
            node={node}
            position={pos}
            highlighted={highlightedNodeIds.has(node.id)}
            removed={removedNodeIds?.has(node.id) ?? false}
            affected={affectedNodeIds?.has(node.id) ?? false}
            altPath={altPathNodeIds?.has(node.id) ?? false}
            selected={selectedNodeId === node.id}
            dimmed={isNodeDimmed(node.id)}
            showLabel={showLabels}
            riskHeatEnabled={riskHeatEnabled}
            lodLevel={lod}
            onClick={() => {
              // 簇节点：点击展开/折叠
              if (isCluster) {
                toggleCluster(node.id);
                return;
              }
              setSelectedNodeId(node.id);
              setSelectedEdgeId(null);
              onSelectNode?.(node);
            }}
          />
        );
      })}

      {/* Dry-run 的替代路径线 */}
      {altPaths && altPaths.length > 0 && (
        <AltPathLines altPaths={altPaths} positions={positions} />
      )}

      {/* 网格（动态大小和位置） */}
      <gridHelper
        args={[gridParams.size, gridParams.divisions, '#e5e7eb', '#f3f4f6']}
        position={[0, gridParams.positionY, 0]}
      />

      {/* 相机控制器 */}
      <CameraController
        preset={cameraPreset ?? null}
        onDone={onCameraPresetDone ?? (() => {})}
        positions={positions}
        focusNodeId={focusNodeId}
        onFocusDone={onFocusDone}
        cameraLimits={cameraLimits}
      />

      <OrbitControls
        makeDefault
        enableDamping
        dampingFactor={0.1}
        minDistance={cameraLimits.minDistance}
        maxDistance={cameraLimits.maxDistance}
        target={new THREE.Vector3(...cameraLimits.fitTarget)}
      />
    </>
  );
}

// ── 主导出组件 ──
export default function Topology3D(props: Topology3DProps) {
  const [mounted, setMounted] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMounted(true);
    return () => {
      if (containerRef.current) {
        while (containerRef.current.firstChild) {
          containerRef.current.removeChild(containerRef.current.firstChild);
        }
      }
      setMounted(false);
    };
  }, []);

  if (!mounted) return null;

  return (
    <CanvasErrorBoundary>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }}>
        <Canvas
          camera={{ position: [0, 8, 12], fov: 50 }}
          style={{ background: '#f8fafc' }}
          onPointerMissed={() => {
            props.onSelectNode?.(null);
            props.onSelectEdge?.(null);
          }}
        >
          <Scene {...props} />
        </Canvas>
      </div>
    </CanvasErrorBoundary>
  );
}

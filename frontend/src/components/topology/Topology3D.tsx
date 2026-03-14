'use client';

import { useRef, useMemo, useState, useEffect } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Text, Line } from '@react-three/drei';
import * as THREE from 'three';
import { GraphNode, GraphEdge } from '@/lib/api/types';
import CanvasErrorBoundary from './CanvasErrorBoundary';
import { computeLayout, type LayoutMode, type LayoutResult } from './layouts';
import ArrowHead from './ArrowHead';
import RiskHeatDisk from './RiskHeatDisk';
import CameraController, { type CameraPreset } from './CameraController';

// ── Types ──
export interface Topology3DProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  currentTime: number;       // unix ms
  highlightAlertId?: string | null;
  impactedNodeIds?: Set<string>;
  impactedEdgeIds?: Set<string>;
  layoutMode?: LayoutMode;
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

// ── Animated position wrapper: lerps between old and new positions ──
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
    // On first mount snap immediately
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

// ── Pulsing ring for dry-run impacted nodes ──
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

// ── Breathing pulse for alert-highlighted nodes ──
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

// ── Node sphere ──
function NodeSphere({
  node,
  position,
  highlighted,
  impacted,
  selected,
  dimmed,
  showLabel,
  riskHeatEnabled,
  onClick,
}: {
  node: GraphNode;
  position: [number, number, number];
  highlighted: boolean;
  impacted: boolean;
  selected: boolean;
  dimmed: boolean;
  showLabel: boolean;
  riskHeatEnabled: boolean;
  onClick: () => void;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const [hovered, setHovered] = useState(false);

  const color = useMemo(() => {
    if (highlighted) return '#ef4444';
    if (impacted) return '#f59e0b';
    if (node.type === 'gateway' || node.type === 'router') return '#22c55e';
    if (node.type === 'subnet') return '#8b5cf6';
    if (node.type === 'server') return '#06b6d4';
    if (node.risk >= 0.7) return '#f97316';
    if (node.risk >= 0.4) return '#eab308';
    if (node.risk >= 0.2) return '#3b82f6';
    return '#6ee7b7';
  }, [node, highlighted, impacted]);

  // Risk-based emissive: stronger glow for higher risk when heat is enabled
  const emissiveColor = highlighted
    ? '#ef4444'
    : impacted
      ? '#f59e0b'
      : riskHeatEnabled && node.risk >= 0.4
        ? color
        : '#000000';
  const emissiveVal = highlighted
    ? 0.4
    : impacted
      ? 0.3
      : riskHeatEnabled
        ? node.risk * 0.5
        : 0;
  const scale = selected ? 1.4 : hovered ? 1.2 : 1;
  const opacity = dimmed ? 0.25 : 0.9;

  return (
    <AnimatedGroup targetPosition={position}>
      <mesh
        ref={meshRef}
        onClick={(e) => { e.stopPropagation(); onClick(); }}
        onPointerOver={() => setHovered(true)}
        onPointerOut={() => setHovered(false)}
        scale={scale}
      >
        <sphereGeometry args={[0.5 + node.risk * 0.4, 16, 16]} />
        <meshStandardMaterial
          color={color}
          emissive={emissiveColor}
          emissiveIntensity={emissiveVal}
          transparent
          opacity={opacity}
        />
      </mesh>
      {/* Selection ring */}
      {selected && (
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.9, 1.1, 32]} />
          <meshBasicMaterial color="#ffffff" side={THREE.DoubleSide} />
        </mesh>
      )}
      {/* Pulsing ring for impacted */}
      {impacted && !selected && <PulsingRing color="#f59e0b" />}
      {/* Breathing pulse for alert-highlighted */}
      {highlighted && <BreathingPulse />}
      {/* Risk heat disk */}
      {riskHeatEnabled && <RiskHeatDisk risk={node.risk} />}
      {/* Label */}
      {showLabel && (
        <Text
          position={[0, 1.2, 0]}
          fontSize={0.4}
          color="#374151"
          anchorX="center"
          anchorY="bottom"
        >
          {node.label}
        </Text>
      )}
    </AnimatedGroup>
  );
}

// ── Animated dashed edge for dry-run impact (flowing dash) ──
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
    />
  );
}

// ── Edge line ──
function EdgeLine({
  edge,
  from,
  to,
  active,
  highlighted,
  impacted,
  dimmed,
  showArrow,
  onClick,
}: {
  edge: GraphEdge;
  from: [number, number, number];
  to: [number, number, number];
  active: boolean;
  highlighted: boolean;
  impacted: boolean;
  dimmed: boolean;
  showArrow: boolean;
  onClick: () => void;
}) {
  const [hovered, setHovered] = useState(false);

  const color = useMemo(() => {
    if (highlighted) return '#ef4444';
    if (impacted) return '#f59e0b';
    if ((edge.alert_ids ?? []).length > 0) return '#f97316';
    return '#9ca3af';
  }, [edge, highlighted, impacted]);

  const baseOpacity = active ? (highlighted ? 1 : impacted ? 0.5 : 0.8) : 0.08;
  const opacity = dimmed ? baseOpacity * 0.2 : baseOpacity;
  const lineWidth = highlighted ? 3 : impacted ? 2.5 : hovered ? 2.5 : active ? 1.5 : 0.5;

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
      {impacted ? (
        <FlowingDashLine from={from} to={to} color={color} lineWidth={lineWidth} />
      ) : (
        <Line
          points={[from, to]}
          color={color}
          lineWidth={lineWidth}
          transparent
          opacity={opacity}
        />
      )}
      {/* Arrow head */}
      {showArrow && active && <ArrowHead from={from} to={to} color={color} opacity={opacity} />}
      {/* Invisible cylinder for click detection */}
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
      {/* Weight / impact label */}
      {active && (highlighted || impacted) && (
        <Text position={[mid[0], mid[1] + 0.5, mid[2]]} fontSize={0.3} color={impacted ? '#f59e0b' : '#ef4444'}>
          {impacted ? '⚠ IMPACTED' : `${(edge.protocols ?? []).join(',')} w=${edge.weight}`}
        </Text>
      )}
    </group>
  );
}

// ── Alternative-path lines (green dashed) for dry-run ──
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
          // Offset slightly upward so it doesn't z-fight with real edges
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
            />
          );
        });
      })}
    </>
  );
}

// ── Scene ──
function Scene({
  nodes,
  edges,
  currentTime,
  highlightAlertId,
  impactedNodeIds,
  impactedEdgeIds,
  layoutMode = 'circle',
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

  const positions = useMemo(
    () => computeLayout(layoutMode, { nodes, edges }),
    [nodes, edges, layoutMode],
  );

  // Determine which edges should show arrows
  const arrowEdgeIds = useMemo(() => {
    // DAG mode: all arrows by default
    if (layoutMode === 'dag' || showArrows) return null; // null = all
    // When a node is selected, show arrows on its edges
    if (selectedNodeId) {
      return new Set(
        edges
          .filter(e => e.source === selectedNodeId || e.target === selectedNodeId)
          .map(e => e.id),
      );
    }
    // When an edge is selected, show its arrow only
    if (selectedEdgeId) return new Set([selectedEdgeId]);
    return new Set<string>(); // empty = none
  }, [layoutMode, showArrows, selectedNodeId, selectedEdgeId, edges]);

  const shouldShowArrow = (edgeId: string) =>
    arrowEdgeIds === null || arrowEdgeIds.has(edgeId);

  const highlightedEdgeIds = useMemo(() => {
    if (!highlightAlertId) return new Set<string>();
    return new Set(
      edges.filter(e => (e.alert_ids ?? []).includes(highlightAlertId)).map(e => e.id),
    );
  }, [edges, highlightAlertId]);

  const highlightedNodeIds = useMemo(() => {
    if (!highlightAlertId) return new Set<string>();
    const nodeIds = new Set<string>();
    edges.forEach(e => {
      if ((e.alert_ids ?? []).includes(highlightAlertId)) {
        nodeIds.add(e.source);
        nodeIds.add(e.target);
      }
    });
    return nodeIds;
  }, [edges, highlightAlertId]);

  // Dimming: when something is selected, dim non-related elements
  const hasSelection = selectedNodeId !== null || selectedEdgeId !== null;

  const isNodeDimmed = (nodeId: string) => {
    if (!hasSelection) return false;
    if (selectedNodeId === nodeId) return false;
    if (selectedEdgeId) {
      const edge = edges.find(e => e.id === selectedEdgeId);
      if (edge && (edge.source === nodeId || edge.target === nodeId)) return false;
    }
    if (selectedNodeId) {
      // Don't dim direct neighbours
      const isNeighbour = edges.some(
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

      {/* Edges */}
      {edges.map(edge => {
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
            impacted={impactedEdgeIds?.has(edge.id) ?? false}
            dimmed={isEdgeDimmed(edge)}
            showArrow={shouldShowArrow(edge.id)}
            onClick={() => {
              setSelectedEdgeId(edge.id);
              setSelectedNodeId(null);
              onSelectEdge?.(edge);
            }}
          />
        );
      })}

      {/* Nodes */}
      {nodes.map(node => {
        const pos = positions[node.id];
        if (!pos) return null;
        return (
          <NodeSphere
            key={node.id}
            node={node}
            position={pos}
            highlighted={highlightedNodeIds.has(node.id)}
            impacted={impactedNodeIds?.has(node.id) ?? false}
            selected={selectedNodeId === node.id}
            dimmed={isNodeDimmed(node.id)}
            showLabel={showLabels}
            riskHeatEnabled={riskHeatEnabled}
            onClick={() => {
              setSelectedNodeId(node.id);
              setSelectedEdgeId(null);
              onSelectNode?.(node);
            }}
          />
        );
      })}

      {/* Alternative-path lines for dry-run */}
      {altPaths && altPaths.length > 0 && (
        <AltPathLines altPaths={altPaths} positions={positions} />
      )}

      {/* Grid */}
      <gridHelper args={[20, 20, '#e5e7eb', '#f3f4f6']} position={[0, -3, 0]} />

      {/* Camera controller */}
      <CameraController
        preset={cameraPreset ?? null}
        onDone={onCameraPresetDone ?? (() => {})}
        positions={positions}
        focusNodeId={focusNodeId}
        onFocusDone={onFocusDone}
      />

      <OrbitControls
        makeDefault
        enableDamping
        dampingFactor={0.1}
        minDistance={3}
        maxDistance={50}
      />
    </>
  );
}

// ── Main export ──
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

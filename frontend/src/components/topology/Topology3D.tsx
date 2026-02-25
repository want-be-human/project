'use client';

import { useRef, useMemo, useState, useEffect, useCallback } from 'react';
import { Canvas, useFrame, useThree, ThreeEvent } from '@react-three/fiber';
import { OrbitControls, Text, Line } from '@react-three/drei';
import * as THREE from 'three';
import { GraphNode, GraphEdge } from '@/lib/api/types';
import CanvasErrorBoundary from './CanvasErrorBoundary';

// ── Types ──
interface Topology3DProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  currentTime: number;       // unix ms
  highlightAlertId?: string | null;
  impactedNodeIds?: Set<string>;   // dry-run impacted nodes (amber)
  impactedEdgeIds?: Set<string>;   // dry-run impacted edges (amber dashed)
  onSelectNode?: (node: GraphNode | null) => void;
  onSelectEdge?: (edge: GraphEdge | null) => void;
}

// ── Layout: force-directed positions (simple deterministic) ──
function computeLayout(nodes: GraphNode[], edges: GraphEdge[]) {
  const positions: Record<string, [number, number, number]> = {};
  const n = nodes.length;
  // Place nodes in a circle on XZ plane, spread by index
  nodes.forEach((node, i) => {
    const angle = (i / n) * Math.PI * 2;
    const radius = 4 + n * 0.5;
    positions[node.id] = [
      Math.cos(angle) * radius,
      (node.risk - 0.5) * 3,  // Y based on risk
      Math.sin(angle) * radius,
    ];
  });
  return positions;
}

// ── Node sphere ──
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

function NodeSphere({
  node,
  position,
  highlighted,
  impacted,
  selected,
  onClick,
}: {
  node: GraphNode;
  position: [number, number, number];
  highlighted: boolean;
  impacted: boolean;
  selected: boolean;
  onClick: () => void;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const [hovered, setHovered] = useState(false);

  const color = useMemo(() => {
    if (highlighted) return '#ef4444';      // red — alert
    if (impacted) return '#f59e0b';          // amber — dry-run impacted
    if (node.type === 'gateway' || node.type === 'router') return '#22c55e';
    if (node.type === 'subnet') return '#8b5cf6';
    if (node.type === 'server') return '#06b6d4';
    if (node.risk >= 0.7) return '#f97316';
    if (node.risk >= 0.4) return '#eab308';
    if (node.risk >= 0.2) return '#3b82f6';
    return '#6ee7b7';
  }, [node, highlighted, impacted]);

  const emissiveColor = highlighted ? '#ef4444' : impacted ? '#f59e0b' : '#000000';
  const emissiveVal = highlighted ? 0.4 : impacted ? 0.3 : 0;
  const scale = selected ? 1.4 : hovered ? 1.2 : 1;

  return (
    <group position={position}>
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
          opacity={0.9}
        />
      </mesh>
      {/* Ring for selected */}
      {selected && (
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.9, 1.1, 32]} />
          <meshBasicMaterial color="#ffffff" side={THREE.DoubleSide} />
        </mesh>
      )}
      {/* Pulsing ring for impacted */}
      {impacted && !selected && <PulsingRing color="#f59e0b" />}
      {/* Label */}
      <Text
        position={[0, 1.2, 0]}
        fontSize={0.4}
        color="#374151"
        anchorX="center"
        anchorY="bottom"
      >
        {node.label}
      </Text>
    </group>
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
  onClick,
}: {
  edge: GraphEdge;
  from: [number, number, number];
  to: [number, number, number];
  active: boolean;
  highlighted: boolean;
  impacted: boolean;
  onClick: () => void;
}) {
  const [hovered, setHovered] = useState(false);

  const color = useMemo(() => {
    if (highlighted) return '#ef4444';        // red — alert edge
    if (impacted) return '#f59e0b';            // amber — dry-run impacted
    if ((edge.alert_ids ?? []).length > 0) return '#f97316';
    return '#9ca3af';
  }, [edge, highlighted, impacted]);

  const opacity = active ? (highlighted ? 1 : impacted ? 0.5 : 0.8) : 0.08;
  const lineWidth = highlighted ? 3 : impacted ? 2.5 : hovered ? 2.5 : active ? 1.5 : 0.5;

  // Compute cylinder geometry to cover the full edge for click detection
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
      <Line
        points={[from, to]}
        color={color}
        lineWidth={lineWidth}
        transparent
        opacity={opacity}
        dashed={impacted}
        dashSize={impacted ? 0.3 : undefined}
        gapSize={impacted ? 0.15 : undefined}
      />
      {/* Invisible cylinder covering the full edge length for click detection */}
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

// ── Scene ──
function Scene({
  nodes,
  edges,
  currentTime,
  highlightAlertId,
  impactedNodeIds,
  impactedEdgeIds,
  onSelectNode,
  onSelectEdge,
}: Topology3DProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);

  const positions = useMemo(() => computeLayout(nodes, edges), [nodes, edges]);

  const highlightedEdgeIds = useMemo(() => {
    if (!highlightAlertId) return new Set<string>();
    return new Set(
      edges.filter(e => (e.alert_ids ?? []).includes(highlightAlertId)).map(e => e.id)
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

  const isEdgeActive = (edge: GraphEdge) => {
    if (currentTime === 0) return true; // Show all if no time set
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
            onClick={() => {
              setSelectedNodeId(node.id);
              setSelectedEdgeId(null);
              onSelectNode?.(node);
            }}
          />
        );
      })}

      {/* Grid */}
      <gridHelper args={[20, 20, '#e5e7eb', '#f3f4f6']} position={[0, -3, 0]} />

      <OrbitControls
        makeDefault
        enableDamping
        dampingFactor={0.1}
        minDistance={3}
        maxDistance={30}
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
      // Imperatively clear the container BEFORE React attempts DOM reconciliation.
      // This prevents the "removeChild" NotFoundError caused by Three.js having
      // already destroyed internal DOM nodes.
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

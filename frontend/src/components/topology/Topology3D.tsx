'use client';

import { useRef, useMemo, useState, useEffect } from 'react';
import { Canvas, useFrame, useThree, ThreeEvent } from '@react-three/fiber';
import { OrbitControls, Text, Line } from '@react-three/drei';
import * as THREE from 'three';
import { GraphNode, GraphEdge } from '@/lib/api/types';

// ── Types ──
interface Topology3DProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  currentTime: number;       // unix ms
  highlightAlertId?: string | null;
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
function NodeSphere({
  node,
  position,
  highlighted,
  selected,
  onClick,
}: {
  node: GraphNode;
  position: [number, number, number];
  highlighted: boolean;
  selected: boolean;
  onClick: () => void;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const [hovered, setHovered] = useState(false);

  const color = useMemo(() => {
    if (highlighted) return '#ef4444';
    if (node.type === 'gateway') return '#22c55e';
    if (node.risk > 0.7) return '#f97316';
    if (node.risk > 0.3) return '#eab308';
    return '#3b82f6';
  }, [node, highlighted]);

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
          emissive={highlighted ? '#ef4444' : '#000000'}
          emissiveIntensity={highlighted ? 0.4 : 0}
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
  onClick,
}: {
  edge: GraphEdge;
  from: [number, number, number];
  to: [number, number, number];
  active: boolean;
  highlighted: boolean;
  onClick: () => void;
}) {
  const color = useMemo(() => {
    if (highlighted) return '#ef4444';
    if ((edge.alert_ids ?? []).length > 0) return '#f97316';
    return '#9ca3af';
  }, [edge, highlighted]);

  const opacity = active ? (highlighted ? 1 : 0.8) : 0.08;
  const lineWidth = highlighted ? 3 : active ? 1.5 : 0.5;

  // Midpoint for click target
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
      />
      {/* Invisible click target at midpoint */}
      <mesh position={mid} onClick={(e) => { e.stopPropagation(); onClick(); }}>
        <sphereGeometry args={[0.3, 8, 8]} />
        <meshBasicMaterial transparent opacity={0} />
      </mesh>
      {/* Weight label on active highlighted edges */}
      {active && highlighted && (
        <Text position={[mid[0], mid[1] + 0.5, mid[2]]} fontSize={0.3} color="#ef4444">
          {(edge.protocols ?? []).join(',')} w={edge.weight}
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
  return (
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
  );
}

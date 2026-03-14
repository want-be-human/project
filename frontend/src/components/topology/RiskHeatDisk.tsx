'use client';

import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

interface RiskHeatDiskProps {
  risk: number; // 0–1
}

/**
 * Semi-transparent disk below a node visualising risk as a heat spot.
 * - Radius scales with risk
 * - Colour graduates green → yellow → red
 * - High risk (≥0.7) gets a subtle pulse animation
 */
export default function RiskHeatDisk({ risk }: RiskHeatDiskProps) {
  const ref = useRef<THREE.Mesh>(null);

  // Colour: green(0) → yellow(0.5) → red(1)
  const color = risk >= 0.7 ? '#ef4444' : risk >= 0.4 ? '#eab308' : '#22c55e';
  const baseRadius = 0.5 + risk * 2;
  const baseOpacity = 0.1 + risk * 0.35;

  useFrame(({ clock }) => {
    if (!ref.current) return;
    if (risk >= 0.7) {
      // Subtle pulse for high-risk nodes
      const pulse = 1 + Math.sin(clock.getElapsedTime() * 2.5) * 0.08;
      ref.current.scale.set(pulse, pulse, 1);
      (ref.current.material as THREE.MeshBasicMaterial).opacity =
        baseOpacity + Math.sin(clock.getElapsedTime() * 2.5) * 0.06;
    }
  });

  return (
    <mesh
      ref={ref}
      rotation={[-Math.PI / 2, 0, 0]}
      position={[0, -0.55, 0]}
    >
      <circleGeometry args={[baseRadius, 32]} />
      <meshBasicMaterial
        color={color}
        transparent
        opacity={baseOpacity}
        side={THREE.DoubleSide}
        depthWrite={false}
      />
    </mesh>
  );
}

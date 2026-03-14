'use client';

import { useMemo } from 'react';
import * as THREE from 'three';

interface ArrowHeadProps {
  from: [number, number, number];
  to: [number, number, number];
  color: string;
  opacity?: number;
}

/**
 * Cone-based arrow head rendered near the target end of an edge.
 */
export default function ArrowHead({ from, to, color, opacity = 0.9 }: ArrowHeadProps) {
  const { position, quaternion } = useMemo(() => {
    const a = new THREE.Vector3(...from);
    const b = new THREE.Vector3(...to);
    const dir = new THREE.Vector3().subVectors(b, a).normalize();
    // Place arrow at 85% along the edge (near target, offset to avoid overlap with node sphere)
    const pos = new THREE.Vector3().lerpVectors(a, b, 0.82);
    const quat = new THREE.Quaternion().setFromUnitVectors(
      new THREE.Vector3(0, 1, 0),
      dir,
    );
    return { position: pos.toArray() as [number, number, number], quaternion: quat };
  }, [from, to]);

  return (
    <mesh position={position} quaternion={quaternion}>
      <coneGeometry args={[0.15, 0.45, 8]} />
      <meshStandardMaterial color={color} transparent opacity={opacity} />
    </mesh>
  );
}

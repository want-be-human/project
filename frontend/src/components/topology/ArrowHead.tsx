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
 * 使用圆锥体渲染的箭头头部，显示在边接近目标端的位置。
 */
export default function ArrowHead({ from, to, color, opacity = 0.9 }: ArrowHeadProps) {
  const { position, quaternion } = useMemo(() => {
    const a = new THREE.Vector3(...from);
    const b = new THREE.Vector3(...to);
    const dir = new THREE.Vector3().subVectors(b, a).normalize();
    // 将箭头放在边长度的 82% 处（靠近目标端，并避免与节点球体重叠）
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

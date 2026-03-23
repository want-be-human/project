'use client';

import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

interface RiskHeatDiskProps {
  risk: number; // 0–1
}

/**
 * 节点下方的半透明圆盘，用热斑形式可视化风险。
 * - 半径随风险值缩放
 * - 颜色由绿 → 黄 → 红渐变
 * - 高风险（≥0.7）会有轻微脉冲动画
 */
export default function RiskHeatDisk({ risk }: RiskHeatDiskProps) {
  const ref = useRef<THREE.Mesh>(null);

  // 颜色映射：green(0) → yellow(0.5) → red(1)
  const color = risk >= 0.7 ? '#ef4444' : risk >= 0.4 ? '#eab308' : '#22c55e';
  const baseRadius = 0.5 + risk * 2;
  const baseOpacity = 0.1 + risk * 0.35;

  useFrame(({ clock }) => {
    if (!ref.current) return;
    if (risk >= 0.7) {
      // 高风险节点的轻微脉冲效果
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

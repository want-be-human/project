'use client';

import { useEffect, useRef } from 'react';
import { useThree, useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { LayoutResult } from './layouts/types';
import type { CameraLimits } from './optimization/types';

export type CameraPreset = 'top' | 'front' | 'side' | 'fit' | null;

interface CameraControllerProps {
  preset: CameraPreset;
  /** 相机动画结束后调用，用于重置触发器 */
  onDone: () => void;
  /** 当前节点坐标，用于计算全图适配视角 */
  positions: LayoutResult;
  /** 需要飞行聚焦的节点 ID */
  focusNodeId?: string | null;
  onFocusDone?: () => void;
  /** 优化层提供的动态相机限制 */
  cameraLimits?: CameraLimits;
}

const LERP_SPEED = 4; // 数值越大，动画越快

/**
 * 管理预设视角与节点聚焦的平滑相机过渡。
 * 必须放置在 <Canvas> 内部。
 */
export default function CameraController({
  preset,
  onDone,
  positions,
  focusNodeId,
  onFocusDone,
  cameraLimits,
}: CameraControllerProps) {
  const { camera } = useThree();
  const targetPos = useRef<THREE.Vector3 | null>(null);
  const targetLookAt = useRef<THREE.Vector3>(new THREE.Vector3());
  const animating = useRef(false);

  // 根据包围盒计算”全图适配”相机位置
  useEffect(() => {
    if (!preset) return;

    // 所有预设都看向图中心（而非固定原点）
    const center = cameraLimits
      ? new THREE.Vector3(...cameraLimits.fitTarget)
      : new THREE.Vector3(0, 0, 0);

    if (preset === 'fit') {
      if (cameraLimits) {
        targetPos.current = new THREE.Vector3(...cameraLimits.fitPosition);
        targetLookAt.current.copy(center);
      } else {
        const pts = Object.values(positions);
        if (pts.length === 0) { onDone(); return; }
        const box = new THREE.Box3();
        pts.forEach(([x, y, z]) => box.expandByPoint(new THREE.Vector3(x, y, z)));
        box.getCenter(center);
        const size = box.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z, 5);
        const dist = maxDim * 1.8;
        targetPos.current = new THREE.Vector3(center.x, center.y + dist * 0.5, center.z + dist);
        targetLookAt.current.copy(center);
      }
    } else {
      // top / front / side：基于图对角线缩放偏移量，看向图中心
      const d = cameraLimits
        ? Math.max(
            Math.abs(cameraLimits.fitPosition[0] - cameraLimits.fitTarget[0]),
            Math.abs(cameraLimits.fitPosition[1] - cameraLimits.fitTarget[1]),
            Math.abs(cameraLimits.fitPosition[2] - cameraLimits.fitTarget[2]),
            10,
          )
        : 25;

      if (preset === 'top') {
        targetPos.current = new THREE.Vector3(center.x, center.y + d, center.z + 0.01);
      } else if (preset === 'front') {
        targetPos.current = new THREE.Vector3(center.x, center.y + d * 0.2, center.z + d);
      } else if (preset === 'side') {
        targetPos.current = new THREE.Vector3(center.x + d, center.y + d * 0.2, center.z);
      }
      targetLookAt.current.copy(center);
    }
    animating.current = true;
  }, [preset, positions, onDone, cameraLimits]);

  // 聚焦到指定节点
  useEffect(() => {
    if (!focusNodeId) return;
    const pos = positions[focusNodeId];
    if (!pos) return;

    const nodeVec = new THREE.Vector3(...pos);
    const camDir = new THREE.Vector3().subVectors(camera.position, nodeVec).normalize();
    const dist = 8;

    targetPos.current = nodeVec.clone().add(camDir.multiplyScalar(dist));
    targetLookAt.current.copy(nodeVec);
    animating.current = true;
  }, [focusNodeId, positions, camera]);

  useFrame((_, delta) => {
    if (!animating.current || !targetPos.current) return;

    const t = Math.min(1, LERP_SPEED * delta);
    camera.position.lerp(targetPos.current, t);
    camera.lookAt(targetLookAt.current);

    // 检查是否收敛到目标位置
    if (camera.position.distanceTo(targetPos.current) < 0.05) {
      animating.current = false;
      targetPos.current = null;

      if (preset) onDone();
      if (focusNodeId && onFocusDone) onFocusDone();
    }
  });

  return null;
}

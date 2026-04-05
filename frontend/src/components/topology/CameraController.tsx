'use client';

import { useEffect, useRef } from 'react';
import { useThree, useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { LayoutResult } from './layouts/types';
import type { CameraLimits } from './optimization/types';

export type CameraPreset = 'fit' | null;

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

const LERP_SPEED = 4;

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
  const { camera, controls } = useThree();
  const targetPos = useRef<THREE.Vector3 | null>(null);
  const targetLookAt = useRef<THREE.Vector3>(new THREE.Vector3());
  const animating = useRef(false);
  // 首次 fit 时直接跳转，避免从默认位置缓慢 LERP
  const firstFit = useRef(true);

  useEffect(() => {
    if (preset !== 'fit') return;

    const center = cameraLimits
      ? new THREE.Vector3(...cameraLimits.fitTarget)
      : new THREE.Vector3(0, 0, 0);

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
      targetPos.current = new THREE.Vector3(center.x + dist, center.y + dist * 0.2, center.z);
      targetLookAt.current.copy(center);
    }

    // 首次 fit：直接跳转到目标位置
    if (firstFit.current && targetPos.current) {
      firstFit.current = false;
      camera.position.copy(targetPos.current);
      camera.lookAt(targetLookAt.current);
      camera.updateProjectionMatrix();
      if (controls && 'target' in controls) {
        (controls.target as THREE.Vector3).copy(targetLookAt.current);
        (controls as any).update();
      }
      targetPos.current = null;
      onDone();
      return;
    }

    animating.current = true;
  }, [preset, positions, onDone, cameraLimits, camera, controls]);

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

    // 同步 OrbitControls 的 target
    if (controls && 'target' in controls) {
      (controls.target as THREE.Vector3).copy(targetLookAt.current);
      (controls as any).update();
    }

    if (camera.position.distanceTo(targetPos.current) < 0.05) {
      animating.current = false;
      targetPos.current = null;

      if (preset) onDone();
      if (focusNodeId && onFocusDone) onFocusDone();
    }
  });

  return null;
}

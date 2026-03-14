'use client';

import { useEffect, useRef } from 'react';
import { useThree, useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { LayoutResult } from './layouts/types';

export type CameraPreset = 'top' | 'front' | 'side' | 'fit' | null;

interface CameraControllerProps {
  preset: CameraPreset;
  /** Called once the camera animation finishes to reset the trigger */
  onDone: () => void;
  /** Current node positions for fit-all calculation */
  positions: LayoutResult;
  /** Node ID to fly the camera towards */
  focusNodeId?: string | null;
  onFocusDone?: () => void;
}

const PRESET_POSITIONS: Record<string, THREE.Vector3> = {
  top:   new THREE.Vector3(0, 25, 0.01), // slight z offset to avoid gimbal lock
  front: new THREE.Vector3(0, 5, 25),
  side:  new THREE.Vector3(25, 5, 0),
};

const LERP_SPEED = 4; // higher = faster animation

/**
 * Manages smooth camera transitions for presets and node focus.
 * Must be placed inside <Canvas>.
 */
export default function CameraController({
  preset,
  onDone,
  positions,
  focusNodeId,
  onFocusDone,
}: CameraControllerProps) {
  const { camera } = useThree();
  const targetPos = useRef<THREE.Vector3 | null>(null);
  const targetLookAt = useRef<THREE.Vector3>(new THREE.Vector3());
  const animating = useRef(false);

  // Compute fit-all camera position from bounding box
  useEffect(() => {
    if (!preset) return;

    if (preset === 'fit') {
      const pts = Object.values(positions);
      if (pts.length === 0) { onDone(); return; }

      const box = new THREE.Box3();
      pts.forEach(([x, y, z]) => box.expandByPoint(new THREE.Vector3(x, y, z)));
      const center = new THREE.Vector3();
      box.getCenter(center);
      const size = box.getSize(new THREE.Vector3());
      const maxDim = Math.max(size.x, size.y, size.z, 5);
      const dist = maxDim * 1.6;

      targetPos.current = new THREE.Vector3(center.x, center.y + dist * 0.4, center.z + dist);
      targetLookAt.current.copy(center);
    } else {
      const pos = PRESET_POSITIONS[preset];
      if (pos) {
        targetPos.current = pos.clone();
        targetLookAt.current.set(0, 0, 0);
      }
    }
    animating.current = true;
  }, [preset, positions, onDone]);

  // Focus on a specific node
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

    // Check convergence
    if (camera.position.distanceTo(targetPos.current) < 0.05) {
      animating.current = false;
      targetPos.current = null;

      if (preset) onDone();
      if (focusNodeId && onFocusDone) onFocusDone();
    }
  });

  return null;
}

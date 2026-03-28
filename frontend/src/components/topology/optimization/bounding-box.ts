import type { LayoutResult } from '../layouts/types';
import type { BoundingBoxInfo, CameraLimits, GridParams } from './types';

/**
 * 从布局坐标计算包围盒信息。
 * 空图时返回默认值。
 */
export function computeBoundingBox(positions: LayoutResult): BoundingBoxInfo {
  const pts = Object.values(positions);
  if (pts.length === 0) {
    return {
      min: [0, 0, 0],
      max: [0, 0, 0],
      center: [0, 0, 0],
      diagonal: 10,
    };
  }

  const min: [number, number, number] = [Infinity, Infinity, Infinity];
  const max: [number, number, number] = [-Infinity, -Infinity, -Infinity];

  for (const [x, y, z] of pts) {
    if (x < min[0]) min[0] = x;
    if (y < min[1]) min[1] = y;
    if (z < min[2]) min[2] = z;
    if (x > max[0]) max[0] = x;
    if (y > max[1]) max[1] = y;
    if (z > max[2]) max[2] = z;
  }

  const center: [number, number, number] = [
    (min[0] + max[0]) / 2,
    (min[1] + max[1]) / 2,
    (min[2] + max[2]) / 2,
  ];

  const diagonal = Math.sqrt(
    (max[0] - min[0]) ** 2 +
    (max[1] - min[1]) ** 2 +
    (max[2] - min[2]) ** 2,
  );

  return { min, max, center, diagonal: Math.max(diagonal, 5) };
}

/**
 * 根据包围盒计算动态相机限制。
 * minDistance 和 maxDistance 随图大小自适应。
 */
export function computeCameraLimits(bb: BoundingBoxInfo): CameraLimits {
  const d = bb.diagonal;
  return {
    minDistance: Math.max(d * 0.15, 2),
    maxDistance: d * 3,
    fitPosition: [
      bb.center[0],
      bb.center[1] + d * 0.4,
      bb.center[2] + d,
    ],
    fitTarget: [...bb.center],
  };
}

/**
 * 根据包围盒计算网格参数。
 * 网格大小对齐到 5 的倍数，位置在包围盒底部下方。
 */
export function computeGridParams(bb: BoundingBoxInfo): GridParams {
  const rawSize = Math.max(bb.diagonal * 1.2, 10);
  const size = Math.ceil(rawSize / 5) * 5;
  return {
    size,
    divisions: Math.max(Math.round(size / 2), 10),
    positionY: bb.min[1] - 1.5,
  };
}

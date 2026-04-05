import type { LayoutResult } from '../layouts/types';
import type { BoundingBoxInfo, CameraLimits, GridParams } from './types';

// ── 视觉外扩常量 ──
// 节点球体最大半径：0.5 + risk*0.4，risk=1 → 0.9；簇节点 scale=1.6 → ~1.44
const NODE_VISUAL_RADIUS = 1.0;
// 脉冲环 / 选中环外扩
const RING_EXTRA = 0.5;
// 标签高度（仅影响 Y 轴上方）
const LABEL_HEIGHT = 1.5;
// 边箭头头部长度（XZ 平面外扩）
const ARROW_EXTRA = 0.3;
// 最终 padding 比例（含 UI 浮层安全边距）
const PADDING_FACTOR = 0.08; // 8%：适度安全边距

/**
 * 从布局坐标计算视觉包围盒。
 * 在节点中心点基础上外扩节点半径、标签（Y轴上方）、脉冲环、箭头等视觉元素。
 *
 * 注意：标签在节点正上方（Y轴），不在 X/Z 方向延伸，
 * 因此 XZ 平面的包围盒只需外扩节点半径和箭头，不需要加标签宽度。
 */
export function computeBoundingBox(
  positions: LayoutResult,
  options: { includeLabels?: boolean } = {},
): BoundingBoxInfo {
  const pts = Object.values(positions);
  if (pts.length === 0) {
    return { min: [-5, -5, -5], max: [5, 5, 5], center: [0, 0, 0], diagonal: 10 };
  }

  const visualRadius = NODE_VISUAL_RADIUS + RING_EXTRA;
  const labelH = options.includeLabels !== false ? LABEL_HEIGHT : 0;

  const min: [number, number, number] = [Infinity, Infinity, Infinity];
  const max: [number, number, number] = [-Infinity, -Infinity, -Infinity];

  for (const [x, y, z] of pts) {
    // XZ 平面：节点半径 + 箭头（标签在 Y 轴上方，不影响 XZ 范围）
    const xzPad = visualRadius + ARROW_EXTRA;
    // Y 轴：上方加标签高度，下方只加节点半径
    const yPadUp = visualRadius + labelH;
    const yPadDown = visualRadius;

    if (x - xzPad < min[0]) min[0] = x - xzPad;
    if (y - yPadDown < min[1]) min[1] = y - yPadDown;
    if (z - xzPad < min[2]) min[2] = z - xzPad;
    if (x + xzPad > max[0]) max[0] = x + xzPad;
    if (y + yPadUp > max[1]) max[1] = y + yPadUp;
    if (z + xzPad > max[2]) max[2] = z + xzPad;
  }

  const center: [number, number, number] = [
    (min[0] + max[0]) / 2,
    (min[1] + max[1]) / 2,
    (min[2] + max[2]) / 2,
  ];

  const sizeX = max[0] - min[0];
  const sizeY = max[1] - min[1];
  const sizeZ = max[2] - min[2];
  const diagonal = Math.sqrt(sizeX ** 2 + sizeY ** 2 + sizeZ ** 2);

  return { min, max, center, diagonal: Math.max(diagonal, 5) };
}

/**
 * 根据包围盒和相机 FOV 计算动态相机限制。
 *
 * 核心算法：
 * 1. 计算图在各投影平面的尺寸
 * 2. 根据 PerspectiveCamera FOV=50°、aspect 计算能完整容纳的距离
 * 3. 对长条图（宽深比 > 3）按主轴方向单独计算
 * 4. 加入 PADDING_FACTOR 安全边距
 * 5. fitTarget 对齐到包围盒中心，而非固定原点
 */
export function computeCameraLimits(
  bb: BoundingBoxInfo,
  options: {
    fov?: number;
    aspect?: number;
  } = {},
): CameraLimits {
  const fovDeg = options.fov ?? 50;
  const aspect = options.aspect ?? (16 / 9);

  const halfFov = (fovDeg * Math.PI) / 180 / 2;

  const sizeX = bb.max[0] - bb.min[0];
  const sizeY = bb.max[1] - bb.min[1];
  const sizeZ = bb.max[2] - bb.min[2];
  const [cx, cy, cz] = bb.center;

  // 给定目标尺寸，计算相机需要退后多远才能完整容纳
  const distToFit = (halfSpanH: number, halfSpanV: number) => {
    const dH = halfSpanH / (Math.tan(halfFov) * aspect); // 水平方向限制
    const dV = halfSpanV / Math.tan(halfFov);             // 垂直方向限制
    return Math.max(dH, dV, 3) * (1 + PADDING_FACTOR);
  };

  // 长条图检测
  const xzRatio = sizeX > 0 && sizeZ > 0 ? Math.max(sizeX / sizeZ, sizeZ / sizeX) : 1;
  const isElongated = xzRatio > 3;

  const fitTarget: [number, number, number] = [cx, cy, cz];

  // 统一侧面视角：相机在 +X 方向偏移，略微抬升
  const dist = distToFit(sizeY / 2, sizeZ / 2);
  const finalDist = isElongated ? Math.max(dist, bb.diagonal * 0.85) : dist;
  const fitPosition: [number, number, number] = [cx + finalDist, cy + finalDist * 0.2, cz];

  const d = bb.diagonal;
  return {
    minDistance: Math.max(d * 0.08, 2),
    maxDistance: Math.max(d * 5, 20),
    fitPosition,
    fitTarget,
  };
}

/**
 * 根据包围盒计算网格参数。
 * 网格大小对齐到 5 的倍数，位置在图底部下方。
 */
export function computeGridParams(bb: BoundingBoxInfo): GridParams {
  const sizeX = bb.max[0] - bb.min[0];
  const sizeZ = bb.max[2] - bb.min[2];
  const maxSpan = Math.max(sizeX, sizeZ, 10);
  const size = Math.ceil((maxSpan * 1.2) / 5) * 5;
  return {
    size,
    divisions: Math.max(Math.round(size / 2), 10),
    positionY: bb.min[1] - 1.5,
  };
}

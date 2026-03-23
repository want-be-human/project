import type { LayoutConfig, LayoutResult } from './types';
import { circleLayout } from './circle';

// d3-force-3d 没有官方 @types，使用动态导入与手工类型定义
interface SimNode {
  id: string;
  x: number;
  y: number;
  z: number;
  risk: number;
}

/**
 * 基于 d3-force-3d 的三维力导向布局。
 * 先用 circle 布局初始化节点位置以避免随机初始抖动，
 * 再同步执行 300 次仿真迭代。
 */
export function forceLayout(config: LayoutConfig): LayoutResult {
  const { nodes, edges } = config;
  if (nodes.length === 0) return {};

  // 使用 circle 布局作为稳定初始种子
  const seed = circleLayout(config);

  // 构建仿真节点
  const simNodes: SimNode[] = nodes.map((n) => ({
    id: n.id,
    x: seed[n.id]?.[0] ?? 0,
    y: seed[n.id]?.[1] ?? 0,
    z: seed[n.id]?.[2] ?? 0,
    risk: n.risk,
  }));

  // 构建连边
  const nodeSet = new Set(nodes.map((n) => n.id));
  const links = edges
    .filter((e) => nodeSet.has(e.source) && nodeSet.has(e.target))
    .map((e) => ({ source: e.source, target: e.target }));

  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const d3Force3d = require('d3-force-3d');
    const sim = d3Force3d
      .forceSimulation(simNodes, 3)
      .force('charge', d3Force3d.forceManyBody().strength(-120))
      .force(
        'link',
        d3Force3d
          .forceLink(links)
          .id((d: SimNode) => d.id)
          .distance(5)
      )
      .force('center', d3Force3d.forceCenter())
      .stop();

    // 同步执行 300 次 tick
    for (let i = 0; i < 300; i++) sim.tick();

    const positions: LayoutResult = {};
    for (const n of simNodes) {
      // 保留基于风险的 Y 轴偏移
      positions[n.id] = [n.x, (n.risk - 0.5) * 3, n.z];
    }
    return positions;
  } catch {
    // d3-force-3d 不可用时回退
    return seed;
  }
}

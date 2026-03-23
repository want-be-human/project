export type { LayoutMode, LayoutResult, LayoutConfig } from './types';

import type { LayoutMode, LayoutConfig, LayoutResult } from './types';
import { circleLayout } from './circle';
import { forceLayout } from './force';
import { dagLayout } from './dag';
import { clusteredSubnetLayout } from './clustered-subnet';

/**
 * 按指定模式计算布局坐标。
 * 任意异常时回退到 circle 布局。
 */
export function computeLayout(
  mode: LayoutMode,
  config: LayoutConfig,
): LayoutResult {
  try {
    switch (mode) {
      case 'force':
        return forceLayout(config);
      case 'dag':
        return dagLayout(config);
      case 'clustered-subnet':
        return clusteredSubnetLayout(config);
      case 'circle':
      default:
        return circleLayout(config);
    }
  } catch {
    // 安全回退
    return circleLayout(config);
  }
}

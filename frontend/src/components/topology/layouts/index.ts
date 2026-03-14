export type { LayoutMode, LayoutResult, LayoutConfig } from './types';

import type { LayoutMode, LayoutConfig, LayoutResult } from './types';
import { circleLayout } from './circle';
import { forceLayout } from './force';
import { dagLayout } from './dag';
import { clusteredSubnetLayout } from './clustered-subnet';

/**
 * Compute layout positions for the given mode.
 * Falls back to circle layout on any error.
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
    // Safety fallback
    return circleLayout(config);
  }
}

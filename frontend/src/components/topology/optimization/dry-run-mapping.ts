import type { OptimizedEdge } from './types';

/** 簇节点的 dry-run 状态 */
export type ClusterDryRunStatus =
  | 'fully-removed'      // 所有成员都被移除
  | 'partial-removed'    // 部分成员被移除
  | 'partial-affected'   // 部分成员受波及
  | 'none';              // 无影响

export interface MappedDryRunSets {
  /** 映射后的被移除节点 ID（含簇 ID） */
  mappedRemovedNodeIds: Set<string>;
  /** 映射后的受波及节点 ID（含簇 ID） */
  mappedAffectedNodeIds: Set<string>;
  /** 映射后的被移除边 ID（含合并边 ID） */
  mappedRemovedEdgeIds: Set<string>;
  /** 映射后的受波及边 ID（含合并边 ID） */
  mappedAffectedEdgeIds: Set<string>;
  /** 簇 ID → dry-run 状态 */
  clusterDryRunStatus: Map<string, ClusterDryRunStatus>;
}

/**
 * 将原始 dry-run 影响集合映射到优化后的图。
 *
 * 节点映射：
 *   - 原始节点属于未展开簇 → 将簇 ID 加入对应集合
 *   - 原始节点不属于簇（或簇已展开）→ 保留原始 ID
 *
 * 边映射：
 *   - 通过合并边的 mergedEdgeIds 反查原始边的影响状态
 *
 * @param nodeToClusterMap  原始节点 ID → 簇 ID 映射
 * @param optimizedEdges    优化后的边列表
 * @param removedNodeIds    原始被移除节点 ID 集合
 * @param affectedNodeIds   原始受波及节点 ID 集合
 * @param removedEdgeIds    原始被移除边 ID 集合
 * @param affectedEdgeIds   原始受波及边 ID 集合
 */
export function mapDryRunSets(
  nodeToClusterMap: Map<string, string>,
  optimizedEdges: OptimizedEdge[],
  removedNodeIds?: Set<string>,
  affectedNodeIds?: Set<string>,
  removedEdgeIds?: Set<string>,
  affectedEdgeIds?: Set<string>,
): MappedDryRunSets {
  const mappedRemovedNodeIds = new Set<string>();
  const mappedAffectedNodeIds = new Set<string>();
  const mappedRemovedEdgeIds = new Set<string>();
  const mappedAffectedEdgeIds = new Set<string>();

  // 统计每个簇的影响情况
  const clusterRemovedCount = new Map<string, number>();
  const clusterAffectedCount = new Map<string, number>();
  const clusterTotalCount = new Map<string, number>();

  // 初始化簇计数
  for (const [_nodeId, clusterId] of nodeToClusterMap) {
    clusterTotalCount.set(clusterId, (clusterTotalCount.get(clusterId) ?? 0) + 1);
  }

  // 节点映射
  if (removedNodeIds) {
    for (const nodeId of removedNodeIds) {
      const clusterId = nodeToClusterMap.get(nodeId);
      if (clusterId) {
        mappedRemovedNodeIds.add(clusterId);
        clusterRemovedCount.set(clusterId, (clusterRemovedCount.get(clusterId) ?? 0) + 1);
      } else {
        mappedRemovedNodeIds.add(nodeId);
      }
    }
  }

  if (affectedNodeIds) {
    for (const nodeId of affectedNodeIds) {
      const clusterId = nodeToClusterMap.get(nodeId);
      if (clusterId) {
        mappedAffectedNodeIds.add(clusterId);
        clusterAffectedCount.set(clusterId, (clusterAffectedCount.get(clusterId) ?? 0) + 1);
      } else {
        mappedAffectedNodeIds.add(nodeId);
      }
    }
  }

  // 边映射：通过 mergedEdgeIds 反查
  if (removedEdgeIds || affectedEdgeIds) {
    for (const edge of optimizedEdges) {
      if (removedEdgeIds) {
        const hasRemoved = edge.mergedEdgeIds.some(id => removedEdgeIds.has(id));
        if (hasRemoved) mappedRemovedEdgeIds.add(edge.id);
      }
      if (affectedEdgeIds) {
        const hasAffected = edge.mergedEdgeIds.some(id => affectedEdgeIds.has(id));
        if (hasAffected) mappedAffectedEdgeIds.add(edge.id);
      }
    }
  }

  // 计算簇级 dry-run 状态
  const clusterDryRunStatus = new Map<string, ClusterDryRunStatus>();
  for (const [clusterId, total] of clusterTotalCount) {
    const removed = clusterRemovedCount.get(clusterId) ?? 0;
    const affected = clusterAffectedCount.get(clusterId) ?? 0;

    if (removed >= total) {
      clusterDryRunStatus.set(clusterId, 'fully-removed');
    } else if (removed > 0) {
      clusterDryRunStatus.set(clusterId, 'partial-removed');
    } else if (affected > 0) {
      clusterDryRunStatus.set(clusterId, 'partial-affected');
    } else {
      clusterDryRunStatus.set(clusterId, 'none');
    }
  }

  return {
    mappedRemovedNodeIds,
    mappedAffectedNodeIds,
    mappedRemovedEdgeIds,
    mappedAffectedEdgeIds,
    clusterDryRunStatus,
  };
}

"""
统一特征编排管道。
协调 flow 统计特征、规则语义特征、图结构特征的提取与合并，
输出供 SupervisedRanker 使用的统一特征矩阵。
"""

import numpy as np

from app.core.logging import get_logger
from app.services.features.service import FeaturesService
from app.services.detection.rule_enricher import RuleEnricher
from app.services.detection.graph_feature_builder import GraphFeatureBuilder

logger = get_logger(__name__)

# 用于 Layer 3 的 flow 统计特征子集（从 FeaturesService.FEATURE_NAMES 中选取数值型）
_FLOW_STAT_FEATURE_NAMES: list[str] = [
    name for name in FeaturesService.FEATURE_NAMES
    if name != "dst_port_bucket"  # 排除分类型特征
]


class FeaturePipeline:
    """
    特征编排器：将三类特征合并为统一特征向量。
    特征顺序：flow 统计特征 + baseline_score + 规则语义特征 + 图结构特征。
    使用 numpy 预分配矩阵，避免逐行 append。
    """

    def __init__(self):
        self._flow_feature_names = list(_FLOW_STAT_FEATURE_NAMES)
        self._rule_feature_names = list(RuleEnricher.RULE_FEATURE_NAMES)
        self._graph_feature_names = list(GraphFeatureBuilder.GRAPH_FEATURE_NAMES)
        self._all_names = (
            self._flow_feature_names
            + ["baseline_score"]
            + self._rule_feature_names
            + self._graph_feature_names
        )
        self._n_features = len(self._all_names)

    def get_all_feature_names(self) -> list[str]:
        """返回完整特征名列表（用于训练和推理对齐）。"""
        return list(self._all_names)

    def build_feature_matrix(
        self, flows: list[dict]
    ) -> tuple[list[str], list[list[float]]]:
        """
        构建完整特征矩阵（numpy 预分配，批量填充）。

        参数：
            flows: 已完成三层特征提取的流字典列表
        返回：
            (feature_names, matrix_rows)
        """
        n = len(flows)
        m = self._n_features
        matrix = np.zeros((n, m), dtype=np.float64)

        n_flow = len(self._flow_feature_names)
        n_rule = len(self._rule_feature_names)
        n_graph = len(self._graph_feature_names)
        col_baseline = n_flow
        col_rule_start = n_flow + 1
        col_graph_start = col_rule_start + n_rule

        # 批量提取——仍需遍历 flows 做 dict 查找，但写入预分配数组避免 append 开销
        for i, flow in enumerate(flows):
            features = flow.get("features", {})
            det = flow.get("_detection", {})
            rule_features = det.get("rule_features", {})
            graph_features = det.get("graph_features", {})

            # flow 统计特征
            for j, name in enumerate(self._flow_feature_names):
                val = features.get(name, 0)
                if isinstance(val, str):
                    val = hash(val) % 10
                matrix[i, j] = float(val)

            # baseline_score
            matrix[i, col_baseline] = float(det.get("baseline_score", 0.0))

            # 规则语义特征
            for j, name in enumerate(self._rule_feature_names):
                matrix[i, col_rule_start + j] = float(rule_features.get(name, 0.0))

            # 图结构特征
            for j, name in enumerate(self._graph_feature_names):
                matrix[i, col_graph_start + j] = float(graph_features.get(name, 0.0))

        logger.info(
            "FeaturePipeline 构建完成: %d 样本 × %d 特征",
            n, m,
        )
        # 返回 list[list[float]] 保持接口兼容（下游 np.array() 转换时零拷贝）
        return list(self._all_names), matrix.tolist()

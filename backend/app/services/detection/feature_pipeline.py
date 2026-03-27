"""
统一特征编排管道。
协调 flow 统计特征、规则语义特征、图结构特征的提取与合并，
输出供 SupervisedRanker 使用的统一特征矩阵。
"""

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
    """

    def __init__(self):
        self._flow_feature_names = list(_FLOW_STAT_FEATURE_NAMES)
        self._rule_feature_names = list(RuleEnricher.RULE_FEATURE_NAMES)
        self._graph_feature_names = list(GraphFeatureBuilder.GRAPH_FEATURE_NAMES)

    def get_all_feature_names(self) -> list[str]:
        """返回完整特征名列表（用于训练和推理对齐）。"""
        return (
            self._flow_feature_names
            + ["baseline_score"]
            + self._rule_feature_names
            + self._graph_feature_names
        )

    def build_feature_matrix(
        self, flows: list[dict]
    ) -> tuple[list[str], list[list[float]]]:
        """
        构建完整特征矩阵。

        要求 flows 已经过 BaselineDetector、RuleEnricher、GraphFeatureBuilder 处理，
        即 flow["_detection"] 中包含 baseline_score、rule_features、graph_features。

        参数：
            flows: 已完成三层特征提取的流字典列表
        返回：
            (feature_names, matrix_rows)
            feature_names: 特征名列表
            matrix_rows: 每条 flow 对应一行特征值
        """
        feature_names = self.get_all_feature_names()
        matrix: list[list[float]] = []

        for flow in flows:
            row: list[float] = []
            features = flow.get("features", {})
            det = flow.get("_detection", {})
            rule_features = det.get("rule_features", {})
            graph_features = det.get("graph_features", {})

            # ── flow 统计特征 ──
            for name in self._flow_feature_names:
                val = features.get(name, 0)
                if isinstance(val, str):
                    val = hash(val) % 10  # 与 DetectionService 保持一致的编码
                row.append(float(val))

            # ── baseline_score ──
            row.append(float(det.get("baseline_score", 0.0)))

            # ── 规则语义特征 ──
            for name in self._rule_feature_names:
                row.append(float(rule_features.get(name, 0.0)))

            # ── 图结构特征 ──
            for name in self._graph_feature_names:
                row.append(float(graph_features.get(name, 0.0)))

            matrix.append(row)

        logger.info(
            "FeaturePipeline 构建完成: %d 样本 × %d 特征",
            len(matrix),
            len(feature_names),
        )
        return feature_names, matrix

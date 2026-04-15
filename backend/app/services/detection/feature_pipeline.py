import numpy as np

from app.core.logging import get_logger
from app.services.detection.graph_feature_builder import GraphFeatureBuilder
from app.services.detection.rule_enricher import RuleEnricher
from app.services.features.service import FeaturesService


_FLOW_STAT_FEATURE_NAMES: list[str] = [
    name for name in FeaturesService.FEATURE_NAMES
    if name != "dst_port_bucket"
]

logger = get_logger(__name__)


class FeaturePipeline:
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
        return list(self._all_names)

    def build_feature_matrix(
        self, flows: list[dict]
    ) -> tuple[list[str], list[list[float]]]:
        n = len(flows)
        m = self._n_features
        matrix = np.zeros((n, m), dtype=np.float64)

        n_flow = len(self._flow_feature_names)
        n_rule = len(self._rule_feature_names)
        col_baseline = n_flow
        col_rule_start = n_flow + 1
        col_graph_start = col_rule_start + n_rule

        for i, flow in enumerate(flows):
            features = flow.get("features", {})
            det = flow.get("_detection", {})
            rule_features = det.get("rule_features", {})
            graph_features = det.get("graph_features", {})

            for j, name in enumerate(self._flow_feature_names):
                val = features.get(name, 0)
                if isinstance(val, str):
                    val = hash(val) % 10
                matrix[i, j] = float(val)

            matrix[i, col_baseline] = float(det.get("baseline_score", 0.0))

            for j, name in enumerate(self._rule_feature_names):
                matrix[i, col_rule_start + j] = float(rule_features.get(name, 0.0))

            for j, name in enumerate(self._graph_feature_names):
                matrix[i, col_graph_start + j] = float(graph_features.get(name, 0.0))

        logger.info("FeaturePipeline 构建完成: %d 样本 × %d 特征", n, m)
        return list(self._all_names), matrix.tolist()

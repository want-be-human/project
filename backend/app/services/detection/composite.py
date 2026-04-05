"""
复合检测服务 — 3层架构编排器。
作为 DetectionService 的升级替代，对外暴露相同的 score_flows 接口。

3层架构：
  Layer 1: BaselineDetector（IsolationForest 基线打分）
  Layer 2: RuleEnricher（规则特征增强）
  Layer 3: SupervisedRanker（监督/半监督最终分类）

中间层：
  GraphFeatureBuilder（图结构特征提取）
  FeaturePipeline（统一特征编排）
"""

from app.core.logging import get_logger
from app.services.detection.baseline_detector import BaselineDetector
from app.services.detection.rule_enricher import RuleEnricher
from app.services.detection.graph_feature_builder import GraphFeatureBuilder
from app.services.detection.feature_pipeline import FeaturePipeline
from app.services.detection.supervised_ranker import SupervisedRanker

logger = get_logger(__name__)

# ── 模块级单例（避免每次处理 PCAP 重新加载模型）──
_singleton: "CompositeDetectionService | None" = None


def get_composite_detector() -> "CompositeDetectionService":
    """获取 CompositeDetectionService 单例（懒加载，首次调用时加载模型）。"""
    global _singleton
    if _singleton is None:
        _singleton = CompositeDetectionService(mode="persisted")
    return _singleton


class CompositeDetectionService:
    """
    3层复合异常检测服务。
    对外接口与 DetectionService.score_flows() 兼容。
    """

    def __init__(self, mode: str = "persisted"):
        """
        初始化复合检测服务。

        参数：
            mode: "persisted"（加载离线模型）或 "runtime"/"fallback"
        """
        self.baseline = BaselineDetector(mode=mode)
        self.rule_enricher = RuleEnricher()
        self.graph_builder = GraphFeatureBuilder()
        self.feature_pipeline = FeaturePipeline()
        self.ranker = SupervisedRanker(mode=mode)

        logger.info(
            "CompositeDetectionService 初始化完成: baseline=%s, ranker=%s",
            self.baseline.mode,
            self.ranker.mode,
        )

    def score_flows(self, flows: list[dict]) -> list[dict]:
        """
        3层复合评分。兼容 DetectionService.score_flows 的调用签名。

        流程：
          1. Layer 1: baseline_score（IsolationForest）
          2. Layer 2: rule_score + rule_features（RuleEnricher）
          3. GraphFeatureBuilder: graph_features + graph_score
          4. FeaturePipeline: 合并特征矩阵
          5. Layer 3: final_score + final_label（SupervisedRanker）
          6. 向后兼容映射: anomaly_score = final_score

        参数：
            flows: 包含 features 字段的流字典列表
        返回：
            已填充 anomaly_score 和扩展检测字段的流列表
        """
        if not flows:
            return flows

        logger.info("CompositeDetectionService 开始处理 %d 条流", len(flows))

        # ── Layer 1: 基线检测 ──
        flows = self.baseline.score(flows)

        # ── Layer 2: 规则增强 ──
        flows = self.rule_enricher.enrich(flows)

        # ── 图特征构建 ──
        flows = self.graph_builder.build_and_extract(flows)

        # ── 特征矩阵合并 ──
        feature_names, feature_matrix = self.feature_pipeline.build_feature_matrix(flows)

        # ── Layer 3: 最终排序/分类 ──
        flows = self.ranker.predict(flows, feature_matrix, feature_names)

        # ── 向后兼容映射 ──
        flows = self._write_back_compat(flows)

        logger.info(
            "CompositeDetectionService 完成: %d 条流, max_final=%.3f",
            len(flows),
            max((f.get("anomaly_score", 0) for f in flows), default=0),
        )
        return flows

    def _write_back_compat(self, flows: list[dict]) -> list[dict]:
        """
        向后兼容：
          - anomaly_score = final_score（AlertingService 读取此字段）
          - 扩展字段写入 features dict（持久化到 DB 的 features JSON 列）
        """
        for flow in flows:
            det = flow.get("_detection", {})

            # 核心兼容映射
            flow["anomaly_score"] = det.get(
                "final_score", det.get("baseline_score", 0.5)
            )

            # 扩展字段写入 features（供前端和后续分析使用）
            features = flow.setdefault("features", {})
            features["baseline_score"] = det.get("baseline_score")
            features["rule_score"] = det.get("rule_score")
            features["graph_score"] = det.get("graph_score")
            features["final_score"] = det.get("final_score")
            features["final_label"] = det.get("final_label")

            # 将 explanation 精简后写入（避免 JSON 过大）
            explanation = det.get("explanation", {})
            features["detection_explanation"] = {
                "mode": explanation.get("mode", "unknown"),
                "rule_type": explanation.get("rule_type", "anomaly"),
                "rule_reasons": explanation.get("rule_reasons", []),
                "layer_contributions": explanation.get("layer_contributions", {}),
                "guard_triggers": explanation.get("guard_triggers", []),
                "final_decision_reason": explanation.get("final_decision_reason", ""),
            }

            # 写入更多检测层字段，供下游 AlertingService 消费
            features["rule_type"] = det.get("rule_type")
            features["rule_reasons"] = det.get("rule_reasons", [])
            features["detection_mode"] = explanation.get("mode", "unknown")
            features["guard_triggers"] = explanation.get("guard_triggers", [])

        return flows

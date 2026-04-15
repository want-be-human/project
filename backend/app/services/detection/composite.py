import time as _time

from app.core.logging import get_logger
from app.services.detection.baseline_detector import BaselineDetector
from app.services.detection.feature_pipeline import FeaturePipeline
from app.services.detection.graph_feature_builder import GraphFeatureBuilder
from app.services.detection.rule_enricher import RuleEnricher
from app.services.detection.supervised_ranker import SupervisedRanker

logger = get_logger(__name__)

_singleton: "CompositeDetectionService | None" = None


def get_composite_detector() -> "CompositeDetectionService":
    global _singleton
    if _singleton is None:
        _singleton = CompositeDetectionService(mode="persisted")
    return _singleton


class CompositeDetectionService:
    def __init__(self, mode: str = "persisted"):
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
        if not flows:
            return flows

        logger.info("CompositeDetectionService 开始处理 %d 条流", len(flows))

        t0 = _time.monotonic()
        flows = self.baseline.score(flows)
        logger.info("  Layer 1 (baseline): %.1fs", _time.monotonic() - t0)

        t0 = _time.monotonic()
        flows = self.rule_enricher.enrich(flows)
        logger.info("  Layer 2 (rule): %.1fs", _time.monotonic() - t0)

        t0 = _time.monotonic()
        flows = self.graph_builder.build_and_extract(flows)
        logger.info("  Graph features: %.1fs", _time.monotonic() - t0)

        t0 = _time.monotonic()
        feature_names, feature_matrix = self.feature_pipeline.build_feature_matrix(flows)
        logger.info("  Feature matrix: %.1fs", _time.monotonic() - t0)

        t0 = _time.monotonic()
        flows = self.ranker.predict(flows, feature_matrix, feature_names)
        logger.info("  Layer 3 (ranker): %.1fs", _time.monotonic() - t0)

        flows = self._write_back_compat(flows)

        logger.info(
            "CompositeDetectionService 完成: %d 条流, max_final=%.3f",
            len(flows),
            max((f.get("anomaly_score", 0) for f in flows), default=0),
        )
        return flows

    def _write_back_compat(self, flows: list[dict]) -> list[dict]:
        for flow in flows:
            det = flow.get("_detection", {})

            flow["anomaly_score"] = det.get(
                "final_score", det.get("baseline_score", 0.5)
            )

            features = flow.setdefault("features", {})
            features["baseline_score"] = det.get("baseline_score")
            features["rule_score"] = det.get("rule_score")
            features["graph_score"] = det.get("graph_score")
            features["final_score"] = det.get("final_score")
            features["final_label"] = det.get("final_label")

            explanation = det.get("explanation", {})
            features["detection_explanation"] = {
                "mode": explanation.get("mode", "unknown"),
                "rule_type": explanation.get("rule_type", "anomaly"),
                "rule_reasons": explanation.get("rule_reasons", []),
                "layer_contributions": explanation.get("layer_contributions", {}),
                "guard_triggers": explanation.get("guard_triggers", []),
                "final_decision_reason": explanation.get("final_decision_reason", ""),
            }

            features["rule_type"] = det.get("rule_type")
            features["rule_reasons"] = det.get("rule_reasons", [])
            features["detection_mode"] = explanation.get("mode", "unknown")
            features["guard_triggers"] = explanation.get("guard_triggers", [])

        return flows

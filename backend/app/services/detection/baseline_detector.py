"""Layer 1 baseline detector: delegates to DetectionService (IsolationForest)."""

from app.core.logging import get_logger
from app.services.detection.service import DetectionService

logger = get_logger(__name__)


class BaselineDetector:
    def __init__(self, mode: str = "persisted", model_params: dict | None = None):
        self._detector = DetectionService(model_params=model_params, mode=mode)
        self.mode = self._detector.mode
        logger.info("BaselineDetector 初始化完成，模式=%s", self.mode)

    def score(self, flows: list[dict]) -> list[dict]:
        if not flows:
            return flows

        flows = self._detector.score_flows(flows)

        for flow in flows:
            det = flow.setdefault("_detection", {})
            det["baseline_score"] = flow.get("anomaly_score", 0.5)

        logger.info(
            "BaselineDetector 评分完成: %d 条流, max_baseline=%.3f",
            len(flows),
            max((f.get("_detection", {}).get("baseline_score", 0) for f in flows), default=0),
        )
        return flows

    def score_with_fitted(self, flows: list[dict]) -> list[dict]:
        if not flows:
            return flows

        if self._detector.model is None or self._detector.meta is None:
            logger.warning("score_with_fitted: 无已拟合模型，回退到 score()")
            return self.score(flows)

        original_mode = self._detector.mode
        self._detector.mode = "persisted"
        try:
            flows = self._detector.score_flows(flows)
        finally:
            self._detector.mode = original_mode

        for flow in flows:
            det = flow.setdefault("_detection", {})
            det["baseline_score"] = flow.get("anomaly_score", 0.5)

        logger.info(
            "BaselineDetector(fitted) 评分完成: %d 条流, max_baseline=%.3f",
            len(flows),
            max((f.get("_detection", {}).get("baseline_score", 0) for f in flows), default=0),
        )
        return flows

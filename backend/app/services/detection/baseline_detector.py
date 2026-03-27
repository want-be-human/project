"""
Layer 1: 基线异常检测器。
委托现有 DetectionService（IsolationForest），输出 baseline_score。
职责：
  - baseline anomaly detector
  - 候选异常流排序器
  - 弱监督前置筛选器
"""

from app.core.logging import get_logger
from app.services.detection.service import DetectionService

logger = get_logger(__name__)


class BaselineDetector:
    """
    IsolationForest 基线检测器。
    通过委托模式复用 DetectionService 的全部逻辑，零代码重复。
    """

    def __init__(self, mode: str = "persisted", model_params: dict | None = None):
        """
        初始化基线检测器。

        参数：
            mode: "persisted"（加载离线模型）或 "runtime"（当前批次 fit）
            model_params: IsolationForest 参数（仅 runtime 模式使用）
        """
        self._detector = DetectionService(model_params=model_params, mode=mode)
        self.mode = self._detector.mode
        logger.info("BaselineDetector 初始化完成，模式=%s", self.mode)

    def score(self, flows: list[dict]) -> list[dict]:
        """
        为每条 flow 计算 baseline_score。

        将 DetectionService 输出的 anomaly_score 复制到
        flow["_detection"]["baseline_score"]，保持原始 anomaly_score 不变。

        参数：
            flows: 包含 features 字段的流字典列表
        返回：
            已填充 _detection.baseline_score 的流列表
        """
        if not flows:
            return flows

        # 委托给现有 DetectionService
        flows = self._detector.score_flows(flows)

        # 将 anomaly_score 映射到 _detection 命名空间
        for flow in flows:
            det = flow.setdefault("_detection", {})
            det["baseline_score"] = flow.get("anomaly_score", 0.5)

        logger.info(
            "BaselineDetector 评分完成: %d 条流, max_baseline=%.3f",
            len(flows),
            max((f.get("_detection", {}).get("baseline_score", 0) for f in flows), default=0),
        )
        return flows

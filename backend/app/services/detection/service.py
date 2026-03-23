"""
检测服务。
使用 IsolationForest 实现基线异常检测。
支持两种模式：
  - persisted（默认）：加载离线训练好的模型做推理，跨批次分数可比
  - runtime：兼容旧逻辑，对当前批次现场 fit
"""

import json
from pathlib import Path

import numpy as np

from app.core.config import BASE_DIR
from app.core.logging import get_logger

logger = get_logger(__name__)

# 模型文件路径
MODEL_DIR = BASE_DIR / "models"
MODEL_PATH = MODEL_DIR / "flow_iforest.joblib"
META_PATH = MODEL_DIR / "flow_iforest.meta.json"


class DetectionService:
    """
    异常检测服务。

    遵循 DOC B B4.4 规范。
    使用 IsolationForest 进行基线检测。
    """

    # 默认特征集合（runtime 模式使用；persisted 模式会被 metadata 覆盖）
    DEFAULT_FEATURE_NAMES = [
        "total_packets",
        "total_bytes",
        "bytes_per_packet",
        "flow_duration_ms",
        "fwd_ratio_packets",
        "fwd_ratio_bytes",
        "iat_mean_ms",
        "iat_std_ms",
        "syn_count",
        "ack_count",
        "fin_count",
        "rst_count",
        "syn_ratio",
        "rst_ratio",
        "avg_pkt_size_fwd",
        "avg_pkt_size_bwd",
        "is_tcp",
        "is_udp",
    ]

    def __init__(self, model_params: dict | None = None, mode: str = "persisted"):
        self.model_params = model_params or {}
        self.model = None
        self.meta = None
        self.feature_names = list(self.DEFAULT_FEATURE_NAMES)

        if mode == "persisted":
            # 尝试加载持久化模型；失败则降级为 runtime
            if self._load_model():
                self.mode = "persisted"
            else:
                self.mode = "runtime"
        else:
            self.mode = "runtime"

    def _load_model(self) -> bool:
        """
        加载持久化的 IsolationForest 模型和 metadata。

        返回：
            True 表示加载成功，False 表示需要降级到 runtime 模式。
        """
        try:
            import joblib

            if not MODEL_PATH.exists() or not META_PATH.exists():
                logger.warning(
                    "持久化模型文件不存在 (%s)，降级为 runtime 模式", MODEL_PATH
                )
                return False

            # 加载 metadata 并校验
            meta = json.loads(META_PATH.read_text(encoding="utf-8"))
            feature_names = meta.get("feature_names")
            normalization = meta.get("normalization", {})

            if not feature_names or not isinstance(feature_names, list):
                logger.warning("metadata 中 feature_names 无效，降级为 runtime 模式")
                return False
            if "p5" not in normalization or "p95" not in normalization:
                logger.warning("metadata 中缺少归一化参数，降级为 runtime 模式")
                return False

            # 加载模型
            self.model = joblib.load(MODEL_PATH)
            self.meta = meta
            # 用训练时的特征顺序覆盖，保证推理一致性
            self.feature_names = feature_names

            # sklearn 版本校验（仅警告）
            try:
                import sklearn
                if meta.get("sklearn_version") != sklearn.__version__:
                    logger.warning(
                        "sklearn 版本不一致：训练=%s, 当前=%s",
                        meta.get("sklearn_version"),
                        sklearn.__version__,
                    )
            except ImportError:
                pass

            logger.info(
                "已加载持久化模型 (训练样本=%d, 特征=%d)",
                meta.get("training_samples", 0),
                len(feature_names),
            )
            return True

        except Exception as e:
            logger.warning("加载持久化模型失败: %s，降级为 runtime 模式", e)
            return False

    def score_flows(self, flows: list[dict]) -> list[dict]:
        """
        计算流量的异常分数。

        参数：
            flows: 包含特征字段的流字典列表

        返回：
            已填充 anomaly_score 的原始流列表
        """
        if not flows:
            return flows

        # 样本数不足时给默认分数
        if len(flows) < 2 and self.mode == "runtime":
            for flow in flows:
                flow["anomaly_score"] = 0.5
            return flows

        if self.mode == "persisted":
            return self._score_persisted(flows)
        return self._score_runtime(flows)

    def _score_persisted(self, flows: list[dict]) -> list[dict]:
        """使用持久化模型做推理（不执行 fit）。"""
        try:
            X = self._flows_to_matrix(flows)

            # 校验特征维度与训练时一致
            expected_cols = len(self.feature_names)
            if X.shape[1] != expected_cols:
                logger.error(
                    "特征维度不匹配：期望 %d, 实际 %d，降级为 runtime",
                    expected_cols,
                    X.shape[1],
                )
                return self._score_runtime(flows)

            # 使用训练好的模型评分（禁止 fit）
            raw_scores = self.model.score_samples(X)
            neg_scores = -raw_scores

            # 使用训练集的 p5/p95 做归一化，保证跨批次可比
            p5 = self.meta["normalization"]["p5"]
            p95 = self.meta["normalization"]["p95"]
            clipped = np.clip(neg_scores, p5, p95)

            if p95 > p5:
                normalized = (clipped - p5) / (p95 - p5)
            else:
                normalized = np.full_like(raw_scores, 0.5)

            for i, flow in enumerate(flows):
                flow["anomaly_score"] = float(normalized[i])

            logger.info(
                "持久化模型推理完成: %d 条流, max=%.3f",
                len(flows),
                normalized.max(),
            )

        except Exception as e:
            logger.error("持久化模型推理失败: %s，降级为 runtime", e)
            return self._score_runtime(flows)

        return flows

    def _score_runtime(self, flows: list[dict]) -> list[dict]:
        """兼容旧逻辑：对当前批次现场 fit IsolationForest。"""
        try:
            from sklearn.ensemble import IsolationForest

            X = self._flows_to_matrix(flows)

            if X.shape[0] < 2:
                for flow in flows:
                    flow["anomaly_score"] = 0.5
                return flows

            contamination = self.model_params.get("contamination", 0.1)
            n_estimators = self.model_params.get("n_estimators", 100)

            model = IsolationForest(
                contamination=contamination,
                n_estimators=n_estimators,
                random_state=42,
            )
            model.fit(X)

            raw_scores = model.score_samples(X)
            neg_scores = -raw_scores

            p5, p95 = np.percentile(neg_scores, [5, 95])
            clipped = np.clip(neg_scores, p5, p95)

            if p95 > p5:
                normalized = (clipped - p5) / (p95 - p5)
            else:
                normalized = np.full_like(raw_scores, 0.5)

            for i, flow in enumerate(flows):
                flow["anomaly_score"] = float(normalized[i])

            logger.info(
                "runtime 异常检测完成: %d 条流, p5=%.4f, p95=%.4f, max=%.3f",
                len(flows),
                p5,
                p95,
                normalized.max(),
            )

        except ImportError:
            logger.warning("sklearn 未安装，使用随机分数")
            for flow in flows:
                flow["anomaly_score"] = np.random.random() * 0.5
        except Exception as e:
            logger.error("runtime 异常检测失败: %s", e)
            for flow in flows:
                flow["anomaly_score"] = 0.5

        return flows

    def _flows_to_matrix(self, flows: list[dict]) -> np.ndarray:
        """将流量列表转换为特征矩阵。"""
        rows = []

        for flow in flows:
            features = flow.get("features", {})
            row = []

            for name in self.feature_names:
                value = features.get(name, 0)
                # 处理非数值特征
                if isinstance(value, str):
                    value = hash(value) % 10  # 简单编码
                row.append(float(value))

            rows.append(row)

        return np.array(rows)

    def get_top_anomalous_flows(
        self,
        flows: list[dict],
        threshold: float = 0.7,
        limit: int = 10,
    ) -> list[dict]:
        """
        获取超过阈值的高异常流量。

        参数：
            flows: 已打分的流列表
            threshold: 最小异常分数阈值
            limit: 返回的最大流数量

        返回：
            按分数降序排列的异常流列表
        """
        anomalous = [f for f in flows if (f.get("anomaly_score") or 0) >= threshold]
        anomalous.sort(key=lambda x: x.get("anomaly_score", 0), reverse=True)
        return anomalous[:limit]

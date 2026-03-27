"""
Layer 3: 监督/半监督最终排序器。
支持两种模式：
  - persisted：加载训练好的 LightGBM/XGBoost 模型做推理
  - fallback：无监督模型时使用加权融合 baseline_score + rule_score + graph_score
预留半监督（PU Learning / 伪标签）训练接口。
"""

import json
from pathlib import Path

import numpy as np

from app.core.config import BASE_DIR
from app.core.logging import get_logger
from app.core.scoring_policy import (
    COMPOSITE_DETECTION_WEIGHTS,
    COMPOSITE_DETECTION_THRESHOLDS,
)

logger = get_logger(__name__)

# 模型文件路径
MODEL_DIR = BASE_DIR / "models"
RANKER_MODEL_PATH = MODEL_DIR / "composite_ranker.joblib"
RANKER_META_PATH = MODEL_DIR / "composite_ranker.meta.json"


class SupervisedRanker:
    """
    最终模型：基于聚合特征输出 final_score 和 final_label。
    支持 persisted（加载训练好的模型）和 fallback（加权融合）两种模式。
    """

    def __init__(self, mode: str = "persisted"):
        """
        初始化排序器。

        参数：
            mode: "persisted"（加载模型）或 "fallback"（加权融合）
        """
        self.model = None
        self.meta = None
        self.mode = mode
        self.threshold = COMPOSITE_DETECTION_THRESHOLDS["anomaly_threshold"]

        if mode == "persisted":
            if self._load_model():
                self.mode = "persisted"
            else:
                self.mode = "fallback"
                logger.info("SupervisedRanker 降级为 fallback 模式（加权融合）")
        else:
            self.mode = "fallback"

        logger.info("SupervisedRanker 初始化完成，模式=%s", self.mode)

    def _load_model(self) -> bool:
        """加载持久化的监督模型和 metadata。"""
        try:
            import joblib

            if not RANKER_MODEL_PATH.exists() or not RANKER_META_PATH.exists():
                logger.info("监督模型文件不存在 (%s)，将使用 fallback 模式", RANKER_MODEL_PATH)
                return False

            meta = json.loads(RANKER_META_PATH.read_text(encoding="utf-8"))
            self.model = joblib.load(RANKER_MODEL_PATH)
            self.meta = meta
            self.threshold = meta.get("threshold", self.threshold)

            logger.info(
                "已加载监督模型: type=%s, 特征=%d, 阈值=%.3f",
                meta.get("model_type", "unknown"),
                len(meta.get("feature_names", [])),
                self.threshold,
            )
            return True

        except Exception as e:
            logger.warning("加载监督模型失败: %s", e)
            return False

    def predict(
        self,
        flows: list[dict],
        feature_matrix: list[list[float]],
        feature_names: list[str],
    ) -> list[dict]:
        """
        为每条 flow 计算 final_score 和 final_label。

        写入：
            flow["_detection"]["final_score"]   — 最终分数 0-1
            flow["_detection"]["final_label"]   — 最终标签
            flow["_detection"]["explanation"]   — 可解释性输出

        参数：
            flows: 已完成前两层评分的流字典列表
            feature_matrix: 统一特征矩阵
            feature_names: 特征名列表
        返回：
            已填充最终评分的流列表
        """
        if not flows:
            return flows

        if self.mode == "persisted" and self.model is not None:
            return self._predict_persisted(flows, feature_matrix, feature_names)
        return self._predict_fallback(flows, feature_names)

    def _predict_persisted(
        self,
        flows: list[dict],
        feature_matrix: list[list[float]],
        feature_names: list[str],
    ) -> list[dict]:
        """使用持久化模型预测。"""
        try:
            X = np.array(feature_matrix)

            # 校验特征维度
            expected_features = self.meta.get("feature_names", [])
            if X.shape[1] != len(expected_features):
                logger.warning(
                    "特征维度不匹配：期望 %d, 实际 %d，降级为 fallback",
                    len(expected_features),
                    X.shape[1],
                )
                return self._predict_fallback(flows, feature_names)

            # 预测概率（取正类概率作为 final_score）
            if hasattr(self.model, "predict_proba"):
                proba = self.model.predict_proba(X)
                scores = proba[:, 1] if proba.shape[1] > 1 else proba[:, 0]
            else:
                # 回归模型或无 predict_proba 的模型
                scores = self.model.predict(X)
                scores = np.clip(scores, 0.0, 1.0)

            for i, flow in enumerate(flows):
                det = flow.setdefault("_detection", {})
                final_score = float(scores[i])
                det["final_score"] = round(final_score, 4)
                det["final_label"] = self._score_to_label(
                    final_score, det.get("rule_type", "anomaly")
                )
                det["explanation"] = self._build_explanation(
                    flow, feature_names, feature_matrix[i], "persisted"
                )

            logger.info(
                "SupervisedRanker(persisted) 预测完成: %d 条流, max=%.3f",
                len(flows),
                float(scores.max()),
            )

        except Exception as e:
            logger.error("监督模型预测失败: %s，降级为 fallback", e)
            return self._predict_fallback(flows, feature_names)

        return flows

    def _predict_fallback(
        self,
        flows: list[dict],
        feature_names: list[str],
    ) -> list[dict]:
        """
        无监督 fallback：加权融合 baseline_score、rule_score、graph_score。
        权重从 COMPOSITE_DETECTION_WEIGHTS 读取。
        """
        w = COMPOSITE_DETECTION_WEIGHTS

        for flow in flows:
            det = flow.setdefault("_detection", {})
            baseline = det.get("baseline_score", 0.0)
            rule = det.get("rule_score", 0.0)
            graph = det.get("graph_score", 0.0)

            final_score = (
                baseline * w["baseline_score"]
                + rule * w["rule_score"]
                + graph * w["graph_score"]
            )
            final_score = min(round(final_score, 4), 1.0)

            det["final_score"] = final_score
            det["final_label"] = self._score_to_label(
                final_score, det.get("rule_type", "anomaly")
            )
            det["explanation"] = self._build_explanation(
                flow, feature_names, [], "fallback"
            )

        logger.info(
            "SupervisedRanker(fallback) 融合完成: %d 条流, max=%.3f",
            len(flows),
            max((f.get("_detection", {}).get("final_score", 0) for f in flows), default=0),
        )
        return flows

    def _score_to_label(self, final_score: float, rule_type: str) -> str:
        """
        将 final_score 映射为最终标签。
        高于阈值时采用规则推断类型，低于阈值标记为 normal。
        """
        if final_score >= self.threshold:
            return rule_type if rule_type != "anomaly" else "anomaly"
        return "normal"

    def _build_explanation(
        self,
        flow: dict,
        feature_names: list[str],
        feature_values: list[float] | list,
        mode: str,
    ) -> dict:
        """
        生成单条 flow 的可解释性输出。
        包含各层贡献度、模式信息。
        """
        det = flow.get("_detection", {})
        explanation: dict = {
            "mode": mode,
            "layer_contributions": {
                "baseline_score": det.get("baseline_score", 0.0),
                "rule_score": det.get("rule_score", 0.0),
                "graph_score": det.get("graph_score", 0.0),
            },
            "rule_type": det.get("rule_type", "anomaly"),
            "rule_reasons": det.get("rule_reasons", []),
        }

        # 持久化模型模式下，尝试提取特征重要性
        if mode == "persisted" and feature_values and self.model is not None:
            importance = self._get_feature_importance(feature_names, feature_values)
            if importance:
                explanation["top_features"] = importance[:5]

        return explanation

    def _get_feature_importance(
        self,
        feature_names: list[str],
        feature_values: list[float],
    ) -> list[dict]:
        """
        获取特征重要性排序。
        优先使用模型内置 feature_importances_，否则用特征值绝对值近似。
        """
        try:
            if hasattr(self.model, "feature_importances_"):
                importances = self.model.feature_importances_
                pairs = list(zip(feature_names, importances, feature_values))
                pairs.sort(key=lambda x: abs(x[1]), reverse=True)
                return [
                    {"name": name, "importance": round(float(imp), 4), "value": round(float(val), 4)}
                    for name, imp, val in pairs[:10]
                ]
        except Exception:
            pass

        # 回退：按特征值绝对值排序
        if feature_values:
            pairs = list(zip(feature_names, feature_values))
            pairs.sort(key=lambda x: abs(x[1]), reverse=True)
            return [
                {"name": name, "value": round(float(val), 4)}
                for name, val in pairs[:5]
            ]
        return []

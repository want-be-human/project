"""
Layer 3 监督排序器。

支持：
- 持久化模式：加载已训练的分类器推断 final_score/final_label
- 降级模式：使用固定权重组合 baseline/rule/graph 分数
- 保护机制：防止强规则信号和多源一致性被监督模型覆盖
"""

import json
from pathlib import Path

import numpy as np

from app.core.config import BASE_DIR
from app.core.logging import get_logger
from app.core.scoring_policy import (
    COMPOSITE_DETECTION_THRESHOLDS,
    COMPOSITE_DETECTION_WEIGHTS,
    STRONG_RULE_TYPES,
    GUARD_RULE_FLOOR_THRESHOLD,
    GUARD_RULE_FLOOR_FACTOR,
    GUARD_CONSENSUS_BASELINE,
    GUARD_CONSENSUS_SECONDARY,
    GUARD_CONSENSUS_FLOOR,
)
from app.services.detection.model_compat import validate_sklearn_version

logger = get_logger(__name__)

MODEL_DIR = BASE_DIR / "models"
RANKER_MODEL_PATH = MODEL_DIR / "composite_ranker.joblib"
RANKER_META_PATH = MODEL_DIR / "composite_ranker.meta.json"


class SupervisedRanker:
    """基于复合特征向量的最终评分器。"""

    def __init__(self, mode: str = "persisted"):
        self.model = None
        self.meta = None
        self.mode = mode
        self.threshold = COMPOSITE_DETECTION_THRESHOLDS["anomaly_threshold"]

        if mode == "persisted":
            if self._load_model():
                self.mode = "persisted"
            else:
                self.mode = "fallback"
                logger.info("SupervisedRanker 已降级为 fallback 模式")
        else:
            self.mode = "fallback"

        logger.info("SupervisedRanker 初始化完成, 模式=%s", self.mode)

    def _load_model(self) -> bool:
        """加载持久化的监督模型和元数据。"""
        try:
            import joblib

            if not RANKER_MODEL_PATH.exists() or not RANKER_META_PATH.exists():
                logger.info(
                    "监督模型文件不存在 (%s)；使用 fallback 模式",
                    RANKER_MODEL_PATH,
                )
                return False

            meta = json.loads(RANKER_META_PATH.read_text(encoding="utf-8"))
            if not validate_sklearn_version(meta, "composite_ranker"):
                return False

            self.model = joblib.load(RANKER_MODEL_PATH)
            self.meta = meta
            self.threshold = meta.get("threshold", self.threshold)

            logger.info(
                "已加载监督模型: 类型=%s, 特征数=%d, 阈值=%.3f",
                meta.get("model_type", "unknown"),
                len(meta.get("feature_names", [])),
                float(self.threshold),
            )
            return True

        except Exception as exc:
            logger.warning("加载监督模型失败: %s", exc)
            return False

    def predict(
        self,
        flows: list[dict],
        feature_matrix: list[list[float]],
        feature_names: list[str],
    ) -> list[dict]:
        """计算每条流的 final_score/final_label。"""
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
        """使用持久化分类器进行推断。"""
        try:
            X = np.array(feature_matrix)
            expected_features = self.meta.get("feature_names", [])
            if X.shape[1] != len(expected_features):
                logger.warning(
                    "特征维度不匹配: 期望 %d, 实际 %d; 使用 fallback",
                    len(expected_features),
                    X.shape[1],
                )
                return self._predict_fallback(flows, feature_names)

            if hasattr(self.model, "predict_proba"):
                proba = self.model.predict_proba(X)
                scores = proba[:, 1] if proba.shape[1] > 1 else proba[:, 0]
            else:
                scores = self.model.predict(X)
                scores = np.clip(scores, 0.0, 1.0)

            base_mode = "persisted"

            for i, flow in enumerate(flows):
                det = flow.setdefault("_detection", {})
                raw_score = float(scores[i])

                # 应用保护机制
                guarded_score, guard_triggers = self._apply_guardrails(flow, raw_score)
                mode = f"guarded_{base_mode}" if guard_triggers else base_mode

                det["final_score"] = float(np.clip(guarded_score, 0.0, 1.0))
                det["final_label"] = self._score_to_label(
                    guarded_score, det.get("rule_type", "anomaly")
                )
                det["explanation"] = self._build_explanation(
                    flow, feature_names, feature_matrix[i], mode,
                    guard_triggers=guard_triggers,
                    original_score=raw_score if guard_triggers else None,
                )

            logger.info(
                "SupervisedRanker(persisted) 完成: %d 条流, 最大值=%.3f",
                len(flows),
                float(scores.max()),
            )
            return flows

        except Exception as exc:
            logger.error("监督推断失败: %s; 使用 fallback", exc)
            return self._predict_fallback(flows, feature_names)

    def _predict_fallback(
        self,
        flows: list[dict],
        feature_names: list[str],
    ) -> list[dict]:
        """降级模式：baseline_score、rule_score 和 graph_score 的加权融合。"""
        weights = COMPOSITE_DETECTION_WEIGHTS
        base_mode = "fallback"

        for flow in flows:
            det = flow.setdefault("_detection", {})
            baseline = det.get("baseline_score", 0.0)
            rule = det.get("rule_score", 0.0)
            graph = det.get("graph_score", 0.0)

            raw_score = (
                baseline * weights["baseline_score"]
                + rule * weights["rule_score"]
                + graph * weights["graph_score"]
            )
            raw_score = float(np.clip(raw_score, 0.0, 1.0))

            # 应用保护机制
            guarded_score, guard_triggers = self._apply_guardrails(flow, raw_score)
            mode = f"guarded_{base_mode}" if guard_triggers else base_mode

            det["final_score"] = guarded_score
            det["final_label"] = self._score_to_label(
                guarded_score, det.get("rule_type", "anomaly")
            )
            det["explanation"] = self._build_explanation(
                flow, feature_names, [], mode,
                guard_triggers=guard_triggers,
                original_score=raw_score if guard_triggers else None,
            )

        logger.info(
            "SupervisedRanker(fallback) 完成: %d 条流, 最大值=%.3f",
            len(flows),
            max((f.get("_detection", {}).get("final_score", 0) for f in flows), default=0),
        )
        return flows

    def _apply_guardrails(
        self, flow: dict, final_score: float,
    ) -> tuple[float, list[str]]:
        """
        应用保护逻辑，防止强规则信号或多源一致性被监督模型压制。

        Guard 1 — 强规则下限保护：
            当 rule_type 为强风险类型且 rule_score >= 阈值时，
            final_score 不得低于 rule_score × floor_factor。

        Guard 2 — 多源一致性保护：
            当 baseline_score 高，且 rule_score 或 graph_score 同时较高时，
            final_score 不得低于 consensus_floor。

        返回：(guarded_score, guard_triggers)
        """
        det = flow.get("_detection", {})
        guards: list[str] = []
        guarded = final_score

        rule_score = det.get("rule_score", 0.0)
        rule_type = det.get("rule_type", "anomaly")
        baseline = det.get("baseline_score", 0.0)
        graph = det.get("graph_score", 0.0)

        # Guard 1: 强规则下限
        if rule_type in STRONG_RULE_TYPES and rule_score >= GUARD_RULE_FLOOR_THRESHOLD:
            floor = rule_score * GUARD_RULE_FLOOR_FACTOR
            if final_score < floor:
                guarded = max(guarded, floor)
                guards.append(
                    f"rule_floor:{rule_type}(rule={rule_score:.2f},floor={floor:.2f})"
                )

        # Guard 2: 多源一致性
        if baseline >= GUARD_CONSENSUS_BASELINE:
            secondary = max(rule_score, graph)
            if secondary >= GUARD_CONSENSUS_SECONDARY and final_score < GUARD_CONSENSUS_FLOOR:
                guarded = max(guarded, GUARD_CONSENSUS_FLOOR)
                guards.append(
                    f"consensus(b={baseline:.2f},r={rule_score:.2f},g={graph:.2f})"
                )

        return float(np.clip(guarded, 0.0, 1.0)), guards

    def _score_to_label(self, final_score: float, rule_type: str) -> str:
        """将 final_score 映射为最终标签。"""
        if final_score >= self.threshold:
            return rule_type if rule_type != "anomaly" else "anomaly"
        return "normal"

    def _build_explanation(
        self,
        flow: dict,
        feature_names: list[str],
        feature_values: list[float] | list,
        mode: str,
        guard_triggers: list[str] | None = None,
        original_score: float | None = None,
    ) -> dict:
        """构建紧凑的逐流解释负载。"""
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

        # 保护机制信息
        if guard_triggers:
            explanation["guard_triggers"] = guard_triggers
            explanation["final_decision_reason"] = "guardrail_applied"
            if original_score is not None:
                explanation["original_score"] = round(original_score, 4)
        else:
            explanation["guard_triggers"] = []
            base = mode.replace("guarded_", "")
            explanation["final_decision_reason"] = (
                "model_decision" if base == "persisted" else "fallback_fusion"
            )

        if mode.endswith("persisted") and feature_values and self.model is not None:
            importance = self._get_feature_importance(feature_names, feature_values)
            if importance:
                explanation["top_features"] = importance[:5]

        return explanation

    def _get_feature_importance(
        self,
        feature_names: list[str],
        feature_values: list[float],
    ) -> list[dict]:
        """返回模型特征重要性（如果可用）。"""
        try:
            estimator = self.model
            if not hasattr(estimator, "feature_importances_") and hasattr(estimator, "estimator"):
                estimator = estimator.estimator
            if (
                not hasattr(estimator, "feature_importances_")
                and hasattr(self.model, "calibrated_classifiers_")
                and self.model.calibrated_classifiers_
            ):
                estimator = self.model.calibrated_classifiers_[0].estimator

            if hasattr(estimator, "feature_importances_"):
                importances = estimator.feature_importances_
                pairs = list(zip(feature_names, importances, feature_values))
                pairs.sort(key=lambda x: abs(x[1]), reverse=True)
                return [
                    {
                        "name": name,
                        "importance": round(float(imp), 4),
                        "value": round(float(val), 4),
                    }
                    for name, imp, val in pairs[:10]
                ]
        except Exception:
            pass

        if feature_values:
            pairs = list(zip(feature_names, feature_values))
            pairs.sort(key=lambda x: abs(x[1]), reverse=True)
            return [{"name": name, "value": round(float(val), 4)} for name, val in pairs[:5]]
        return []

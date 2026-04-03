"""
Layer 3 supervised ranker.

Supports:
- persisted mode: load a trained classifier and infer final_score/final_label
- fallback mode: combine baseline/rule/graph scores with fixed weights
"""

import json
from pathlib import Path

import numpy as np

from app.core.config import BASE_DIR
from app.core.logging import get_logger
from app.core.scoring_policy import (
    COMPOSITE_DETECTION_THRESHOLDS,
    COMPOSITE_DETECTION_WEIGHTS,
)
from app.services.detection.model_compat import validate_sklearn_version

logger = get_logger(__name__)

MODEL_DIR = BASE_DIR / "models"
RANKER_MODEL_PATH = MODEL_DIR / "composite_ranker.joblib"
RANKER_META_PATH = MODEL_DIR / "composite_ranker.meta.json"


class SupervisedRanker:
    """Final scorer built on top of the composite feature vector."""

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
                logger.info("SupervisedRanker downgraded to fallback mode")
        else:
            self.mode = "fallback"

        logger.info("SupervisedRanker initialized, mode=%s", self.mode)

    def _load_model(self) -> bool:
        """Load the persisted supervised model and metadata."""
        try:
            import joblib

            if not RANKER_MODEL_PATH.exists() or not RANKER_META_PATH.exists():
                logger.info(
                    "Supervised model files do not exist (%s); using fallback mode",
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
                "Loaded supervised model: type=%s, features=%d, threshold=%.3f",
                meta.get("model_type", "unknown"),
                len(meta.get("feature_names", [])),
                float(self.threshold),
            )
            return True

        except Exception as exc:
            logger.warning("Failed to load supervised model: %s", exc)
            return False

    def predict(
        self,
        flows: list[dict],
        feature_matrix: list[list[float]],
        feature_names: list[str],
    ) -> list[dict]:
        """Compute final_score/final_label for each flow."""
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
        """Infer with the persisted classifier."""
        try:
            X = np.array(feature_matrix)
            expected_features = self.meta.get("feature_names", [])
            if X.shape[1] != len(expected_features):
                logger.warning(
                    "Feature dimension mismatch: expected %d, got %d; using fallback",
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
                "SupervisedRanker(persisted) completed: %d flows, max=%.3f",
                len(flows),
                float(scores.max()),
            )
            return flows

        except Exception as exc:
            logger.error("Supervised inference failed: %s; using fallback", exc)
            return self._predict_fallback(flows, feature_names)

    def _predict_fallback(
        self,
        flows: list[dict],
        feature_names: list[str],
    ) -> list[dict]:
        """Fallback: weighted fusion of baseline_score, rule_score, and graph_score."""
        weights = COMPOSITE_DETECTION_WEIGHTS

        for flow in flows:
            det = flow.setdefault("_detection", {})
            baseline = det.get("baseline_score", 0.0)
            rule = det.get("rule_score", 0.0)
            graph = det.get("graph_score", 0.0)

            final_score = (
                baseline * weights["baseline_score"]
                + rule * weights["rule_score"]
                + graph * weights["graph_score"]
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
            "SupervisedRanker(fallback) completed: %d flows, max=%.3f",
            len(flows),
            max((f.get("_detection", {}).get("final_score", 0) for f in flows), default=0),
        )
        return flows

    def _score_to_label(self, final_score: float, rule_type: str) -> str:
        """Map final_score to a final label."""
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
        """Build a compact per-flow explanation payload."""
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
        """Return model feature importance when available."""
        try:
            if hasattr(self.model, "feature_importances_"):
                importances = self.model.feature_importances_
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

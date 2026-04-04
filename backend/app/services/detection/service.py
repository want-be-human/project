"""
DetectionService.

Provides the Layer 1 baseline anomaly detector backed by IsolationForest.
It supports:
- persisted mode: load a pre-trained model and score without fitting
- runtime mode: fit an IsolationForest on the current batch
"""

import json
from pathlib import Path

import numpy as np

from app.core.config import BASE_DIR
from app.core.logging import get_logger
from app.services.detection.model_compat import validate_sklearn_version

logger = get_logger(__name__)

MODEL_DIR = BASE_DIR / "models"
MODEL_PATH = MODEL_DIR / "flow_iforest.joblib"
META_PATH = MODEL_DIR / "flow_iforest.meta.json"


class DetectionService:
    """Baseline anomaly scoring service using IsolationForest."""

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
            self.mode = "persisted" if self._load_model() else "runtime"
        else:
            self.mode = "runtime"

    def _load_model(self) -> bool:
        """Load the persisted IsolationForest model and metadata."""
        try:
            import joblib

            if not MODEL_PATH.exists() or not META_PATH.exists():
                logger.warning(
                    "Persisted model files do not exist (%s); falling back to runtime mode",
                    MODEL_PATH,
                )
                return False

            meta = json.loads(META_PATH.read_text(encoding="utf-8"))
            feature_names = meta.get("feature_names")
            normalization = meta.get("normalization", {})

            if not feature_names or not isinstance(feature_names, list):
                logger.warning("Invalid model metadata: feature_names missing or malformed")
                return False
            if "p5" not in normalization or "p95" not in normalization:
                logger.warning("Invalid model metadata: normalization parameters missing")
                return False
            if not validate_sklearn_version(meta, "flow_iforest"):
                return False

            self.model = joblib.load(MODEL_PATH)
            self.meta = meta
            self.feature_names = feature_names

            logger.info(
                "Loaded persisted baseline model (samples=%d, features=%d)",
                meta.get("training_samples", 0),
                len(feature_names),
            )
            return True

        except Exception as exc:
            logger.warning("Failed to load persisted baseline model: %s", exc)
            return False

    def score_flows(self, flows: list[dict]) -> list[dict]:
        """Score flows and write anomaly_score in place."""
        if not flows:
            return flows

        if len(flows) < 2 and self.mode == "runtime":
            for flow in flows:
                flow["anomaly_score"] = 0.5
            return flows

        if self.mode == "persisted":
            return self._score_persisted(flows)
        return self._score_runtime(flows)

    def _score_persisted(self, flows: list[dict]) -> list[dict]:
        """Score using the persisted model without fitting."""
        try:
            X = self._flows_to_matrix(flows)
            expected_cols = len(self.feature_names)
            if X.shape[1] != expected_cols:
                logger.error(
                    "Feature dimension mismatch: expected %d, got %d; falling back to runtime",
                    expected_cols,
                    X.shape[1],
                )
                return self._score_runtime(flows)

            raw_scores = self.model.score_samples(X)
            neg_scores = -raw_scores

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
                "Persisted baseline inference completed: %d flows, max=%.3f",
                len(flows),
                float(normalized.max()),
            )
            return flows

        except Exception as exc:
            logger.error(
                "Persisted baseline inference failed: %s; falling back to runtime", exc
            )
            return self._score_runtime(flows)

    def _score_runtime(self, flows: list[dict]) -> list[dict]:
        """Fit an IsolationForest on the current batch and score it."""
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

            # 保存已拟合模型和归一化参数，供后续 score_with_fitted 使用
            self.model = model

            raw_scores = model.score_samples(X)
            neg_scores = -raw_scores
            p5, p95 = np.percentile(neg_scores, [5, 95])
            self.meta = {"normalization": {"p5": float(p5), "p95": float(p95)}}
            clipped = np.clip(neg_scores, p5, p95)

            if p95 > p5:
                normalized = (clipped - p5) / (p95 - p5)
            else:
                normalized = np.full_like(raw_scores, 0.5)

            for i, flow in enumerate(flows):
                flow["anomaly_score"] = float(normalized[i])

            logger.info(
                "Runtime anomaly detection completed: %d flows, p5=%.4f, p95=%.4f, max=%.3f",
                len(flows),
                float(p5),
                float(p95),
                float(normalized.max()),
            )
            return flows

        except ImportError:
            logger.warning("scikit-learn is not installed; using random fallback scores")
            for flow in flows:
                flow["anomaly_score"] = np.random.random() * 0.5
            return flows
        except Exception as exc:
            logger.error("Runtime anomaly detection failed: %s", exc)
            for flow in flows:
                flow["anomaly_score"] = 0.5
            return flows

    def _flows_to_matrix(self, flows: list[dict]) -> np.ndarray:
        """Convert a flow list into a numeric feature matrix."""
        rows = []
        for flow in flows:
            features = flow.get("features", {})
            row = []
            for name in self.feature_names:
                value = features.get(name, 0)
                if isinstance(value, str):
                    value = hash(value) % 10
                row.append(float(value))
            rows.append(row)
        return np.array(rows)

    def get_top_anomalous_flows(
        self,
        flows: list[dict],
        threshold: float = 0.7,
        limit: int = 10,
    ) -> list[dict]:
        """Return the top anomalous flows above threshold."""
        anomalous = [f for f in flows if (f.get("anomaly_score") or 0) >= threshold]
        anomalous.sort(key=lambda x: x.get("anomaly_score", 0), reverse=True)
        return anomalous[:limit]

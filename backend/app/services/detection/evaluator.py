import numpy as np

from app.core.logging import get_logger

logger = get_logger(__name__)

_DELTA_KEYS = ("roc_auc", "pr_auc", "f1", "precision", "recall")


class Evaluator:
    def __init__(self):
        pass

    def compute_metrics(
        self,
        y_true: np.ndarray,
        y_scores: np.ndarray,
        threshold: float = 0.5,
    ) -> dict:
        from sklearn.metrics import (
            average_precision_score,
            f1_score,
            precision_score,
            recall_score,
            roc_auc_score,
        )

        y_pred = (y_scores >= threshold).astype(int)

        metrics: dict = {}
        if len(np.unique(y_true)) > 1:
            metrics["roc_auc"] = round(float(roc_auc_score(y_true, y_scores)), 4)
            metrics["pr_auc"] = round(float(average_precision_score(y_true, y_scores)), 4)
        else:
            metrics["roc_auc"] = None
            metrics["pr_auc"] = None

        metrics["f1"] = round(float(f1_score(y_true, y_pred, zero_division=0)), 4)
        metrics["precision"] = round(float(precision_score(y_true, y_pred, zero_division=0)), 4)
        metrics["recall"] = round(float(recall_score(y_true, y_pred, zero_division=0)), 4)
        metrics["threshold"] = threshold
        metrics["total_samples"] = int(len(y_true))
        metrics["positive_samples"] = int(y_true.sum())
        metrics["predicted_positive"] = int(y_pred.sum())

        return metrics

    def compare_models(
        self,
        y_true: np.ndarray,
        scores_baseline: np.ndarray,
        scores_composite: np.ndarray,
        threshold: float = 0.5,
    ) -> dict:
        baseline_metrics = self.compute_metrics(y_true, scores_baseline, threshold)
        composite_metrics = self.compute_metrics(y_true, scores_composite, threshold)

        delta: dict = {}
        for key in _DELTA_KEYS:
            bv = baseline_metrics.get(key)
            cv = composite_metrics.get(key)
            delta[key] = round(cv - bv, 4) if bv is not None and cv is not None else None

        return {
            "baseline": baseline_metrics,
            "composite": composite_metrics,
            "delta": delta,
            "summary": self._comparison_summary(delta),
        }

    def ablation_study(
        self,
        y_true: np.ndarray,
        feature_matrix: np.ndarray,
        feature_names: list[str],
        feature_groups: dict[str, list[str]],
        model_factory: callable,
        threshold: float = 0.5,
    ) -> dict:
        from sklearn.model_selection import train_test_split

        X_train, X_test, y_train, y_test = train_test_split(
            feature_matrix, y_true, test_size=0.3, random_state=42, stratify=y_true
        )

        model_full = model_factory()
        model_full.fit(X_train, y_train)
        if hasattr(model_full, "predict_proba"):
            scores_full = model_full.predict_proba(X_test)[:, 1]
        else:
            scores_full = model_full.predict(X_test)
        full_metrics = self.compute_metrics(y_test, scores_full, threshold)

        ablation_results: dict[str, dict] = {"full": full_metrics}

        for group_name, group_features in feature_groups.items():
            remove_indices = [
                i for i, name in enumerate(feature_names) if name in group_features
            ]
            keep_indices = [
                i for i in range(len(feature_names)) if i not in remove_indices
            ]

            if not keep_indices:
                continue

            X_train_ablated = X_train[:, keep_indices]
            X_test_ablated = X_test[:, keep_indices]

            model_ablated = model_factory()
            model_ablated.fit(X_train_ablated, y_train)
            if hasattr(model_ablated, "predict_proba"):
                scores_ablated = model_ablated.predict_proba(X_test_ablated)[:, 1]
            else:
                scores_ablated = model_ablated.predict(X_test_ablated)

            ablated_metrics = self.compute_metrics(y_test, scores_ablated, threshold)

            delta_f1 = (full_metrics["f1"] or 0) - (ablated_metrics["f1"] or 0)
            delta_auc = (full_metrics["roc_auc"] or 0) - (ablated_metrics["roc_auc"] or 0)

            ablation_results[f"without_{group_name}"] = {
                **ablated_metrics,
                "removed_features": len(remove_indices),
                "delta_f1": round(delta_f1, 4),
                "delta_roc_auc": round(delta_auc, 4),
            }

        return ablation_results

    def threshold_sensitivity(
        self,
        y_true: np.ndarray,
        y_scores: np.ndarray,
        thresholds: list[float] | None = None,
    ) -> list[dict]:
        if thresholds is None:
            thresholds = [round(t, 2) for t in np.arange(0.30, 1.00, 0.05)]

        return [self.compute_metrics(y_true, y_scores, threshold=t) for t in thresholds]

    def per_type_metrics(
        self,
        y_true: np.ndarray,
        y_scores: np.ndarray,
        type_labels: list[str],
        threshold: float = 0.5,
    ) -> dict:
        unique_types = sorted(set(type_labels))
        results: dict = {}

        for attack_type in unique_types:
            mask = np.array([t == attack_type for t in type_labels])
            if mask.sum() == 0:
                continue

            metrics = self.compute_metrics(y_true[mask], y_scores[mask], threshold)
            metrics["sample_count"] = int(mask.sum())
            results[attack_type] = metrics

        return results

    def generate_report(
        self,
        y_true: np.ndarray,
        scores_baseline: np.ndarray,
        scores_composite: np.ndarray,
        type_labels: list[str] | None = None,
        threshold: float = 0.5,
    ) -> dict:
        report: dict = {
            "experiment_1_model_comparison": self.compare_models(
                y_true, scores_baseline, scores_composite, threshold
            ),
            "experiment_3_threshold_sensitivity": {
                "baseline": self.threshold_sensitivity(y_true, scores_baseline),
                "composite": self.threshold_sensitivity(y_true, scores_composite),
            },
        }

        if type_labels is not None:
            report["experiment_4_per_type"] = {
                "baseline": self.per_type_metrics(y_true, scores_baseline, type_labels, threshold),
                "composite": self.per_type_metrics(y_true, scores_composite, type_labels, threshold),
            }

        return report

    @staticmethod
    def _comparison_summary(delta: dict) -> str:
        parts: list[str] = []
        for key, val in delta.items():
            if val is None:
                continue
            direction = "提升" if val > 0 else "下降"
            parts.append(f"{key} {direction} {abs(val):.4f}")
        return "复合模型相比基线：" + "，".join(parts) if parts else "无显著差异"

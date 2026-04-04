#!/usr/bin/env python3
"""
Leak-free composite model training.

Supported modes:
- legacy two-PCAP mode: one normal PCAP + one attack PCAP
- manifest mode: one or more PCAP sources, each optionally paired with an
  official labels CSV
- dataset preset mode: CIC-IDS2017 core subset discovery

The training flow is:
1. Load labeled flows.
2. Split into train / validation / test.
3. Fit IsolationForest on train only and score every split without refitting.
4. Add rule and graph features without leaking test information.
5. Train the supervised ranker on train.
6. Fit a probability calibrator on a calibration holdout from validation.
7. Tune the decision threshold on a separate threshold holdout.
8. Evaluate once on test and persist the calibrated model.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.services.detection.baseline_detector import BaselineDetector
from app.services.detection.evaluator import Evaluator
from app.services.detection.feature_pipeline import FeaturePipeline
from app.services.detection.graph_feature_builder import GraphFeatureBuilder
from app.services.detection.rule_enricher import RuleEnricher
from app.services.features.service import FeaturesService
from app.services.parsing.service import ParsingService
from scripts.training_dataset import (
    DatasetSource,
    assign_default_family,
    build_cicids2017_core_sources,
    label_flows_with_official_csv,
    load_dataset_manifest,
)

MODEL_DIR = BACKEND_DIR / "models"
RANKER_MODEL_PATH = MODEL_DIR / "composite_ranker.joblib"
RANKER_META_PATH = MODEL_DIR / "composite_ranker.meta.json"
REPORT_PATH = MODEL_DIR / "evaluation_report.json"

DEFAULT_NORMAL_PCAP = BACKEND_DIR / "data" / "pcaps" / "training_normal.pcap"
DEFAULT_ATTACK_PCAP = BACKEND_DIR / "data" / "pcaps" / "training_attack.pcap"
DEFAULT_CICIDS2017_ROOT = BACKEND_DIR / "data" / "datasets" / "cicids2017"


def three_way_split(
    flows: list[dict],
    strategy: str = "stratified",
    train_ratio: float = 0.6,
    val_ratio: float = 0.2,
    random_state: int = 42,
) -> tuple[list[dict], list[dict], list[dict]]:
    from sklearn.model_selection import train_test_split

    labels = [f.get("_label", 0) for f in flows]

    if strategy == "temporal":
        block_size = 10
        group_ids = [i // block_size for i in range(len(flows))]
        unique_groups = sorted(set(group_ids))
        rng = np.random.RandomState(random_state)
        rng.shuffle(unique_groups)

        n_train = int(len(unique_groups) * train_ratio)
        n_val = int(len(unique_groups) * val_ratio)

        train_groups = set(unique_groups[:n_train])
        val_groups = set(unique_groups[n_train:n_train + n_val])

        train_flows: list[dict] = []
        val_flows: list[dict] = []
        test_flows: list[dict] = []
        for index, flow in enumerate(flows):
            group_id = group_ids[index]
            if group_id in train_groups:
                train_flows.append(flow)
            elif group_id in val_groups:
                val_flows.append(flow)
            else:
                test_flows.append(flow)
        return train_flows, val_flows, test_flows

    test_ratio = 1.0 - train_ratio - val_ratio
    train_val, test_flows = train_test_split(
        flows,
        test_size=test_ratio,
        random_state=random_state,
        stratify=labels,
    )
    labels_train_val = [f.get("_label", 0) for f in train_val]
    val_relative = val_ratio / (train_ratio + val_ratio)
    train_flows, val_flows = train_test_split(
        train_val,
        test_size=val_relative,
        random_state=random_state,
        stratify=labels_train_val,
    )
    return train_flows, val_flows, test_flows


def split_validation_for_calibration(
    X_val: np.ndarray,
    y_val: np.ndarray,
    *,
    random_state: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict]:
    from sklearn.model_selection import train_test_split

    if len(X_val) < 10 or len(np.unique(y_val)) < 2:
        info = {
            "strategy": "shared_validation",
            "calibration_samples": int(len(X_val)),
            "threshold_samples": int(len(X_val)),
        }
        return X_val, X_val, y_val, y_val, info

    class_counts = np.bincount(y_val.astype(int), minlength=2)
    if int(class_counts.min()) < 2:
        info = {
            "strategy": "shared_validation",
            "calibration_samples": int(len(X_val)),
            "threshold_samples": int(len(X_val)),
        }
        return X_val, X_val, y_val, y_val, info

    X_calib, X_threshold, y_calib, y_threshold = train_test_split(
        X_val,
        y_val,
        test_size=0.5,
        random_state=random_state,
        stratify=y_val,
    )

    if len(np.unique(y_calib)) < 2 or len(np.unique(y_threshold)) < 2:
        info = {
            "strategy": "shared_validation",
            "calibration_samples": int(len(X_val)),
            "threshold_samples": int(len(X_val)),
        }
        return X_val, X_val, y_val, y_val, info

    info = {
        "strategy": "split_validation",
        "calibration_samples": int(len(X_calib)),
        "threshold_samples": int(len(X_threshold)),
    }
    return X_calib, X_threshold, y_calib, y_threshold, info


def resolve_calibration_method(
    y_calib: np.ndarray,
    calibration_method: str,
) -> str:
    if calibration_method != "auto":
        return calibration_method

    class_counts = np.bincount(y_calib.astype(int), minlength=2)
    if int(class_counts.min()) >= 50 and int(len(y_calib)) >= 200:
        return "isotonic"
    return "sigmoid"


def train_supervised(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    model_type: str = "lightgbm",
) -> object:
    if model_type == "lightgbm":
        try:
            from lightgbm import LGBMClassifier

            model = LGBMClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.05,
                num_leaves=31,
                min_child_samples=10,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                verbose=-1,
            )
            model.fit(X_train, y_train, eval_set=[(X_val, y_val)])
            return model
        except ImportError:
            print("  lightgbm is not installed, falling back to sklearn GradientBoosting")
            model_type = "sklearn_gb"

    if model_type == "xgboost":
        try:
            from xgboost import XGBClassifier

            model = XGBClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                eval_metric="logloss",
                verbosity=0,
            )
            model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
            return model
        except ImportError:
            print("  xgboost is not installed, falling back to sklearn GradientBoosting")
            model_type = "sklearn_gb"

    from sklearn.ensemble import GradientBoostingClassifier

    model = GradientBoostingClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        random_state=42,
    )
    model.fit(X_train, y_train)
    return model


def train_semi_supervised(
    X_labeled: np.ndarray,
    y_labeled: np.ndarray,
    X_unlabeled: np.ndarray,
    model_type: str = "pu_learning",
) -> object:
    from sklearn.ensemble import GradientBoostingClassifier

    print(f"  semi-supervised mode: {model_type}")
    print(f"  labeled samples: {len(y_labeled)}, unlabeled samples: {len(X_unlabeled)}")

    initial_model = GradientBoostingClassifier(
        n_estimators=100,
        max_depth=4,
        random_state=42,
    )
    initial_model.fit(X_labeled, y_labeled)

    if len(X_unlabeled) == 0:
        return initial_model

    if hasattr(initial_model, "predict_proba"):
        proba = initial_model.predict_proba(X_unlabeled)[:, 1]
    else:
        proba = initial_model.predict(X_unlabeled)

    high_conf_pos = proba >= 0.9
    high_conf_neg = proba <= 0.1
    mask = high_conf_pos | high_conf_neg
    pseudo_labels = (proba[mask] >= 0.5).astype(int)

    print(
        "  pseudo labels: "
        f"{int(mask.sum())} (positive={int(high_conf_pos.sum())}, negative={int(high_conf_neg.sum())})"
    )

    if mask.sum() == 0:
        return initial_model

    X_combined = np.vstack([X_labeled, X_unlabeled[mask]])
    y_combined = np.concatenate([y_labeled, pseudo_labels])

    final_model = GradientBoostingClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        random_state=42,
    )
    final_model.fit(X_combined, y_combined)
    return final_model


def calibrate_threshold(y_true: np.ndarray, y_scores: np.ndarray) -> float:
    from sklearn.metrics import f1_score

    best_threshold = 0.5
    best_f1 = -1.0

    for threshold in np.arange(0.3, 0.95, 0.01):
        y_pred = (y_scores >= threshold).astype(int)
        f1 = f1_score(y_true, y_pred, zero_division=0)
        if f1 > best_f1:
            best_f1 = float(f1)
            best_threshold = float(threshold)

    return round(best_threshold, 2)


def fit_probability_calibrator(
    base_model: object,
    X_calib: np.ndarray,
    y_calib: np.ndarray,
    *,
    calibration_method: str,
) -> tuple[object, dict]:
    if calibration_method == "none":
        return base_model, {"enabled": False, "method": "none", "reason": "disabled"}

    if len(np.unique(y_calib)) < 2:
        return base_model, {
            "enabled": False,
            "method": "none",
            "reason": "single_class_calibration_split",
        }

    from sklearn.calibration import CalibratedClassifierCV

    resolved_method = resolve_calibration_method(y_calib, calibration_method)
    calibrated_model = CalibratedClassifierCV(
        estimator=base_model,
        method=resolved_method,
        cv="prefit",
    )
    calibrated_model.fit(X_calib, y_calib)
    info = {
        "enabled": True,
        "method": resolved_method,
        "samples": int(len(X_calib)),
        "positive_samples": int(y_calib.sum()),
    }
    return calibrated_model, info


def _get_scores(model: object, X: np.ndarray) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(X)
        return proba[:, 1] if proba.shape[1] > 1 else proba[:, 0]
    return model.predict(X).astype(float)


def load_training_flows(
    sources: list[DatasetSource],
    *,
    window_sec: int,
    label_match_tolerance_sec: int,
) -> tuple[list[dict], dict]:
    parser = ParsingService()
    features = FeaturesService()

    all_flows: list[dict] = []
    source_stats: list[dict] = []

    for source in sources:
        if not source.pcap.exists():
            raise FileNotFoundError(f"PCAP does not exist: {source.pcap}")
        if source.labels_csv is not None and not source.labels_csv.exists():
            raise FileNotFoundError(f"Labels CSV does not exist: {source.labels_csv}")

        print(f"  loading source: {source.name}")
        print(f"    pcap: {source.pcap}")
        raw_flows = parser.parse_to_flows(source.pcap, window_sec=window_sec)
        print(f"    parsed flows: {len(raw_flows)}")

        if source.labels_csv is not None:
            labeled_flows, stats = label_flows_with_official_csv(
                raw_flows,
                source.labels_csv,
                include_families=source.include_families,
                tolerance_sec=label_match_tolerance_sec,
                source_name=source.name,
                timestamp_day_first=source.timestamp_day_first,
            )
        elif source.default_family is not None:
            labeled_flows, stats = assign_default_family(
                raw_flows,
                source.default_family,
                source.name,
            )
        else:
            raise ValueError(
                f"Source {source.name} must provide either labels_csv or default_family"
            )

        if not labeled_flows:
            raise ValueError(f"No labeled flows were produced for source: {source.name}")

        labeled_flows = features.extract_features_batch(labeled_flows)
        all_flows.extend(labeled_flows)
        source_stats.append(stats)

        print(
            "    labeled flows: "
            f"{stats['labeled_flows']} "
            f"(families={stats.get('family_counts', {})}, unmatched={stats.get('unmatched_flows', 0)})"
        )

    summary = {
        "source_count": len(sources),
        "sources": source_stats,
        "total_flows": len(all_flows),
        "family_counts": dict(
            Counter(flow.get("_attack_type", "normal") for flow in all_flows)
        ),
    }
    return all_flows, summary


def build_sources_from_args(args: argparse.Namespace) -> tuple[list[DatasetSource], dict]:
    if args.dataset_manifest:
        sources, config = load_dataset_manifest(args.dataset_manifest)
        config["mode"] = "manifest"
        return sources, config

    if args.dataset_preset == "cicids2017_core":
        dataset_root = args.dataset_root or DEFAULT_CICIDS2017_ROOT
        sources = build_cicids2017_core_sources(dataset_root)
        config = {
            "mode": "dataset_preset",
            "preset": "cicids2017_core",
            "window_sec": args.window_sec,
            "label_match_tolerance_sec": args.label_match_tolerance_sec,
            "dataset_root": str(dataset_root),
        }
        return sources, config

    if not args.pcap_normal.exists():
        print(f"[1/8] normal PCAP does not exist, generating demo training data: {args.pcap_normal}")
        from scripts.generate_demo_pcaps import generate_training_pcap

        args.pcap_normal.parent.mkdir(parents=True, exist_ok=True)
        generate_training_pcap(args.pcap_normal)

    sources = [DatasetSource(name="legacy_normal", pcap=args.pcap_normal, default_family="normal")]
    if args.pcap_attack.exists():
        sources.append(
            DatasetSource(
                name="legacy_attack",
                pcap=args.pcap_attack,
                default_family="anomaly",
            )
        )

    config = {
        "mode": "legacy",
        "window_sec": args.window_sec,
        "label_match_tolerance_sec": args.label_match_tolerance_sec,
    }
    return sources, config


def build_feature_groups(feature_names: list[str]) -> dict[str, list[str]]:
    return {
        "flow_stats": [
            name
            for name in feature_names
            if not name.startswith("rule_")
            and not name.startswith("node_")
            and not name.startswith("neighbor_")
            and not name.startswith("edge_")
            and not name.startswith("subnet_")
            and not name.startswith("is_hub")
            and not name.startswith("betweenness")
            and not name.startswith("clustering")
            and name != "baseline_score"
        ],
        "baseline": ["baseline_score"],
        "rule_features": [name for name in feature_names if name.startswith("rule_")],
        "graph_features": [
            name
            for name in feature_names
            if name.startswith("node_")
            or name.startswith("neighbor_")
            or name.startswith("edge_")
            or name.startswith("subnet_")
            or name.startswith("is_hub")
            or name.startswith("betweenness")
            or name.startswith("clustering")
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the composite detection model")
    parser.add_argument("--pcap-normal", type=Path, default=DEFAULT_NORMAL_PCAP)
    parser.add_argument("--pcap-attack", type=Path, default=DEFAULT_ATTACK_PCAP)
    parser.add_argument("--dataset-manifest", type=Path, default=None)
    parser.add_argument(
        "--dataset-preset",
        choices=["cicids2017_core"],
        default=None,
    )
    parser.add_argument("--dataset-root", type=Path, default=None)
    parser.add_argument("--window-sec", type=int, default=60)
    parser.add_argument("--label-match-tolerance-sec", type=int, default=120)
    parser.add_argument(
        "--model-type",
        choices=["lightgbm", "xgboost", "sklearn_gb"],
        default="lightgbm",
    )
    parser.add_argument(
        "--mode",
        choices=["supervised", "semi-supervised"],
        default="supervised",
    )
    parser.add_argument("--contamination", type=float, default=0.1)
    parser.add_argument(
        "--split-strategy",
        choices=["stratified", "temporal"],
        default="stratified",
    )
    parser.add_argument(
        "--calibration-method",
        choices=["auto", "sigmoid", "isotonic", "none"],
        default="auto",
    )
    args = parser.parse_args()

    print("[1/8] Loading labeled training sources...")
    sources, dataset_config = build_sources_from_args(args)

    if args.dataset_manifest and "window_sec" in dataset_config:
        args.window_sec = int(dataset_config["window_sec"])
        args.label_match_tolerance_sec = int(dataset_config["label_match_tolerance_sec"])

    all_flows, dataset_summary = load_training_flows(
        sources,
        window_sec=args.window_sec,
        label_match_tolerance_sec=args.label_match_tolerance_sec,
    )

    if len(all_flows) < 5:
        print("Error: not enough labeled flows to train the composite model.")
        sys.exit(1)

    print(f"[2/8] Feature extraction completed during source loading: {len(all_flows)} flows")

    y_all = np.array([flow.get("_label", 0) for flow in all_flows])
    threshold = 0.7
    model = None
    base_model = None
    comparison: dict | None = None
    eval_metrics: dict = {}
    per_type_metrics: dict = {}
    calibration_info: dict = {"enabled": False, "method": "none"}
    calibration_split_info: dict = {}
    feature_names: list[str] = []

    positives = int(y_all.sum())
    negatives = int((y_all == 0).sum())
    has_supervised_labels = positives >= 3 and negatives >= 3

    if has_supervised_labels:
        print(f"[3/8] Splitting data ({args.split_strategy})...")
        train_flows, val_flows, test_flows = three_way_split(
            all_flows,
            strategy=args.split_strategy,
        )

        y_train = np.array([flow.get("_label", 0) for flow in train_flows])
        y_val = np.array([flow.get("_label", 0) for flow in val_flows])
        y_test = np.array([flow.get("_label", 0) for flow in test_flows])
        attack_type_test = [flow.get("_attack_type", "normal") for flow in test_flows]

        print(
            f"  train={len(train_flows)} (normal={int((y_train == 0).sum())}, attack={int((y_train == 1).sum())})"
        )
        print(
            f"  val={len(val_flows)} (normal={int((y_val == 0).sum())}, attack={int((y_val == 1).sum())})"
        )
        print(
            f"  test={len(test_flows)} (normal={int((y_test == 0).sum())}, attack={int((y_test == 1).sum())})"
        )

        print("[4/8] Fitting the baseline detector on train only...")
        baseline = BaselineDetector(
            mode="runtime",
            model_params={"contamination": args.contamination},
        )
        train_flows = baseline.score(train_flows)
        val_flows = baseline.score_with_fitted(val_flows)
        test_flows = baseline.score_with_fitted(test_flows)

        print("[5/8] Building rule features...")
        enricher = RuleEnricher()
        train_flows = enricher.enrich(train_flows)
        val_flows = enricher.enrich(val_flows)
        test_flows = enricher.enrich(test_flows)

        print("[6/8] Building graph features without leaking validation/test structure...")
        graph_builder = GraphFeatureBuilder()
        train_flows = graph_builder.build_and_extract(train_flows)
        train_graph = graph_builder.last_graph
        assert train_graph is not None, "Training graph was not built."
        val_flows = graph_builder.extract_with_graph(val_flows, train_graph)
        test_flows = graph_builder.extract_with_graph(test_flows, train_graph)

        print("[7/8] Training the supervised ranker and calibrating probabilities...")
        pipeline = FeaturePipeline()
        feature_names, train_matrix = pipeline.build_feature_matrix(train_flows)
        _, val_matrix = pipeline.build_feature_matrix(val_flows)
        _, test_matrix = pipeline.build_feature_matrix(test_flows)

        X_train = np.array(train_matrix)
        X_val = np.array(val_matrix)
        X_test = np.array(test_matrix)

        if args.mode == "semi-supervised":
            n_labeled = max(int(len(y_train) * 0.3), 5)
            X_labeled = X_train[:n_labeled]
            y_labeled = y_train[:n_labeled]
            X_unlabeled = X_train[n_labeled:]
            base_model = train_semi_supervised(X_labeled, y_labeled, X_unlabeled)
        else:
            base_model = train_supervised(X_train, y_train, X_val, y_val, args.model_type)

        X_calib, X_threshold, y_calib, y_threshold, calibration_split_info = split_validation_for_calibration(
            X_val,
            y_val,
        )
        model, calibration_info = fit_probability_calibrator(
            base_model,
            X_calib,
            y_calib,
            calibration_method=args.calibration_method,
        )

        threshold_scores = _get_scores(model, X_threshold)
        threshold = calibrate_threshold(y_threshold, threshold_scores)
        print(
            "  calibration="
            f"{calibration_info.get('method', 'none')} "
            f"threshold={threshold}"
        )

        print("[8/8] Final evaluation on the test split...")
        test_scores = _get_scores(model, X_test)
        evaluator = Evaluator()
        eval_metrics = evaluator.compute_metrics(y_test, test_scores, threshold)
        baseline_test_scores = np.array(
            [flow.get("_detection", {}).get("baseline_score", 0.0) for flow in test_flows]
        )
        comparison = evaluator.compare_models(
            y_test,
            baseline_test_scores,
            test_scores,
            threshold,
        )
        per_type_metrics = evaluator.per_type_metrics(
            y_test,
            test_scores,
            attack_type_test,
            threshold,
        )

        print(f"  ROC-AUC:   {eval_metrics.get('roc_auc')}")
        print(f"  PR-AUC:    {eval_metrics.get('pr_auc')}")
        print(f"  F1:        {eval_metrics.get('f1')}")
        print(f"  Precision: {eval_metrics.get('precision')}")
        print(f"  Recall:    {eval_metrics.get('recall')}")
        print(f"  Comparison: {comparison.get('summary')}")

        experiment_config = {
            "dataset_mode": dataset_config.get("mode", "legacy"),
            "dataset_preset": dataset_config.get("preset"),
            "split_strategy": args.split_strategy,
            "training_mode": args.mode,
            "threshold_source": "validation_threshold_holdout_f1_optimal",
            "threshold": threshold,
            "training_samples": int(len(train_flows)),
            "validation_samples": int(len(val_flows)),
            "test_samples": int(len(test_flows)),
            "window_sec": int(args.window_sec),
            "label_match_tolerance_sec": int(args.label_match_tolerance_sec),
            "calibration_split": calibration_split_info,
            "probability_calibration": calibration_info,
        }
    else:
        print("[3/8] Not enough positive/negative labels for supervised training; skipping ranker fit.")
        feature_names = []
        experiment_config = {
            "dataset_mode": dataset_config.get("mode", "legacy"),
            "dataset_preset": dataset_config.get("preset"),
            "split_strategy": "none",
            "training_mode": "baseline_only",
            "threshold_source": "default",
            "threshold": threshold,
            "training_samples": int(len(all_flows)),
            "validation_samples": 0,
            "test_samples": 0,
            "window_sec": int(args.window_sec),
            "label_match_tolerance_sec": int(args.label_match_tolerance_sec),
            "probability_calibration": calibration_info,
        }

    print("Saving model artifacts...")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    if model is not None:
        import joblib
        import sklearn

        joblib.dump(model, RANKER_MODEL_PATH)
        feature_groups = build_feature_groups(feature_names)

        meta = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "sklearn_version": sklearn.__version__,
            "model_type": type(model).__name__,
            "base_model_type": type(base_model).__name__ if base_model is not None else None,
            "training_mode": args.mode,
            "feature_names": feature_names,
            "feature_groups": feature_groups,
            "threshold": threshold,
            "experiment_config": experiment_config,
            "dataset_summary": dataset_summary,
            "evaluation": eval_metrics,
            "per_type_metrics": per_type_metrics,
        }
        RANKER_META_PATH.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  model: {RANKER_MODEL_PATH}")
        print(f"  meta:  {RANKER_META_PATH}")
    else:
        print("  supervised model not trained; runtime will use fallback fusion")

    report: dict = {
        "experiment_config": experiment_config,
        "dataset_summary": dataset_summary,
        "threshold": threshold,
    }
    if eval_metrics:
        report["composite_final"] = eval_metrics
    if comparison is not None:
        report["baseline_only"] = comparison["baseline"]
        report["delta"] = comparison["delta"]
        report["comparison_summary"] = comparison["summary"]
    if per_type_metrics:
        report["per_type_metrics"] = per_type_metrics

    REPORT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  report: {REPORT_PATH}")
    print()
    print("Training completed.")


if __name__ == "__main__":
    main()

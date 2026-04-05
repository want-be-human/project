#!/usr/bin/env python3
"""
Leak-free composite model training with TensorBoard logging and GPU support.

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
5. Train the supervised ranker on train (GPU accelerated when available).
6. Fit a probability calibrator on a calibration holdout from validation.
7. Tune the decision threshold on a separate threshold holdout.
8. Evaluate once on test and persist the calibrated model.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
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
DEFAULT_TB_DIR = BACKEND_DIR / "runs"


# ---------------------------------------------------------------------------
# GPU detection
# ---------------------------------------------------------------------------

def _detect_gpu() -> bool:
    """检查 XGBoost CUDA GPU 是否可用。"""
    try:
        import xgboost as xgb
        m = xgb.XGBClassifier(device="cuda", n_estimators=1, verbosity=0)
        m.fit([[0], [1]], [0, 1])
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# XGBoost TensorBoard callback
# ---------------------------------------------------------------------------

def _make_tb_callback(writer):
    """构建记录到 TensorBoard 的 XGBoost TrainingCallback。"""
    from xgboost.callback import TrainingCallback  # type: ignore[attr-defined]

    class _TBCallback(TrainingCallback):
        def after_iteration(self, model, epoch, evals_log):  # noqa: ARG002
            for data_name, metrics in evals_log.items():
                for metric_name, values in metrics.items():
                    val = values[-1] if values else 0
                    writer.add_scalar(
                        f"xgb_iter/{data_name}_{metric_name}", val, epoch,
                    )
            return False

    return _TBCallback()


# ---------------------------------------------------------------------------
# 数据划分
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 模型训练
# ---------------------------------------------------------------------------

def train_supervised(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    model_type: str = "lightgbm",
    *,
    use_gpu: bool = False,
    writer: object | None = None,
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
            import xgboost as xgb

            device = "cuda" if use_gpu else "cpu"
            print(f"  XGBoost device: {device}")
            cbs = [_make_tb_callback(writer)] if writer is not None else None

            model = xgb.XGBClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                eval_metric="logloss",
                device=device,
                verbosity=1,
                callbacks=cbs,
            )
            model.fit(
                X_train, y_train,
                eval_set=[(X_train, y_train), (X_val, y_val)],
                verbose=10,
            )
            return model
        except ImportError:
            print("  xgboost is not installed, falling back to sklearn GradientBoosting")
            model_type = "sklearn_gb"

    # sklearn GradientBoosting fallback — try XGBoost GPU first if requested
    if use_gpu:
        print("  GPU requested — promoting sklearn_gb to xgboost with CUDA")
        try:
            import xgboost as xgb

            cbs = [_make_tb_callback(writer)] if writer is not None else None

            model = xgb.XGBClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                eval_metric="logloss",
                device="cuda",
                verbosity=1,
                callbacks=cbs,
            )
            model.fit(
                X_train, y_train,
                eval_set=[(X_train, y_train), (X_val, y_val)],
                verbose=10,
            )
            return model
        except Exception as e:
            print(f"  XGBoost GPU failed ({e}), falling back to sklearn CPU")

    from sklearn.ensemble import GradientBoostingClassifier

    print("  sklearn GradientBoostingClassifier (CPU)")
    model = GradientBoostingClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        random_state=42,
    )
    model.fit(X_train, y_train)

    # 将分阶段训练损失记录到 TensorBoard
    if writer is not None:
        try:
            for i, y_pred in enumerate(model.staged_predict_proba(X_val)):
                from sklearn.metrics import log_loss
                loss = log_loss(y_val, y_pred, labels=[0, 1])
                writer.add_scalar("sklearn_staged/val_logloss", loss, i)
        except Exception:
            pass

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


def calibrate_threshold(
    y_true: np.ndarray,
    y_scores: np.ndarray,
    *,
    writer: object | None = None,
) -> float:
    from sklearn.metrics import f1_score

    best_threshold = 0.5
    best_f1 = -1.0

    for threshold in np.arange(0.3, 0.95, 0.01):
        y_pred = (y_scores >= threshold).astype(int)
        f1 = f1_score(y_true, y_pred, zero_division=0)
        if writer is not None:
            writer.add_scalar("threshold_tuning/f1", f1, int(threshold * 100))
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
    from sklearn.frozen import FrozenEstimator

    resolved_method = resolve_calibration_method(y_calib, calibration_method)
    calibrated_model = CalibratedClassifierCV(
        estimator=FrozenEstimator(base_model),
        method=resolved_method,
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


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------

def load_training_flows(
    sources: list[DatasetSource],
    *,
    idle_timeout: int = 120,
    active_timeout: int = 1800,
    label_match_tolerance_sec: int,
    writer: object | None = None,
) -> tuple[list[dict], dict]:
    parser = ParsingService()
    features = FeaturesService()

    all_flows: list[dict] = []
    source_stats: list[dict] = []

    for idx, source in enumerate(sources):
        if not source.pcap.exists():
            raise FileNotFoundError(f"PCAP does not exist: {source.pcap}")
        if source.labels_csv is not None and not source.labels_csv.exists():
            raise FileNotFoundError(f"Labels CSV does not exist: {source.labels_csv}")

        print(f"  loading source: {source.name}")
        print(f"    pcap: {source.pcap}")
        t0 = time.time()
        raw_flows = parser.parse_to_flows(
            source.pcap, idle_timeout=idle_timeout, active_timeout=active_timeout,
        )
        parse_time = time.time() - t0
        print(f"    parsed flows: {len(raw_flows)} (耗时 {parse_time:.1f}s)")

        if writer is not None:
            writer.add_scalar(f"source/{source.name}/parse_sec", parse_time, 0)
            writer.add_scalar(f"source/{source.name}/raw_flows", len(raw_flows), 0)

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

        if writer is not None:
            writer.add_scalar(f"source/{source.name}/labeled_flows", stats["labeled_flows"], 0)
            writer.add_scalar(f"source/{source.name}/unmatched_flows", stats.get("unmatched_flows", 0), 0)
            for fam, cnt in stats.get("family_counts", {}).items():
                writer.add_scalar(f"source/{source.name}/family_{fam}", cnt, 0)

    summary = {
        "source_count": len(sources),
        "sources": source_stats,
        "total_flows": len(all_flows),
        "family_counts": dict(
            Counter(flow.get("_attack_type", "normal") for flow in all_flows)
        ),
    }

    if writer is not None:
        writer.add_scalar("dataset/total_flows", summary["total_flows"], 0)
        for fam, cnt in summary["family_counts"].items():
            writer.add_scalar(f"dataset/family_{fam}", cnt, 0)

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
            "idle_timeout": args.idle_timeout,
            "active_timeout": args.active_timeout,
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
        "idle_timeout": args.idle_timeout,
            "active_timeout": args.active_timeout,
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


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

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
    parser.add_argument("--idle-timeout", type=int, default=120,
                        help="Flow idle timeout in seconds (NFStream mode)")
    parser.add_argument("--active-timeout", type=int, default=1800,
                        help="Flow active timeout in seconds (NFStream mode)")
    parser.add_argument("--window-sec", type=int, default=60,
                        help="[Deprecated] Flow window for dpkt fallback mode")
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
    parser.add_argument("--tensorboard-dir", type=Path, default=DEFAULT_TB_DIR)
    parser.add_argument(
        "--device",
        choices=["auto", "gpu", "cpu"],
        default="auto",
        help="Training device: auto detects GPU, gpu forces CUDA, cpu forces CPU",
    )
    args = parser.parse_args()

    # ── TensorBoard 初始化 ──
    from tensorboardX import SummaryWriter

    run_name = f"composite_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    log_dir = args.tensorboard_dir / run_name
    writer = SummaryWriter(str(log_dir))
    print(f"TensorBoard 日志: {log_dir}")
    print(f"  启动查看: tensorboard --logdir {args.tensorboard_dir}")

    t_total_start = time.time()

    # ── GPU 检测 ──
    if args.device == "auto":
        use_gpu = _detect_gpu()
    elif args.device == "gpu":
        use_gpu = True
    else:
        use_gpu = False
    device_label = "CUDA GPU" if use_gpu else "CPU"
    print(f"训练设备: {device_label}")
    writer.add_text("config/device", device_label, 0)
    writer.add_text("config/model_type", args.model_type, 0)

    print("[1/8] Loading labeled training sources...")
    sources, dataset_config = build_sources_from_args(args)

    if args.dataset_manifest and "window_sec" in dataset_config:
        args.label_match_tolerance_sec = int(dataset_config["label_match_tolerance_sec"])

    all_flows, dataset_summary = load_training_flows(
        sources,
        idle_timeout=args.idle_timeout,
        active_timeout=args.active_timeout,
        label_match_tolerance_sec=args.label_match_tolerance_sec,
        writer=writer,
    )

    if len(all_flows) < 5:
        print("Error: not enough labeled flows to train the composite model.")
        writer.close()
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

    writer.add_scalar("dataset/positives", positives, 0)
    writer.add_scalar("dataset/negatives", negatives, 0)

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

        writer.add_scalar("split/train_total", len(train_flows), 0)
        writer.add_scalar("split/train_attack", int(y_train.sum()), 0)
        writer.add_scalar("split/val_total", len(val_flows), 0)
        writer.add_scalar("split/val_attack", int(y_val.sum()), 0)
        writer.add_scalar("split/test_total", len(test_flows), 0)
        writer.add_scalar("split/test_attack", int(y_test.sum()), 0)

        print("[4/8] Fitting the baseline detector on train only...")
        t0 = time.time()
        baseline = BaselineDetector(
            mode="runtime",
            model_params={"contamination": args.contamination},
        )
        train_flows = baseline.score(train_flows)
        val_flows = baseline.score_with_fitted(val_flows)
        test_flows = baseline.score_with_fitted(test_flows)
        writer.add_scalar("timing/baseline_sec", time.time() - t0, 0)

        print("[5/8] Building rule features...")
        t0 = time.time()
        enricher = RuleEnricher()
        train_flows = enricher.enrich(train_flows)
        val_flows = enricher.enrich(val_flows)
        test_flows = enricher.enrich(test_flows)
        writer.add_scalar("timing/rule_sec", time.time() - t0, 0)

        print("[6/8] Building graph features without leaking validation/test structure...")
        t0 = time.time()
        graph_builder = GraphFeatureBuilder()
        train_flows = graph_builder.build_and_extract(train_flows)
        train_graph = graph_builder.last_graph
        assert train_graph is not None, "Training graph was not built."
        val_flows = graph_builder.extract_with_graph(val_flows, train_graph)
        test_flows = graph_builder.extract_with_graph(test_flows, train_graph)
        writer.add_scalar("timing/graph_sec", time.time() - t0, 0)

        print("[7/8] Training the supervised ranker and calibrating probabilities...")
        pipeline = FeaturePipeline()
        feature_names, train_matrix = pipeline.build_feature_matrix(train_flows)
        _, val_matrix = pipeline.build_feature_matrix(val_flows)
        _, test_matrix = pipeline.build_feature_matrix(test_flows)

        X_train = np.array(train_matrix)
        X_val = np.array(val_matrix)
        X_test = np.array(test_matrix)

        writer.add_scalar("features/count", len(feature_names), 0)

        t0 = time.time()
        if args.mode == "semi-supervised":
            n_labeled = max(int(len(y_train) * 0.3), 5)
            X_labeled = X_train[:n_labeled]
            y_labeled = y_train[:n_labeled]
            X_unlabeled = X_train[n_labeled:]
            base_model = train_semi_supervised(X_labeled, y_labeled, X_unlabeled)
        else:
            base_model = train_supervised(
                X_train, y_train, X_val, y_val, args.model_type,
                use_gpu=use_gpu,
                writer=writer,
            )
        train_time = time.time() - t0
        writer.add_scalar("timing/supervised_train_sec", train_time, 0)
        print(f"  模型训练耗时: {train_time:.1f}s")

        # 记录实际使用的模型类型
        actual_model_type = type(base_model).__name__
        writer.add_text("config/actual_model_type", actual_model_type, 0)

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
        threshold = calibrate_threshold(y_threshold, threshold_scores, writer=writer)
        print(
            "  calibration="
            f"{calibration_info.get('method', 'none')} "
            f"threshold={threshold}"
        )
        writer.add_scalar("calibration/threshold", threshold, 0)
        writer.add_text("calibration/method", calibration_info.get("method", "none"), 0)

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

        # ── TensorBoard: evaluation metrics ──
        for k, v in eval_metrics.items():
            if isinstance(v, (int, float)) and v is not None:
                writer.add_scalar(f"eval/{k}", v, 0)

        # 仅基线模型指标（用于对比）
        if comparison is not None:
            for k, v in comparison.get("baseline", {}).items():
                if isinstance(v, (int, float)) and v is not None:
                    writer.add_scalar(f"baseline_only/{k}", v, 0)
            for k, v in comparison.get("delta", {}).items():
                if isinstance(v, (int, float)) and v is not None:
                    writer.add_scalar(f"delta/{k}", v, 0)

        # 按攻击类型的指标
        for atk_type, metrics in per_type_metrics.items():
            for k, v in metrics.items():
                if isinstance(v, (int, float)) and v is not None:
                    writer.add_scalar(f"per_type/{atk_type}/{k}", v, 0)

        # 分数分布
        writer.add_histogram("scores/test_all", test_scores, 0)
        if y_test.sum() > 0:
            writer.add_histogram("scores/test_positive", test_scores[y_test == 1], 0)
        if (y_test == 0).sum() > 0:
            writer.add_histogram("scores/test_negative", test_scores[y_test == 0], 0)
        writer.add_histogram("scores/baseline_test", baseline_test_scores, 0)

        # 超参数
        hparam_dict = {
            "model_type": actual_model_type,
            "split_strategy": args.split_strategy,
            "idle_timeout": args.idle_timeout,
            "active_timeout": args.active_timeout,
            "tolerance_sec": args.label_match_tolerance_sec,
            "calibration": calibration_info.get("method", "none"),
            "contamination": args.contamination,
            "device": device_label,
        }
        metric_dict = {
            "hparam/roc_auc": eval_metrics.get("roc_auc", 0) or 0,
            "hparam/pr_auc": eval_metrics.get("pr_auc", 0) or 0,
            "hparam/f1": eval_metrics.get("f1", 0) or 0,
            "hparam/threshold": threshold,
        }
        writer.add_hparams(hparam_dict, metric_dict)

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
            "idle_timeout": int(args.idle_timeout),
            "active_timeout": int(args.active_timeout),
            "label_match_tolerance_sec": int(args.label_match_tolerance_sec),
            "calibration_split": calibration_split_info,
            "probability_calibration": calibration_info,
            "device": device_label,
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
            "idle_timeout": int(args.idle_timeout),
            "active_timeout": int(args.active_timeout),
            "label_match_tolerance_sec": int(args.label_match_tolerance_sec),
            "probability_calibration": calibration_info,
            "device": device_label,
        }

    total_time = time.time() - t_total_start
    writer.add_scalar("timing/total_sec", total_time, 0)

    print("Saving model artifacts...")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    if model is not None:
        import joblib
        import sklearn

        # 保存前移除不可序列化的 TensorBoard 回调
        def _strip_callbacks(m):
            """移除无法被 pickle 的回调引用。"""
            if hasattr(m, "callbacks"):
                m.callbacks = None
            # CalibratedClassifierCV 在 calibrated_classifiers_ 中包装估计器
            for attr in ("estimator", "estimator_"):
                inner = getattr(m, attr, None)
                if inner is not None:
                    _strip_callbacks(inner)
            for cc in getattr(m, "calibrated_classifiers_", []):
                _strip_callbacks(getattr(cc, "estimator", None) or cc)

        _strip_callbacks(model)
        if base_model is not None:
            _strip_callbacks(base_model)

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

    writer.close()

    print()
    print("Training completed.")
    print(f"  总耗时: {total_time:.1f}s")
    print(f"  TensorBoard: tensorboard --logdir {args.tensorboard_dir}")


if __name__ == "__main__":
    main()

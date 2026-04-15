#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import time
from collections import Counter
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
from app.core.scoring_policy import (
    COMPOSITE_DETECTION_WEIGHTS,
    STRONG_RULE_TYPES,
    GUARD_RULE_FLOOR_THRESHOLD,
    GUARD_RULE_FLOOR_FACTOR,
    GUARD_CONSENSUS_BASELINE,
    GUARD_CONSENSUS_SECONDARY,
    GUARD_CONSENSUS_FLOOR,
)
from scripts.training_dataset import (
    build_cicids2017_core_sources,
    label_flows_with_official_csv,
    assign_default_family,
)
from scripts.train_composite_model import three_way_split

MODEL_DIR = BACKEND_DIR / "models"
DEFAULT_CICIDS2017_ROOT = BACKEND_DIR / "data" / "cicids2017"
OUTPUT_DIR = BACKEND_DIR / "models" / "ablation_results"

THRESHOLD = 0.53  # 与训练时一致


def load_data(dataset_root: Path):
    sources = build_cicids2017_core_sources(dataset_root)
    parser = ParsingService()
    features = FeaturesService()

    all_flows = []
    for src in sources:
        if not src.pcap.exists():
            print(f"  PCAP not found: {src.pcap}, skipping")
            continue
        print(f"  Loading {src.name}...")
        t0 = time.time()
        raw = parser.parse_to_flows(src.pcap, idle_timeout=120, active_timeout=1800)
        print(f"    Parsed {len(raw)} flows in {time.time()-t0:.1f}s")

        if src.labels_csv is not None and src.labels_csv.exists():
            labeled, stats = label_flows_with_official_csv(
                raw, src.labels_csv,
                include_families=src.include_families,
                tolerance_sec=120,
                source_name=src.name,
                timestamp_day_first=src.timestamp_day_first,
            )
        elif src.default_family:
            labeled, stats = assign_default_family(raw, src.default_family, src.name)
        else:
            continue

        labeled = features.extract_features_batch(labeled)
        all_flows.extend(labeled)
        print(f"    Labeled: {stats.get('labeled_flows', len(labeled))}, families={stats.get('family_counts', {})}")

    print(f"\nTotal flows: {len(all_flows)}")
    print(f"Family counts: {dict(Counter(f.get('_attack_type', 'normal') for f in all_flows))}")

    train, val, test = three_way_split(all_flows, strategy="temporal")
    y_train = np.array([f.get("_label", 0) for f in train])
    y_val = np.array([f.get("_label", 0) for f in val])
    y_test = np.array([f.get("_label", 0) for f in test])
    types_test = [f.get("_attack_type", "normal") for f in test]

    print(f"Train: {len(train)} (attack={int(y_train.sum())})")
    print(f"Val:   {len(val)} (attack={int(y_val.sum())})")
    print(f"Test:  {len(test)} (attack={int(y_test.sum())})")

    return train, val, test, y_train, y_val, y_test, types_test


def apply_guardrails(flows: list[dict], scores: np.ndarray) -> np.ndarray:
    guarded = scores.copy()
    for i, flow in enumerate(flows):
        det = flow.get("_detection", {})
        baseline = det.get("baseline_score", 0.0)
        rule = det.get("rule_score", 0.0)
        rule_type = det.get("rule_type", "anomaly")
        graph = det.get("graph_score", 0.0)

        if rule_type in STRONG_RULE_TYPES and rule >= GUARD_RULE_FLOOR_THRESHOLD:
            guarded[i] = max(guarded[i], rule * GUARD_RULE_FLOOR_FACTOR)

        if baseline >= GUARD_CONSENSUS_BASELINE and max(rule, graph) >= GUARD_CONSENSUS_SECONDARY:
            guarded[i] = max(guarded[i], GUARD_CONSENSUS_FLOOR)

    return guarded


def weighted_fusion(flows: list[dict]) -> np.ndarray:
    scores = np.zeros(len(flows))
    w = COMPOSITE_DETECTION_WEIGHTS
    for i, flow in enumerate(flows):
        det = flow.get("_detection", {})
        scores[i] = (
            w["baseline_score"] * det.get("baseline_score", 0.0)
            + w["rule_score"] * det.get("rule_score", 0.0)
            + w["graph_score"] * det.get("graph_score", 0.0)
        )
    return scores


def main():
    print("=" * 70)
    print("NetTwin-SOC 消融实验")
    print("=" * 70)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    evaluator = Evaluator()

    print("\n[1/7] Loading CIC-IDS2017 dataset...")
    train_flows, val_flows, test_flows, y_train, y_val, y_test, types_test = \
        load_data(DEFAULT_CICIDS2017_ROOT)

    results = {}

    print("\n[2/7] Layer 1: IsolationForest baseline...")
    t0 = time.time()
    baseline = BaselineDetector(mode="runtime", model_params={"contamination": 0.02})
    train_flows = baseline.score(train_flows)
    val_flows = baseline.score_with_fitted(val_flows)
    test_flows = baseline.score_with_fitted(test_flows)
    print(f"  Baseline scoring: {time.time()-t0:.1f}s")

    baseline_scores = np.array([f.get("_detection", {}).get("baseline_score", 0.0) for f in test_flows])
    results["L1_only"] = evaluator.compute_metrics(y_test, baseline_scores, THRESHOLD)
    print(f"  L1 Only: F1={results['L1_only']['f1']}, AUC={results['L1_only']['roc_auc']}")

    print("\n[3/7] Layer 2a: Rule enrichment...")
    t0 = time.time()
    enricher = RuleEnricher()
    train_flows = enricher.enrich(train_flows)
    val_flows = enricher.enrich(val_flows)
    test_flows = enricher.enrich(test_flows)
    print(f"  Rule enrichment: {time.time()-t0:.1f}s")

    # 归一化权重仅 baseline+rule（无 graph）
    w_b = 0.50 / (0.50 + 0.35)
    w_r = 0.35 / (0.50 + 0.35)
    l1l2a_scores = np.zeros(len(test_flows))
    for i, flow in enumerate(test_flows):
        det = flow.get("_detection", {})
        l1l2a_scores[i] = w_b * det.get("baseline_score", 0.0) + w_r * det.get("rule_score", 0.0)
    results["L1_L2a"] = evaluator.compute_metrics(y_test, l1l2a_scores, THRESHOLD)
    print(f"  L1+L2a: F1={results['L1_L2a']['f1']}, AUC={results['L1_L2a']['roc_auc']}")

    print("\n[4/7] Layer 2b: Graph features...")
    t0 = time.time()
    gb = GraphFeatureBuilder()
    train_flows = gb.build_and_extract(train_flows)
    train_graph = gb.last_graph
    val_flows = gb.extract_with_graph(val_flows, train_graph)
    test_flows = gb.extract_with_graph(test_flows, train_graph)
    print(f"  Graph features: {time.time()-t0:.1f}s")

    l1l2al2b_scores = weighted_fusion(test_flows)
    results["L1_L2a_L2b"] = evaluator.compute_metrics(y_test, l1l2al2b_scores, THRESHOLD)
    print(f"  L1+L2a+L2b: F1={results['L1_L2a_L2b']['f1']}, AUC={results['L1_L2a_L2b']['roc_auc']}")

    print("\n[5/7] Layer 3: XGBoost training...")
    pipeline = FeaturePipeline()
    _, train_matrix = pipeline.build_feature_matrix(train_flows)
    _, val_matrix = pipeline.build_feature_matrix(val_flows)
    _, test_matrix = pipeline.build_feature_matrix(test_flows)

    X_train = np.array(train_matrix)
    X_val = np.array(val_matrix)
    X_test = np.array(test_matrix)

    t0 = time.time()
    try:
        import xgboost as xgb
        try:
            probe = xgb.XGBClassifier(device="cuda", n_estimators=1, verbosity=0)
            probe.fit([[0], [1]], [0, 1])
            device = "cuda"
        except Exception:
            device = "cpu"

        model = xgb.XGBClassifier(
            n_estimators=200, max_depth=6, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            random_state=42, eval_metric="logloss",
            device=device, verbosity=0,
        )
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
        print(f"  XGBoost training ({device}): {time.time()-t0:.1f}s")
    except ImportError:
        from sklearn.ensemble import GradientBoostingClassifier
        model = GradientBoostingClassifier(
            n_estimators=200, max_depth=6, learning_rate=0.05,
            subsample=0.8, random_state=42,
        )
        model.fit(X_train, y_train)
        print(f"  sklearn GB training: {time.time()-t0:.1f}s")

    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.frozen import FrozenEstimator
    from sklearn.model_selection import train_test_split as sk_split

    X_calib, _X_thr, y_calib, _y_thr = sk_split(
        X_val, y_val, test_size=0.5, random_state=42, stratify=y_val,
    )
    calibrated = CalibratedClassifierCV(
        estimator=FrozenEstimator(model), method="isotonic",
    )
    calibrated.fit(X_calib, y_calib)

    test_l3 = calibrated.predict_proba(X_test)[:, 1]
    results["L1_L2a_L2b_L3"] = evaluator.compute_metrics(y_test, test_l3, THRESHOLD)
    print(f"  L1+L2a+L2b+L3: F1={results['L1_L2a_L2b_L3']['f1']}, AUC={results['L1_L2a_L2b_L3']['roc_auc']}")

    print("\n[6/7] Applying guardrails...")
    test_guarded = apply_guardrails(test_flows, test_l3)
    results["L1_L2a_L2b_L3_Guard"] = evaluator.compute_metrics(y_test, test_guarded, THRESHOLD)
    print(f"  +Guardrails: F1={results['L1_L2a_L2b_L3_Guard']['f1']}, AUC={results['L1_L2a_L2b_L3_Guard']['roc_auc']}")

    print("\n[7/7] Generating reports...")

    from sklearn.metrics import confusion_matrix, roc_curve, auc
    y_pred = (test_guarded >= THRESHOLD).astype(int)
    cm = confusion_matrix(y_test, y_pred)
    cm_dict = {
        "TN": int(cm[0, 0]),
        "FP": int(cm[0, 1]),
        "FN": int(cm[1, 0]),
        "TP": int(cm[1, 1]),
    }

    fpr, tpr, _ = roc_curve(y_test, test_guarded)
    roc_auc_val = auc(fpr, tpr)
    idxs = np.linspace(0, len(fpr)-1, min(100, len(fpr)), dtype=int)
    roc_data = {
        "fpr": [round(float(fpr[i]), 4) for i in idxs],
        "tpr": [round(float(tpr[i]), 4) for i in idxs],
        "auc": round(float(roc_auc_val), 4),
    }

    per_type = evaluator.per_type_metrics(y_test, test_guarded, types_test, THRESHOLD)

    ablation_table = [
        {
            "config": name,
            "precision": m.get("precision"),
            "recall": m.get("recall"),
            "f1": m.get("f1"),
            "roc_auc": m.get("roc_auc"),
            "predicted_positive": m.get("predicted_positive"),
        }
        for name, m in results.items()
    ]

    report = {
        "ablation_table": ablation_table,
        "confusion_matrix": cm_dict,
        "roc_curve": roc_data,
        "per_type_metrics": per_type,
        "threshold": THRESHOLD,
        "test_samples": int(len(y_test)),
        "test_positive": int(y_test.sum()),
        "test_negative": int((y_test == 0).sum()),
        "attack_type_distribution_test": dict(Counter(types_test)),
    }

    output_path = OUTPUT_DIR / "ablation_report.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n  Report saved: {output_path}")

    print("\n" + "=" * 70)
    print("消融实验结果")
    print("=" * 70)
    print(f"{'配置':<25} {'Precision':>10} {'Recall':>10} {'F1':>10} {'AUC-ROC':>10}")
    print("-" * 70)
    for row in ablation_table:
        print(f"{row['config']:<25} {row['precision']:>10} {row['recall']:>10} {row['f1']:>10} {row['roc_auc']:>10}")

    print(f"\n混淆矩阵:")
    print(f"  TP={cm_dict['TP']}, FP={cm_dict['FP']}, TN={cm_dict['TN']}, FN={cm_dict['FN']}")
    print(f"  误报率(FPR): {cm_dict['FP']/(cm_dict['FP']+cm_dict['TN']):.6f}")
    print(f"  漏检率(FNR): {cm_dict['FN']/(cm_dict['FN']+cm_dict['TP']):.6f}")

    print(f"\n各攻击类型检测效果:")
    print(f"{'类型':<15} {'Precision':>10} {'Recall':>10} {'F1':>10} {'样本数':>10}")
    print("-" * 60)
    for atk, m in sorted(per_type.items()):
        print(f"{atk:<15} {m.get('precision', 0):>10} {m.get('recall', 0):>10} {m.get('f1', 0):>10} {m.get('sample_count', 0):>10}")

    print(f"\nROC AUC: {roc_data['auc']}")
    print(f"\n完成。")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
消融实验脚本：逐层累加检测组件，评估各阶段的指标。
生成：
1. 各层组合的 Precision/Recall/F1/AUC-ROC
2. 最终模型的混淆矩阵
3. ROC 曲线数据
4. 各攻击类型的检测指标

运行方式：
    cd backend
    python -m scripts.run_ablation_study
"""

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


def load_and_prepare_data(dataset_root: Path):
    """加载 CIC-IDS2017 数据，提取特征，分割数据集。"""
    sources = build_cicids2017_core_sources(dataset_root)
    parser = ParsingService()
    features = FeaturesService()

    all_flows = []
    for source in sources:
        if not source.pcap.exists():
            print(f"  PCAP not found: {source.pcap}, skipping")
            continue
        print(f"  Loading {source.name}...")
        t0 = time.time()
        raw_flows = parser.parse_to_flows(source.pcap, idle_timeout=120, active_timeout=1800)
        print(f"    Parsed {len(raw_flows)} flows in {time.time()-t0:.1f}s")

        if source.labels_csv is not None and source.labels_csv.exists():
            labeled_flows, stats = label_flows_with_official_csv(
                raw_flows, source.labels_csv,
                include_families=source.include_families,
                tolerance_sec=120,
                source_name=source.name,
                timestamp_day_first=source.timestamp_day_first,
            )
        elif source.default_family:
            labeled_flows, stats = assign_default_family(raw_flows, source.default_family, source.name)
        else:
            continue

        labeled_flows = features.extract_features_batch(labeled_flows)
        all_flows.extend(labeled_flows)
        print(f"    Labeled: {stats.get('labeled_flows', len(labeled_flows))}, families={stats.get('family_counts', {})}")

    print(f"\nTotal flows: {len(all_flows)}")
    family_counts = Counter(f.get("_attack_type", "normal") for f in all_flows)
    print(f"Family counts: {dict(family_counts)}")

    # Split
    train_flows, val_flows, test_flows = three_way_split(all_flows, strategy="temporal")
    y_train = np.array([f.get("_label", 0) for f in train_flows])
    y_val = np.array([f.get("_label", 0) for f in val_flows])
    y_test = np.array([f.get("_label", 0) for f in test_flows])
    attack_types_test = [f.get("_attack_type", "normal") for f in test_flows]

    print(f"Train: {len(train_flows)} (attack={int(y_train.sum())})")
    print(f"Val:   {len(val_flows)} (attack={int(y_val.sum())})")
    print(f"Test:  {len(test_flows)} (attack={int(y_test.sum())})")

    return train_flows, val_flows, test_flows, y_train, y_val, y_test, attack_types_test


def apply_guardrails(flows: list[dict], scores: np.ndarray) -> np.ndarray:
    """应用防护栏机制。"""
    guarded = scores.copy()
    for i, flow in enumerate(flows):
        det = flow.get("_detection", {})
        baseline_score = det.get("baseline_score", 0.0)
        rule_score = det.get("rule_score", 0.0)
        rule_type = det.get("rule_type", "anomaly")
        graph_score = det.get("graph_score", 0.0)

        # Guard 1: 强规则保底
        if rule_type in STRONG_RULE_TYPES and rule_score >= GUARD_RULE_FLOOR_THRESHOLD:
            guarded[i] = max(guarded[i], rule_score * GUARD_RULE_FLOOR_FACTOR)

        # Guard 2: 多源共识保底
        if baseline_score >= GUARD_CONSENSUS_BASELINE and max(rule_score, graph_score) >= GUARD_CONSENSUS_SECONDARY:
            guarded[i] = max(guarded[i], GUARD_CONSENSUS_FLOOR)

    return guarded


def compute_weighted_fusion(flows: list[dict]) -> np.ndarray:
    """加权融合分数（不使用 XGBoost）。"""
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
    threshold = 0.53  # 与训练时一致

    # ── 加载数据 ──
    print("\n[1/7] Loading CIC-IDS2017 dataset...")
    train_flows, val_flows, test_flows, y_train, y_val, y_test, attack_types_test = \
        load_and_prepare_data(DEFAULT_CICIDS2017_ROOT)

    results = {}

    # ── Layer 1: Baseline (IsolationForest) ──
    print("\n[2/7] Layer 1: IsolationForest baseline...")
    t0 = time.time()
    baseline = BaselineDetector(mode="runtime", model_params={"contamination": 0.02})
    train_flows = baseline.score(train_flows)
    val_flows = baseline.score_with_fitted(val_flows)
    test_flows = baseline.score_with_fitted(test_flows)
    print(f"  Baseline scoring: {time.time()-t0:.1f}s")

    baseline_scores = np.array([f.get("_detection", {}).get("baseline_score", 0.0) for f in test_flows])
    results["L1_only"] = evaluator.compute_metrics(y_test, baseline_scores, threshold)
    print(f"  L1 Only: F1={results['L1_only']['f1']}, AUC={results['L1_only']['roc_auc']}")

    # ── Layer 2a: Rules ──
    print("\n[3/7] Layer 2a: Rule enrichment...")
    t0 = time.time()
    enricher = RuleEnricher()
    train_flows = enricher.enrich(train_flows)
    val_flows = enricher.enrich(val_flows)
    test_flows = enricher.enrich(test_flows)
    print(f"  Rule enrichment: {time.time()-t0:.1f}s")

    # L1+L2a: 加权融合 baseline + rule (无 graph)
    l1l2a_scores = np.zeros(len(test_flows))
    for i, flow in enumerate(test_flows):
        det = flow.get("_detection", {})
        bs = det.get("baseline_score", 0.0)
        rs = det.get("rule_score", 0.0)
        # 归一化权重（仅 baseline + rule）
        w_b = 0.50 / (0.50 + 0.35)
        w_r = 0.35 / (0.50 + 0.35)
        l1l2a_scores[i] = w_b * bs + w_r * rs
    results["L1_L2a"] = evaluator.compute_metrics(y_test, l1l2a_scores, threshold)
    print(f"  L1+L2a: F1={results['L1_L2a']['f1']}, AUC={results['L1_L2a']['roc_auc']}")

    # ── Layer 2b: Graph ──
    print("\n[4/7] Layer 2b: Graph features...")
    t0 = time.time()
    graph_builder = GraphFeatureBuilder()
    train_flows = graph_builder.build_and_extract(train_flows)
    train_graph = graph_builder.last_graph
    val_flows = graph_builder.extract_with_graph(val_flows, train_graph)
    test_flows = graph_builder.extract_with_graph(test_flows, train_graph)
    print(f"  Graph features: {time.time()-t0:.1f}s")

    # L1+L2a+L2b: 加权融合全部三层（无 XGBoost）
    l1l2al2b_scores = compute_weighted_fusion(test_flows)
    results["L1_L2a_L2b"] = evaluator.compute_metrics(y_test, l1l2al2b_scores, threshold)
    print(f"  L1+L2a+L2b: F1={results['L1_L2a_L2b']['f1']}, AUC={results['L1_L2a_L2b']['roc_auc']}")

    # ── Layer 3: XGBoost (train + calibrate + evaluate) ──
    print("\n[5/7] Layer 3: XGBoost training...")
    pipeline = FeaturePipeline()
    feature_names, train_matrix = pipeline.build_feature_matrix(train_flows)
    _, val_matrix = pipeline.build_feature_matrix(val_flows)
    _, test_matrix = pipeline.build_feature_matrix(test_flows)

    X_train = np.array(train_matrix)
    X_val = np.array(val_matrix)
    X_test = np.array(test_matrix)

    t0 = time.time()
    try:
        import xgboost as xgb
        # 尝试 GPU
        try:
            test_model = xgb.XGBClassifier(device="cuda", n_estimators=1, verbosity=0)
            test_model.fit([[0], [1]], [0, 1])
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

    # 概率校准
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.frozen import FrozenEstimator
    from sklearn.model_selection import train_test_split as sk_split

    X_calib, X_thresh, y_calib, y_thresh = sk_split(
        X_val, y_val, test_size=0.5, random_state=42, stratify=y_val,
    )
    calibrated_model = CalibratedClassifierCV(
        estimator=FrozenEstimator(model), method="isotonic",
    )
    calibrated_model.fit(X_calib, y_calib)

    # L1+L2a+L2b+L3 (无 Guardrails)
    test_scores_l3 = calibrated_model.predict_proba(X_test)[:, 1]
    results["L1_L2a_L2b_L3"] = evaluator.compute_metrics(y_test, test_scores_l3, threshold)
    print(f"  L1+L2a+L2b+L3: F1={results['L1_L2a_L2b_L3']['f1']}, AUC={results['L1_L2a_L2b_L3']['roc_auc']}")

    # ── Guardrails ──
    print("\n[6/7] Applying guardrails...")
    test_scores_guarded = apply_guardrails(test_flows, test_scores_l3)
    results["L1_L2a_L2b_L3_Guard"] = evaluator.compute_metrics(y_test, test_scores_guarded, threshold)
    print(f"  +Guardrails: F1={results['L1_L2a_L2b_L3_Guard']['f1']}, AUC={results['L1_L2a_L2b_L3_Guard']['roc_auc']}")

    # ── 汇总 & 生成报告 ──
    print("\n[7/7] Generating reports...")

    # 混淆矩阵
    from sklearn.metrics import confusion_matrix, roc_curve, auc
    y_pred_final = (test_scores_guarded >= threshold).astype(int)
    cm = confusion_matrix(y_test, y_pred_final)
    cm_dict = {
        "TN": int(cm[0, 0]),
        "FP": int(cm[0, 1]),
        "FN": int(cm[1, 0]),
        "TP": int(cm[1, 1]),
    }

    # ROC 曲线数据
    fpr, tpr, roc_thresholds = roc_curve(y_test, test_scores_guarded)
    roc_auc = auc(fpr, tpr)
    # 采样 100 个点用于绘图
    indices = np.linspace(0, len(fpr)-1, min(100, len(fpr)), dtype=int)
    roc_data = {
        "fpr": [round(float(fpr[i]), 4) for i in indices],
        "tpr": [round(float(tpr[i]), 4) for i in indices],
        "auc": round(float(roc_auc), 4),
    }

    # 各攻击类型指标
    per_type = evaluator.per_type_metrics(y_test, test_scores_guarded, attack_types_test, threshold)

    # 汇总消融结果表
    ablation_table = []
    for name, metrics in results.items():
        ablation_table.append({
            "config": name,
            "precision": metrics.get("precision"),
            "recall": metrics.get("recall"),
            "f1": metrics.get("f1"),
            "roc_auc": metrics.get("roc_auc"),
            "predicted_positive": metrics.get("predicted_positive"),
        })

    # 保存所有结果
    report = {
        "ablation_table": ablation_table,
        "confusion_matrix": cm_dict,
        "roc_curve": roc_data,
        "per_type_metrics": per_type,
        "threshold": threshold,
        "test_samples": int(len(y_test)),
        "test_positive": int(y_test.sum()),
        "test_negative": int((y_test == 0).sum()),
        "attack_type_distribution_test": dict(Counter(attack_types_test)),
    }

    output_path = OUTPUT_DIR / "ablation_report.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n  Report saved: {output_path}")

    # 打印消融表
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
    for atk_type, metrics in sorted(per_type.items()):
        print(f"{atk_type:<15} {metrics.get('precision', 0):>10} {metrics.get('recall', 0):>10} {metrics.get('f1', 0):>10} {metrics.get('sample_count', 0):>10}")

    print(f"\nROC AUC: {roc_data['auc']}")
    print(f"\n完成。")


if __name__ == "__main__":
    main()

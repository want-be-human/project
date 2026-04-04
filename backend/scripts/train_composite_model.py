#!/usr/bin/env python3
"""
复合检测模型离线训练脚本（无泄漏版）。

训练 3 层复合检测架构中的所有模型：
  [1/8] 解析 PCAP（正常 + 攻击样本）
  [2/8] 提取 flow 统计特征
  [3/8] 三段式数据切分（train / val / test）
  [4/8] Layer 1: 在训练集上拟合 IsolationForest，独立评分各 split
  [5/8] Layer 2: 计算规则语义特征（各 split 独立）
  [6/8] 在训练集上构建图结构，独立提取各 split 的图特征
  [7/8] Layer 3: 训练监督模型，在 val 上校准阈值
  [8/8] 在 test 上最终评估 + 持久化

无泄漏保证：
  - train/val/test 切分在任何层处理之前完成
  - IsolationForest 仅在 train 上拟合，val/test 使用拟合后模型评分
  - 图结构仅从 train 构建，val/test 在训练图上提取特征
  - 阈值在 val 上校准，test 仅用于最终评估

用法：
    cd backend
    python -m scripts.train_composite_model
    python -m scripts.train_composite_model --pcap-normal data/pcaps/training_normal.pcap \\
                                            --pcap-attack data/pcaps/training_attack.pcap
    python -m scripts.train_composite_model --model-type xgboost
    python -m scripts.train_composite_model --mode semi-supervised
    python -m scripts.train_composite_model --split-strategy temporal
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# 将 backend/ 加入 sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.services.parsing.service import ParsingService
from app.services.features.service import FeaturesService
from app.services.detection.baseline_detector import BaselineDetector
from app.services.detection.rule_enricher import RuleEnricher
from app.services.detection.graph_feature_builder import GraphFeatureBuilder
from app.services.detection.feature_pipeline import FeaturePipeline
from app.services.detection.evaluator import Evaluator

# 模型输出目录
MODEL_DIR = BACKEND_DIR / "models"
RANKER_MODEL_PATH = MODEL_DIR / "composite_ranker.joblib"
RANKER_META_PATH = MODEL_DIR / "composite_ranker.meta.json"
REPORT_PATH = MODEL_DIR / "evaluation_report.json"

# 默认训练 PCAP 路径
DEFAULT_NORMAL_PCAP = BACKEND_DIR / "data" / "pcaps" / "training_normal.pcap"
DEFAULT_ATTACK_PCAP = BACKEND_DIR / "data" / "pcaps" / "training_attack.pcap"


def parse_and_extract(pcap_path: Path, label: int) -> list[dict]:
    """解析 PCAP 并提取特征，为每条 flow 附加标签。"""
    parser = ParsingService()
    flows = parser.parse_to_flows(pcap_path)
    feat_svc = FeaturesService()
    flows = feat_svc.extract_features_batch(flows)
    for f in flows:
        f["_label"] = label  # 0=正常, 1=异常
    return flows


def three_way_split(
    flows: list[dict],
    strategy: str = "stratified",
    train_ratio: float = 0.6,
    val_ratio: float = 0.2,
    random_state: int = 42,
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    三段式切分：train / val / test。

    策略：
      - stratified: 分层随机切分（保持正负样本比例）
      - temporal: 按流索引分块切分（模拟时间序列，避免相邻流泄漏）
    """
    from sklearn.model_selection import train_test_split

    labels = [f.get("_label", 0) for f in flows]

    if strategy == "temporal":
        # 按 10-flow 块分组，再按组切分
        block_size = 10
        group_ids = [i // block_size for i in range(len(flows))]
        unique_groups = sorted(set(group_ids))
        rng = np.random.RandomState(random_state)
        rng.shuffle(unique_groups)

        n_train = int(len(unique_groups) * train_ratio)
        n_val = int(len(unique_groups) * val_ratio)

        train_groups = set(unique_groups[:n_train])
        val_groups = set(unique_groups[n_train:n_train + n_val])

        train_flows, val_flows, test_flows = [], [], []
        for i, f in enumerate(flows):
            g = group_ids[i]
            if g in train_groups:
                train_flows.append(f)
            elif g in val_groups:
                val_flows.append(f)
            else:
                test_flows.append(f)
    else:
        # stratified: 先分出 test，再从剩余中分出 val
        test_ratio = 1.0 - train_ratio - val_ratio
        train_val, test_flows = train_test_split(
            flows, test_size=test_ratio, random_state=random_state,
            stratify=labels,
        )
        labels_tv = [f.get("_label", 0) for f in train_val]
        val_relative = val_ratio / (train_ratio + val_ratio)
        train_flows, val_flows = train_test_split(
            train_val, test_size=val_relative, random_state=random_state,
            stratify=labels_tv,
        )

    return train_flows, val_flows, test_flows


def train_supervised(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    model_type: str = "lightgbm",
) -> object:
    """
    训练监督模型。

    参数：
        X_train, y_train: 训练集
        X_val, y_val: 验证集（用于早停）
        model_type: "lightgbm" 或 "xgboost"
    返回：
        训练好的模型
    """
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
            model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
            )
            return model
        except ImportError:
            print("  lightgbm 未安装，回退到 sklearn GradientBoosting")
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
            model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                verbose=False,
            )
            return model
        except ImportError:
            print("  xgboost 未安装，回退到 sklearn GradientBoosting")
            model_type = "sklearn_gb"

    # 回退方案：sklearn GradientBoosting
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
    """
    半监督训练占位接口。

    当前实现：伪标签方案（pseudo-label）。
    使用有标签数据训练初始模型，对无标签数据预测伪标签，
    然后合并训练最终模型。

    参数：
        X_labeled: 有标签特征矩阵
        y_labeled: 标签
        X_unlabeled: 无标签特征矩阵
        model_type: "pu_learning" 或 "pseudo_label"
    返回：
        训练好的模型
    """
    from sklearn.ensemble import GradientBoostingClassifier

    print(f"  半监督模式: {model_type}")
    print(f"  有标签样本: {len(y_labeled)}, 无标签样本: {len(X_unlabeled)}")

    # 第一阶段：用有标签数据训练初始模型
    initial_model = GradientBoostingClassifier(
        n_estimators=100, max_depth=4, random_state=42
    )
    initial_model.fit(X_labeled, y_labeled)

    if len(X_unlabeled) == 0:
        return initial_model

    # 第二阶段：对无标签数据生成伪标签
    if hasattr(initial_model, "predict_proba"):
        proba = initial_model.predict_proba(X_unlabeled)[:, 1]
    else:
        proba = initial_model.predict(X_unlabeled)

    # 仅选取高置信度样本（>0.9 为正，<0.1 为负）
    high_conf_pos = proba >= 0.9
    high_conf_neg = proba <= 0.1
    mask = high_conf_pos | high_conf_neg
    pseudo_labels = (proba[mask] >= 0.5).astype(int)

    print(f"  高置信度伪标签: {mask.sum()} 条 (正={high_conf_pos.sum()}, 负={high_conf_neg.sum()})")

    if mask.sum() == 0:
        return initial_model

    # 第三阶段：合并训练
    X_combined = np.vstack([X_labeled, X_unlabeled[mask]])
    y_combined = np.concatenate([y_labeled, pseudo_labels])

    final_model = GradientBoostingClassifier(
        n_estimators=200, max_depth=6, learning_rate=0.05, random_state=42
    )
    final_model.fit(X_combined, y_combined)
    return final_model


def calibrate_threshold(y_true: np.ndarray, y_scores: np.ndarray) -> float:
    """基于 F1 最优化自动校准阈值。"""
    from sklearn.metrics import f1_score

    best_threshold = 0.5
    best_f1 = 0.0

    for t in np.arange(0.3, 0.95, 0.01):
        y_pred = (y_scores >= t).astype(int)
        f1 = f1_score(y_true, y_pred, zero_division=0)
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = float(t)

    return round(best_threshold, 2)


def _get_scores(model, X: np.ndarray) -> np.ndarray:
    """从模型获取概率分数。"""
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(X)
        return proba[:, 1] if proba.shape[1] > 1 else proba[:, 0]
    return model.predict(X).astype(float)


def main():
    ap = argparse.ArgumentParser(description="复合检测模型离线训练（无泄漏版）")
    ap.add_argument("--pcap-normal", type=Path, default=DEFAULT_NORMAL_PCAP,
                    help="正常流量 PCAP 路径")
    ap.add_argument("--pcap-attack", type=Path, default=DEFAULT_ATTACK_PCAP,
                    help="攻击流量 PCAP 路径（可选，无则仅训练基线）")
    ap.add_argument("--model-type", choices=["lightgbm", "xgboost", "sklearn_gb"],
                    default="lightgbm", help="Layer 3 模型类型")
    ap.add_argument("--mode", choices=["supervised", "semi-supervised"],
                    default="supervised", help="训练模式")
    ap.add_argument("--contamination", type=float, default=0.1,
                    help="IsolationForest 异常比例参数")
    ap.add_argument("--split-strategy", choices=["stratified", "temporal"],
                    default="stratified", help="数据切分策略")
    args = ap.parse_args()

    # ── [1/8] 解析 PCAP ──
    print(f"[1/8] 解析正常流量 PCAP: {args.pcap_normal}")
    if not args.pcap_normal.exists():
        print("  正常流量 PCAP 不存在，尝试自动生成...")
        from scripts.generate_demo_pcaps import generate_training_pcap
        args.pcap_normal.parent.mkdir(parents=True, exist_ok=True)
        generate_training_pcap(args.pcap_normal)

    normal_flows = parse_and_extract(args.pcap_normal, label=0)
    print(f"  正常流量: {len(normal_flows)} 条")

    attack_flows: list[dict] = []
    has_attack = args.pcap_attack.exists()
    if has_attack:
        print(f"  解析攻击流量 PCAP: {args.pcap_attack}")
        attack_flows = parse_and_extract(args.pcap_attack, label=1)
        print(f"  攻击流量: {len(attack_flows)} 条")
    else:
        print("  未提供攻击流量 PCAP，Layer 3 将仅使用 fallback 模式")

    all_flows = normal_flows + attack_flows

    if len(all_flows) < 5:
        print("错误：训练样本不足（至少需要 5 条流）")
        sys.exit(1)

    # ── [2/8] 特征已在 parse_and_extract 中提取 ──
    print(f"[2/8] 特征提取完成: {len(all_flows)} 条流")

    # ── [3/8] 三段式切分（在任何层处理之前） ──
    print(f"[3/8] 数据切分（策略: {args.split_strategy}）...")

    model = None
    threshold = 0.7
    eval_metrics: dict = {}
    comparison: dict | None = None
    feature_names: list[str] = []

    y_all = np.array([f.get("_label", 0) for f in all_flows])

    if has_attack and y_all.sum() >= 3:
        train_flows, val_flows, test_flows = three_way_split(
            all_flows, strategy=args.split_strategy,
        )
        y_train = np.array([f.get("_label", 0) for f in train_flows])
        y_val = np.array([f.get("_label", 0) for f in val_flows])
        y_test = np.array([f.get("_label", 0) for f in test_flows])

        print(f"  训练集: {len(train_flows)} 条 (正常={int((y_train == 0).sum())}, 异常={int((y_train == 1).sum())})")
        print(f"  验证集: {len(val_flows)} 条 (正常={int((y_val == 0).sum())}, 异常={int((y_val == 1).sum())})")
        print(f"  测试集: {len(test_flows)} 条 (正常={int((y_test == 0).sum())}, 异常={int((y_test == 1).sum())})")

        # ── [4/8] Layer 1: IsolationForest（仅在训练集上拟合） ──
        print("[4/8] Layer 1: IsolationForest 基线评分（无泄漏）...")
        baseline = BaselineDetector(mode="runtime", model_params={"contamination": args.contamination})

        # 在训练集上拟合 + 评分
        train_flows = baseline.score(train_flows)
        # 在 val/test 上使用已拟合模型评分（无重新拟合）
        val_flows = baseline.score_with_fitted(val_flows)
        test_flows = baseline.score_with_fitted(test_flows)

        for split_name, split_flows in [("train", train_flows), ("val", val_flows), ("test", test_flows)]:
            scores = [f.get("_detection", {}).get("baseline_score", 0) for f in split_flows]
            if scores:
                print(f"  {split_name} baseline_score: min={min(scores):.4f}, max={max(scores):.4f}, mean={sum(scores)/len(scores):.4f}")

        # ── [5/8] Layer 2: 规则特征（无状态，各 split 独立） ──
        print("[5/8] Layer 2: 规则语义特征...")
        enricher = RuleEnricher()
        train_flows = enricher.enrich(train_flows)
        val_flows = enricher.enrich(val_flows)
        test_flows = enricher.enrich(test_flows)

        # ── [6/8] 图特征（仅在训练集上构建图） ──
        print("[6/8] 图结构特征（无泄漏）...")
        graph_builder = GraphFeatureBuilder()
        # 在训练集上构建图并提取特征
        train_flows = graph_builder.build_and_extract(train_flows)
        # 在 val/test 上复用训练集构建的图
        train_graph = graph_builder.last_graph
        assert train_graph is not None, "训练集图构建失败"
        val_flows = graph_builder.extract_with_graph(val_flows, train_graph)
        test_flows = graph_builder.extract_with_graph(test_flows, train_graph)

        # ── [7/8] Layer 3: 构建特征矩阵并训练监督模型 ──
        print("[7/8] Layer 3: 构建特征矩阵并训练监督模型...")
        pipeline = FeaturePipeline()

        feature_names, train_matrix = pipeline.build_feature_matrix(train_flows)
        _, val_matrix = pipeline.build_feature_matrix(val_flows)
        _, test_matrix = pipeline.build_feature_matrix(test_flows)

        X_train = np.array(train_matrix)
        X_val = np.array(val_matrix)
        X_test = np.array(test_matrix)

        print(f"  特征矩阵: train={X_train.shape}, val={X_val.shape}, test={X_test.shape}")
        print(f"  特征数: {X_train.shape[1]}")

        if args.mode == "semi-supervised":
            # 半监督：将部分训练集标签移除
            n_labeled = max(int(len(y_train) * 0.3), 5)
            X_labeled = X_train[:n_labeled]
            y_labeled = y_train[:n_labeled]
            X_unlabeled = X_train[n_labeled:]
            model = train_semi_supervised(X_labeled, y_labeled, X_unlabeled)
        else:
            model = train_supervised(X_train, y_train, X_val, y_val, args.model_type)

        # ── 在 val 上校准阈值（不在 test 上调优） ──
        val_scores = _get_scores(model, X_val)
        threshold = calibrate_threshold(y_val, val_scores)
        print(f"  阈值校准（基于验证集 F1 最优）: {threshold}")

        # ── [8/8] 在 test 上最终评估 ──
        print("[8/8] 最终评估（测试集，阈值已锁定）...")
        test_scores = _get_scores(model, X_test)

        evaluator = Evaluator()
        eval_metrics = evaluator.compute_metrics(y_test, test_scores, threshold)
        print(f"  ROC-AUC:   {eval_metrics.get('roc_auc')}")
        print(f"  PR-AUC:    {eval_metrics.get('pr_auc')}")
        print(f"  F1:        {eval_metrics.get('f1')}")
        print(f"  Precision: {eval_metrics.get('precision')}")
        print(f"  Recall:    {eval_metrics.get('recall')}")

        # ── baseline only vs composite 对比（均在 test 上评估） ──
        baseline_test_scores = np.array([
            f.get("_detection", {}).get("baseline_score", 0) for f in test_flows
        ])
        comparison = evaluator.compare_models(
            y_test, baseline_test_scores, test_scores, threshold
        )
        print(f"  对比摘要: {comparison.get('summary')}")

        # ── 实验配置元数据 ──
        experiment_config = {
            "split_strategy": args.split_strategy,
            "training_mode": args.mode,
            "threshold_source": "val_f1_optimal",
            "threshold": threshold,
            "training_samples": int(len(train_flows)),
            "validation_samples": int(len(val_flows)),
            "test_samples": int(len(test_flows)),
            "is_semi_supervised": args.mode == "semi-supervised",
        }
    else:
        print("  无攻击样本或样本不足，跳过监督模型训练")
        # 仅做基线层处理（无需切分）
        print("[4/8] Layer 1: IsolationForest 基线评分...")
        baseline = BaselineDetector(mode="runtime", model_params={"contamination": args.contamination})
        all_flows = baseline.score(all_flows)
        enricher = RuleEnricher()
        all_flows = enricher.enrich(all_flows)
        graph_builder = GraphFeatureBuilder()
        all_flows = graph_builder.build_and_extract(all_flows)
        pipeline = FeaturePipeline()
        feature_names, _ = pipeline.build_feature_matrix(all_flows)
        experiment_config = {
            "split_strategy": "none",
            "training_mode": "baseline_only",
            "threshold_source": "default",
            "threshold": threshold,
            "training_samples": int(len(all_flows)),
            "validation_samples": 0,
            "test_samples": 0,
            "is_semi_supervised": False,
        }

    # ── 持久化 ──
    print("保存模型...")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    if model is not None:
        import joblib
        import sklearn
        joblib.dump(model, RANKER_MODEL_PATH)

        # 确定实际模型类型名
        actual_model_type = type(model).__name__

        meta = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "sklearn_version": sklearn.__version__,
            "model_type": actual_model_type,
            "training_mode": args.mode,
            "feature_names": feature_names,
            "feature_groups": {
                "flow_stats": [n for n in feature_names if not n.startswith("rule_") and not n.startswith("node_") and not n.startswith("neighbor_") and not n.startswith("edge_") and not n.startswith("subnet_") and not n.startswith("is_hub") and not n.startswith("betweenness") and not n.startswith("clustering") and n != "baseline_score"],
                "baseline": ["baseline_score"],
                "rule_features": [n for n in feature_names if n.startswith("rule_")],
                "graph_features": [n for n in feature_names if n.startswith("node_") or n.startswith("neighbor_") or n.startswith("edge_") or n.startswith("subnet_") or n.startswith("is_hub") or n.startswith("betweenness") or n.startswith("clustering")],
            },
            "threshold": threshold,
            "experiment_config": experiment_config,
            "evaluation": eval_metrics,
        }
        RANKER_META_PATH.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  模型文件: {RANKER_MODEL_PATH}")
        print(f"  元数据:   {RANKER_META_PATH}")
    else:
        print("  未训练监督模型（将使用 fallback 加权融合模式）")

    # 保存评估报告
    report: dict = {
        "experiment_config": experiment_config,
        "threshold": threshold,
    }
    if eval_metrics:
        report["composite_final"] = eval_metrics
    if comparison is not None:
        report["baseline_only"] = comparison["baseline"]
        report["delta"] = comparison["delta"]
        report["comparison_summary"] = comparison["summary"]

    REPORT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  评估报告: {REPORT_PATH}")

    print()
    print("训练完成！")


if __name__ == "__main__":
    main()

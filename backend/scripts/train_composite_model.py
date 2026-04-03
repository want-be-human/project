#!/usr/bin/env python3
"""
复合检测模型离线训练脚本。

训练 3 层复合检测架构中的所有模型：
  [1/7] 解析 PCAP（正常 + 攻击样本）
  [2/7] 提取 flow 统计特征
  [3/7] Layer 1: 训练 IsolationForest 基线模型
  [4/7] Layer 2: 计算规则语义特征
  [5/7] 构建图结构特征
  [6/7] Layer 3: 训练监督模型（LightGBM / XGBoost）
  [7/7] 评估 + 持久化

用法：
    cd backend
    python -m scripts.train_composite_model
    python -m scripts.train_composite_model --pcap-normal data/pcaps/training_normal.pcap \\
                                            --pcap-attack data/pcaps/training_attack.pcap
    python -m scripts.train_composite_model --model-type xgboost
    python -m scripts.train_composite_model --mode semi-supervised
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
        X_val, y_val: 验证集
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


def main():
    ap = argparse.ArgumentParser(description="复合检测模型离线训练")
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
    args = ap.parse_args()

    # ── [1/7] 解析 PCAP ──
    print(f"[1/7] 解析正常流量 PCAP: {args.pcap_normal}")
    if not args.pcap_normal.exists():
        print(f"  正常流量 PCAP 不存在，尝试自动生成...")
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

    # ── [2/7] 特征已在 parse_and_extract 中提取 ──
    print(f"[2/7] 特征提取完成: {len(all_flows)} 条流")

    # ── [3/7] Layer 1: 基线检测 ──
    print("[3/7] Layer 1: IsolationForest 基线评分...")
    baseline = BaselineDetector(mode="runtime", model_params={"contamination": args.contamination})
    all_flows = baseline.score(all_flows)
    baselines = [f.get("_detection", {}).get("baseline_score", 0) for f in all_flows]
    print(f"  baseline_score: min={min(baselines):.4f}, max={max(baselines):.4f}, "
          f"mean={sum(baselines)/len(baselines):.4f}")

    # ── [4/7] Layer 2: 规则特征 ──
    print("[4/7] Layer 2: 规则语义特征...")
    enricher = RuleEnricher()
    all_flows = enricher.enrich(all_flows)
    rule_scores = [f.get("_detection", {}).get("rule_score", 0) for f in all_flows]
    print(f"  rule_score: min={min(rule_scores):.4f}, max={max(rule_scores):.4f}")

    # ── [5/7] 图特征 ──
    print("[5/7] 图结构特征...")
    graph_builder = GraphFeatureBuilder()
    all_flows = graph_builder.build_and_extract(all_flows)
    graph_scores = [f.get("_detection", {}).get("graph_score", 0) for f in all_flows]
    print(f"  graph_score: min={min(graph_scores):.4f}, max={max(graph_scores):.4f}")

    # ── [6/7] Layer 3: 训练监督模型 ──
    print("[6/7] Layer 3: 构建特征矩阵并训练监督模型...")
    pipeline = FeaturePipeline()
    feature_names, feature_matrix = pipeline.build_feature_matrix(all_flows)
    X = np.array(feature_matrix)
    y = np.array([f.get("_label", 0) for f in all_flows])
    print(f"  特征矩阵: {X.shape[0]} 样本 × {X.shape[1]} 特征")
    print(f"  标签分布: 正常={int((y == 0).sum())}, 异常={int((y == 1).sum())}")

    model = None
    threshold = 0.7
    eval_metrics: dict = {}

    if has_attack and y.sum() >= 3:
        from sklearn.model_selection import train_test_split

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.3, random_state=42, stratify=y
        )

        if args.mode == "semi-supervised":
            # 半监督：将部分训练集标签移除
            n_labeled = max(int(len(y_train) * 0.3), 5)
            X_labeled = X_train[:n_labeled]
            y_labeled = y_train[:n_labeled]
            X_unlabeled = X_train[n_labeled:]
            model = train_semi_supervised(X_labeled, y_labeled, X_unlabeled)
        else:
            model = train_supervised(X_train, y_train, X_test, y_test, args.model_type)

        # 评估
        if hasattr(model, "predict_proba"):
            test_scores = model.predict_proba(X_test)[:, 1]
        else:
            test_scores = model.predict(X_test)

        # 阈值校准
        threshold = calibrate_threshold(y_test, test_scores)
        print(f"  最优阈值: {threshold}")

        # 计算指标
        evaluator = Evaluator()
        eval_metrics = evaluator.compute_metrics(y_test, test_scores, threshold)
        print(f"  ROC-AUC: {eval_metrics.get('roc_auc')}")
        print(f"  PR-AUC:  {eval_metrics.get('pr_auc')}")
        print(f"  F1:      {eval_metrics.get('f1')}")
        print(f"  Precision: {eval_metrics.get('precision')}")
        print(f"  Recall:    {eval_metrics.get('recall')}")

        # baseline vs composite 对比
        baseline_test = np.array([
            all_flows[i].get("_detection", {}).get("baseline_score", 0)
            for i in range(len(all_flows))
        ])
        # 需要对齐测试集索引
        _, baseline_test_split, _, _ = train_test_split(
            baseline_test, y, test_size=0.3, random_state=42, stratify=y
        )
        comparison = evaluator.compare_models(y_test, baseline_test_split, test_scores, threshold)
        print(f"  对比摘要: {comparison.get('summary')}")
    else:
        print("  无攻击样本或样本不足，跳过监督模型训练")

    # ── [7/7] 持久化 ──
    print("[7/7] 保存模型...")
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
            "training_samples": int(X.shape[0]),
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
    if eval_metrics:
        REPORT_PATH.write_text(
            json.dumps({"evaluation": eval_metrics, "threshold": threshold},
                       indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  评估报告: {REPORT_PATH}")

    print()
    print("训练完成！")


if __name__ == "__main__":
    main()

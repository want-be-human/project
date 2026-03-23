#!/usr/bin/env python3
"""
离线训练 IsolationForest 模型并持久化。

使用项目模拟数据（training_normal.pcap）作为训练样本，
生成 flow_iforest.joblib 和 flow_iforest.meta.json。

用法：
    cd backend
    python -m scripts.train_flow_model
    python -m scripts.train_flow_model --pcap data/pcaps/my_training.pcap
    python -m scripts.train_flow_model --contamination 0.05 --n-estimators 200
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# 将 backend/ 加入 sys.path，以便直接 import app 模块
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.services.parsing.service import ParsingService
from app.services.features.service import FeaturesService
from app.services.detection.service import DetectionService

# 模型输出目录
MODEL_DIR = BACKEND_DIR / "models"
MODEL_PATH = MODEL_DIR / "flow_iforest.joblib"
META_PATH = MODEL_DIR / "flow_iforest.meta.json"

# 默认训练 PCAP 路径
DEFAULT_PCAP = BACKEND_DIR / "data" / "pcaps" / "training_normal.pcap"


def ensure_training_pcap(pcap_path: Path) -> None:
    """若训练 PCAP 不存在，自动调用生成脚本创建。"""
    if pcap_path.exists():
        return
    print(f"训练 PCAP 不存在: {pcap_path}")
    print("正在自动生成训练用正常流量 PCAP ...")
    from scripts.generate_demo_pcaps import generate_training_pcap
    pcap_path.parent.mkdir(parents=True, exist_ok=True)
    generate_training_pcap(pcap_path)


def build_feature_matrix(flows: list[dict], feature_names: list[str]) -> np.ndarray:
    """从 flow 字典列表中提取特征矩阵，特征顺序与 feature_names 一致。"""
    rows = []
    for flow in flows:
        features = flow.get("features", {})
        row = [float(features.get(name, 0)) for name in feature_names]
        rows.append(row)
    return np.array(rows)


def train(pcap_path: Path, contamination: float, n_estimators: int) -> None:
    """执行完整的训练流程。"""
    from sklearn.ensemble import IsolationForest
    import sklearn
    import joblib

    # ── 1. 解析 PCAP 为 flow ──
    print(f"[1/5] 解析 PCAP: {pcap_path}")
    parser = ParsingService()
    flows = parser.parse_to_flows(pcap_path)
    print(f"      解析得到 {len(flows)} 条流")

    if len(flows) < 5:
        print("错误：训练样本不足（至少需要 5 条流），请检查 PCAP 文件")
        sys.exit(1)

    # ── 2. 提取特征 ──
    print("[2/5] 提取特征 ...")
    feat_svc = FeaturesService()
    flows = feat_svc.extract_features_batch(flows)

    # ── 3. 构建特征矩阵 ──
    # 使用 DetectionService 定义的 18 个核心特征
    feature_names = list(DetectionService.DEFAULT_FEATURE_NAMES)
    X = build_feature_matrix(flows, feature_names)
    print(f"[3/5] 特征矩阵: {X.shape[0]} 样本 × {X.shape[1]} 特征")

    # ── 4. 训练 IsolationForest ──
    print(f"[4/5] 训练 IsolationForest (contamination={contamination}, n_estimators={n_estimators}) ...")
    model = IsolationForest(
        contamination=contamination,
        n_estimators=n_estimators,
        random_state=42,
    )
    model.fit(X)

    # 计算归一化参数：与 service.py 中的归一化逻辑一致
    raw_scores = model.score_samples(X)
    neg_scores = -raw_scores
    p5, p95 = float(np.percentile(neg_scores, 5)), float(np.percentile(neg_scores, 95))

    print(f"      归一化参数: p5={p5:.6f}, p95={p95:.6f}")

    # ── 5. 持久化 ──
    print("[5/5] 保存模型 ...")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    joblib.dump(model, MODEL_PATH)

    meta = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sklearn_version": sklearn.__version__,
        "model_params": {
            "n_estimators": n_estimators,
            "contamination": contamination,
            "random_state": 42,
        },
        "feature_names": feature_names,
        "normalization": {"p5": p5, "p95": p95},
        "suggested_threshold": 0.7,
        "training_samples": int(X.shape[0]),
        "training_source": pcap_path.name,
    }
    META_PATH.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print("训练完成！")
    print(f"  模型文件: {MODEL_PATH}")
    print(f"  元数据:   {META_PATH}")
    print(f"  训练样本: {X.shape[0]} 条流")
    print(f"  特征数:   {X.shape[1]}")
    print(f"  p5={p5:.6f}, p95={p95:.6f}")


def main():
    parser = argparse.ArgumentParser(description="离线训练 IsolationForest 流量异常检测模型")
    parser.add_argument("--pcap", type=Path, default=DEFAULT_PCAP, help="训练用 PCAP 文件路径")
    parser.add_argument("--contamination", type=float, default=0.1, help="异常比例参数 (默认 0.1)")
    parser.add_argument("--n-estimators", type=int, default=100, help="IsolationForest 树数量 (默认 100)")
    args = parser.parse_args()

    ensure_training_pcap(args.pcap)
    train(args.pcap, args.contamination, args.n_estimators)


if __name__ == "__main__":
    main()

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
import time
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

# TensorBoard 日志默认目录
DEFAULT_TB_DIR = BACKEND_DIR / "runs"


def ensure_training_pcap(pcap_path: Path) -> None:
    """若训练 PCAP 不存在，自动调用生成脚本创建。"""
    if pcap_path.exists():
        return
    print(f"训练 PCAP 不存在: {pcap_path}")
    print("正在自动生成训练用正常流量 PCAP ...")
    from scripts.generate_demo_pcaps import generate_training_pcap
    pcap_path.parent.mkdir(parents=True, exist_ok=True)
    generate_training_pcap(pcap_path)


def train(pcap_path: Path, contamination: float, n_estimators: int, tb_dir: Path) -> None:
    """执行完整的训练流程。"""
    from sklearn.ensemble import IsolationForest
    import sklearn
    import joblib
    from tensorboardX import SummaryWriter

    # ── TensorBoard 初始化 ──
    run_name = f"baseline_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    log_dir = tb_dir / run_name
    writer = SummaryWriter(str(log_dir))
    print(f"TensorBoard 日志: {log_dir}")
    print(f"  启动查看: tensorboard --logdir {tb_dir}")

    writer.add_text("config/pcap", pcap_path.name, 0)
    writer.add_text("config/model", "IsolationForest (sklearn, CPU)", 0)

    t_start = time.time()

    # ── 1. 解析 PCAP 为 flow ──
    print(f"[1/5] 解析 PCAP: {pcap_path}")
    t0 = time.time()
    parser = ParsingService()
    flows = parser.parse_to_flows(pcap_path)
    parse_time = time.time() - t0
    print(f"      解析得到 {len(flows)} 条流 (耗时 {parse_time:.1f}s)")
    writer.add_scalar("timing/parse_sec", parse_time, 0)
    writer.add_scalar("dataset/total_flows", len(flows), 0)

    if len(flows) < 5:
        print("错误：训练样本不足（至少需要 5 条流），请检查 PCAP 文件")
        writer.close()
        sys.exit(1)

    # ── 2. 提取特征 ──
    print("[2/5] 提取特征 ...")
    t0 = time.time()
    feat_svc = FeaturesService()
    flows = feat_svc.extract_features_batch(flows)
    feat_time = time.time() - t0
    print(f"      特征提取耗时 {feat_time:.1f}s")
    writer.add_scalar("timing/feature_extraction_sec", feat_time, 0)

    # ── 3. 构建特征矩阵 ──
    # 复用 DetectionService._flows_to_matrix，保证训练与推理的特征编码一致
    det_svc = DetectionService(mode="runtime")
    feature_names = list(det_svc.feature_names)
    X = det_svc._flows_to_matrix(flows)
    print(f"[3/5] 特征矩阵: {X.shape[0]} 样本 × {X.shape[1]} 特征")
    writer.add_scalar("dataset/n_features", X.shape[1], 0)

    # 记录特征统计
    for i, fname in enumerate(feature_names):
        col = X[:, i]
        writer.add_scalar(f"feature_stats/{fname}_mean", float(np.mean(col)), 0)
        writer.add_scalar(f"feature_stats/{fname}_std", float(np.std(col)), 0)

    # ── 4. 训练 IsolationForest ──
    # 注意：sklearn IsolationForest 不支持 GPU，仅 CPU 训练
    print(f"[4/5] 训练 IsolationForest (contamination={contamination}, n_estimators={n_estimators}) ...")
    print("      注意: IsolationForest 为 CPU 训练（sklearn 不支持 GPU）")
    t0 = time.time()
    model = IsolationForest(
        contamination=contamination,
        n_estimators=n_estimators,
        random_state=42,
    )
    model.fit(X)
    train_time = time.time() - t0
    print(f"      训练耗时 {train_time:.1f}s")
    writer.add_scalar("timing/train_sec", train_time, 0)

    # 计算归一化参数：与 service.py 中的归一化逻辑一致
    raw_scores = model.score_samples(X)
    neg_scores = -raw_scores
    p5, p95 = float(np.percentile(neg_scores, 5)), float(np.percentile(neg_scores, 95))

    print(f"      归一化参数: p5={p5:.6f}, p95={p95:.6f}")

    # 归一化分数
    spread = max(p95 - p5, 1e-9)
    normalized = np.clip((neg_scores - p5) / spread, 0.0, 1.0)

    # TensorBoard 记录分数分布
    writer.add_histogram("scores/raw_neg_scores", neg_scores, 0)
    writer.add_histogram("scores/normalized", normalized, 0)
    writer.add_scalar("normalization/p5", p5, 0)
    writer.add_scalar("normalization/p95", p95, 0)
    writer.add_scalar("normalization/spread", spread, 0)
    writer.add_scalar("scores/mean", float(np.mean(normalized)), 0)
    writer.add_scalar("scores/median", float(np.median(normalized)), 0)
    writer.add_scalar("scores/max", float(np.max(normalized)), 0)
    writer.add_scalar("scores/above_0.7", float((normalized >= 0.7).sum()) / len(normalized), 0)
    writer.add_scalar("scores/above_0.5", float((normalized >= 0.5).sum()) / len(normalized), 0)

    # 超参数记录
    writer.add_hparams(
        {
            "contamination": contamination,
            "n_estimators": n_estimators,
            "training_samples": X.shape[0],
        },
        {
            "hparam/p5": p5,
            "hparam/p95": p95,
            "hparam/spread": spread,
            "hparam/score_mean": float(np.mean(normalized)),
        },
    )

    total_time = time.time() - t_start
    writer.add_scalar("timing/total_sec", total_time, 0)

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

    writer.close()

    print()
    print("训练完成！")
    print(f"  模型文件: {MODEL_PATH}")
    print(f"  元数据:   {META_PATH}")
    print(f"  训练样本: {X.shape[0]} 条流")
    print(f"  特征数:   {X.shape[1]}")
    print(f"  p5={p5:.6f}, p95={p95:.6f}")
    print(f"  总耗时:   {total_time:.1f}s")
    print(f"  TensorBoard: tensorboard --logdir {tb_dir}")


def main():
    parser = argparse.ArgumentParser(description="离线训练 IsolationForest 流量异常检测模型")
    parser.add_argument("--pcap", type=Path, default=DEFAULT_PCAP, help="训练用 PCAP 文件路径")
    parser.add_argument("--contamination", type=float, default=0.1, help="异常比例参数 (默认 0.1)")
    parser.add_argument("--n-estimators", type=int, default=100, help="IsolationForest 树数量 (默认 100)")
    parser.add_argument("--tensorboard-dir", type=Path, default=DEFAULT_TB_DIR, help="TensorBoard 日志目录")
    args = parser.parse_args()

    ensure_training_pcap(args.pcap)
    train(args.pcap, args.contamination, args.n_estimators, args.tensorboard_dir)


if __name__ == "__main__":
    main()

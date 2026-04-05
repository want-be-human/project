"""
批量接入作业阶段定义。

每个阶段是一个独立函数，复用现有 service 完成实际处理。
阶段顺序：validate → store → parse → featurize → detect → aggregate → persist_result
"""

import hashlib
import json
import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.core.utils import generate_uuid, sanitize_filename, utc_now, compute_file_hash
from app.models.batch import BatchFile, Job
from app.models.flow import Flow
from app.models.alert import Alert, alert_flows
from app.models.pcap import PcapFile

logger = get_logger(__name__)

# 阶段执行顺序
STAGE_ORDER = [
    "validate", "store", "parse", "featurize",
    "detect", "aggregate", "persist_result",
]

# 阶段 → BatchFile 状态映射
STAGE_TO_FILE_STATUS = {
    "validate": "queued",
    "store": "queued",
    "parse": "parsing",
    "featurize": "featurizing",
    "detect": "detecting",
    "aggregate": "aggregating",
    "persist_result": "aggregating",
}

# PCAP 魔数列表
_VALID_PCAP_MAGICS = [
    b"\xa1\xb2\xc3\xd4",  # PCAP 大端
    b"\xd4\xc3\xb2\xa1",  # PCAP 小端
    b"\xa1\xb2\x3c\x4d",  # PCAP-NG 大端（变体）
    b"\x4d\x3c\xb2\xa1",  # PCAP-NG 小端（变体）
    b"\x0a\x0d\x0d\x0a",  # PCAP-NG Section Header Block
]


def _compute_sha256(content: bytes) -> str:
    """计算内容的 sha256 哈希值。"""
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


# ── 阶段 1：校验 ──────────────────────────────────────────────

def stage_validate(
    db: Session, job: Job, batch_file: BatchFile, staging_path: Path,
) -> dict:
    """
    校验 PCAP 文件完整性。

    检查暂存文件是否存在、魔数是否合法。
    返回 {"sha256": str, "size_bytes": int}。
    不再全量读取文件到内存。
    """
    if not staging_path.exists():
        raise FileNotFoundError(f"暂存文件不存在: {staging_path}")

    size_bytes = staging_path.stat().st_size

    if size_bytes < 4:
        raise ValueError("文件过小，不是有效的 PCAP 文件")

    # 魔数校验：只读前 4 字节
    with open(staging_path, "rb") as f:
        magic = f.read(4)
    if magic not in _VALID_PCAP_MAGICS:
        raise ValueError(f"无效的 PCAP 魔数: {magic.hex()}")

    # 流式计算 sha256（如果上传时未计算）
    sha256 = batch_file.sha256 or compute_file_hash(staging_path)

    # 更新 batch_file 元数据
    batch_file.sha256 = sha256
    batch_file.size_bytes = size_bytes
    db.flush()

    return {"sha256": sha256, "size_bytes": size_bytes}


# ── 阶段 2：落盘 ──────────────────────────────────────────────

def stage_store(
    db: Session, job: Job, batch_file: BatchFile, staging_path: Path,
) -> dict:
    """
    将暂存文件移动到 PCAP 存储目录，创建 PcapFile 记录。

    返回 {"pcap_id": str, "storage_path": str}。
    使用 shutil.move 避免全量读取（同盘 rename 零拷贝，跨盘自动 copy+delete）。
    """
    import shutil

    pcap_id = generate_uuid()
    safe_filename = sanitize_filename(batch_file.original_filename)
    storage_path = settings.PCAP_DIR / f"{pcap_id}.pcap"

    # 移动到正式存储位置（零拷贝或流式拷贝）
    shutil.move(str(staging_path), str(storage_path))

    # 创建 PcapFile 记录（与现有 IngestionService.save_pcap 逻辑一致）
    pcap_record = PcapFile(
        id=pcap_id,
        filename=safe_filename,
        storage_path=str(storage_path),
        sha256=batch_file.sha256,
        size_bytes=batch_file.size_bytes,
        status="uploaded",
        progress=0,
        flow_count=0,
        alert_count=0,
    )
    db.add(pcap_record)
    db.flush()

    # 关联 batch_file → pcap
    batch_file.pcap_id = pcap_id
    job.pcap_id = pcap_id
    db.flush()

    # shutil.move 已处理暂存文件，无需手动删除

    logger.info(f"文件已落盘: {pcap_id} ({batch_file.size_bytes} bytes)")
    return {"pcap_id": pcap_id, "storage_path": str(storage_path)}


# ── 阶段 3：解析 ──────────────────────────────────────────────

def stage_parse(
    db: Session, job: Job, batch_file: BatchFile, window_sec: int = 60,
) -> list[dict]:
    """
    解析 PCAP 文件为 flow 字典列表。

    复用 ParsingService.parse_to_flows()。
    """
    from app.services.parsing.service import ParsingService

    pcap = db.query(PcapFile).filter(PcapFile.id == batch_file.pcap_id).first()
    if not pcap:
        raise RuntimeError(f"PcapFile 不存在: {batch_file.pcap_id}")

    parser = ParsingService()
    flow_dicts = parser.parse_to_flows(Path(pcap.storage_path), window_sec=window_sec)

    logger.info(f"解析完成: {batch_file.pcap_id}, {len(flow_dicts)} flows")
    return flow_dicts


# ── 阶段 4：特征提取 ──────────────────────────────────────────

def stage_featurize(
    db: Session, job: Job, batch_file: BatchFile, flow_dicts: list[dict],
) -> list[dict]:
    """
    为 flow 提取特征。

    复用 FeaturesService.extract_features_batch()。
    """
    from app.services.features.service import FeaturesService

    feat_svc = FeaturesService()
    flow_dicts = feat_svc.extract_features_batch(flow_dicts)

    logger.info(f"特征提取完成: {batch_file.pcap_id}, {len(flow_dicts)} flows")
    return flow_dicts


# ── 阶段 5：检测 ──────────────────────────────────────────────

def stage_detect(
    db: Session, job: Job, batch_file: BatchFile, flow_dicts: list[dict],
) -> list[dict]:
    """
    异常评分。

    复用 CompositeDetectionService.score_flows()。
    """
    from app.services.detection.composite import get_composite_detector

    det_svc = get_composite_detector()
    flow_dicts = det_svc.score_flows(flow_dicts)

    scored = [f for f in flow_dicts if f.get("anomaly_score") is not None]
    logger.info(f"检测完成: {batch_file.pcap_id}, {len(scored)} scored flows")
    return flow_dicts


# ── 阶段 6：聚合告警 ──────────────────────────────────────────

def stage_aggregate(
    db: Session, job: Job, batch_file: BatchFile,
    flow_dicts: list[dict], window_sec: int = 60,
) -> list[dict]:
    """
    生成告警。

    复用 AlertingService.generate_alerts()。
    """
    from app.services.alerting.service import AlertingService

    alert_svc = AlertingService(score_threshold=0.7, window_sec=window_sec)
    alert_dicts = alert_svc.generate_alerts(flow_dicts, batch_file.pcap_id)

    logger.info(f"聚合完成: {batch_file.pcap_id}, {len(alert_dicts)} alerts")
    return alert_dicts


# ── 阶段 7：持久化结果 ────────────────────────────────────────

def stage_persist_result(
    db: Session, job: Job, batch_file: BatchFile,
    flow_dicts: list[dict], alert_dicts: list[dict],
) -> dict:
    """
    将 flows 和 alerts 写入数据库，更新 PcapFile 状态。

    复用 pcaps.py 中的入库逻辑。
    返回 {"flow_count": int, "alert_count": int}。
    """
    pcap_id = batch_file.pcap_id

    # ── 高性能 bulk insert flows（Core insert，绕过 ORM 开销）──
    BULK_SIZE = 50_000
    flow_rows = [
        {
            "id": fd["id"],
            "version": fd.get("version", "1.1"),
            "created_at": fd["created_at"],
            "pcap_id": pcap_id,
            "ts_start": fd["ts_start"],
            "ts_end": fd["ts_end"],
            "src_ip": fd["src_ip"],
            "src_port": fd["src_port"],
            "dst_ip": fd["dst_ip"],
            "dst_port": fd["dst_port"],
            "proto": fd["proto"],
            "packets_fwd": fd["packets_fwd"],
            "packets_bwd": fd["packets_bwd"],
            "bytes_fwd": fd["bytes_fwd"],
            "bytes_bwd": fd["bytes_bwd"],
            "features": json.dumps(fd.get("features", {})),
            "anomaly_score": fd.get("anomaly_score"),
            "label": fd.get("label"),
        }
        for fd in flow_dicts
    ]
    flow_table = Flow.__table__
    for i in range(0, len(flow_rows), BULK_SIZE):
        db.execute(flow_table.insert(), flow_rows[i:i + BULK_SIZE])
    db.flush()

    # ── 高性能 bulk insert alerts ──
    alert_count = 0
    alert_flow_links: list[dict] = []
    for ad in alert_dicts:
        flow_ids_for_alert = ad.pop("_flow_ids", [])
        db.execute(
            Alert.__table__.insert(),
            [{
                "id": ad["id"],
                "version": ad.get("version", "1.1"),
                "created_at": ad["created_at"],
                "severity": ad["severity"],
                "status": ad["status"],
                "type": ad["type"],
                "time_window_start": ad["time_window_start"],
                "time_window_end": ad["time_window_end"],
                "primary_src_ip": ad["primary_src_ip"],
                "primary_dst_ip": ad["primary_dst_ip"],
                "primary_proto": ad["primary_proto"],
                "primary_dst_port": ad["primary_dst_port"],
                "evidence": ad["evidence"],
                "aggregation": ad["aggregation"],
                "agent": ad["agent"],
                "twin": ad["twin"],
                "tags": ad["tags"],
                "notes": ad.get("notes", ""),
            }],
        )
        for fid in flow_ids_for_alert:
            alert_flow_links.append({"alert_id": ad["id"], "flow_id": fid, "role": "top"})
        alert_count += 1

    if alert_flow_links:
        for i in range(0, len(alert_flow_links), BULK_SIZE):
            db.execute(alert_flows.insert(), alert_flow_links[i:i + BULK_SIZE])

    # 单次 commit（一次 fsync，而非之前的 2500+ 次）
    db.commit()

    # 更新 PcapFile 状态
    flow_count = len(flow_dicts)
    pcap = db.query(PcapFile).filter(PcapFile.id == pcap_id).first()
    if pcap:
        pcap.status = "done"
        pcap.progress = 100
        pcap.flow_count = flow_count
        pcap.alert_count = alert_count

    db.flush()

    logger.info(f"持久化完成: {pcap_id}, {flow_count} flows, {alert_count} alerts")
    return {"flow_count": flow_count, "alert_count": alert_count}

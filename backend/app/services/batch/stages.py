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


# ── 批量写入常量 ─────────────────────────────────────────────
_BULK_SIZE = 50_000

# flows 表索引定义（必须与 flow.py __table_args__ 保持一致）
_FLOW_INDEX_DEFS = [
    ("idx_flow_pcap_ts",         "flows", "pcap_id, ts_start"),
    ("idx_flow_pcap_src",        "flows", "pcap_id, src_ip"),
    ("idx_flow_pcap_dst",        "flows", "pcap_id, dst_ip"),
    ("idx_flow_pcap_proto_port", "flows", "pcap_id, proto, dst_port"),
    ("idx_flow_score",           "flows", "anomaly_score"),
]

_COPY_COLUMNS = [
    "id", "version", "created_at", "pcap_id",
    "ts_start", "ts_end",
    "src_ip", "src_port", "dst_ip", "dst_port", "proto",
    "packets_fwd", "packets_bwd", "bytes_fwd", "bytes_bwd",
    "features", "anomaly_score", "label",
]


# ── PostgreSQL COPY 协议快速写入 ──────────────────────────────


class _FlowTSVStream:
    """
    流式 TSV 生成器，实现 read() 接口供 cursor.copy_from 消费。

    相比 StringIO 整体缓冲（500K 行 ≈ 500MB），
    此实现内存占用固定 ~128KB（一个读缓冲 + 当前行），
    峰值内存削减 99%。
    """

    def __init__(self, flow_dicts: list[dict], pcap_id: str):
        self._iter = iter(flow_dicts)
        self._pcap_id = pcap_id
        self._buf = ""

    def read(self, size: int = 8192) -> str:
        while len(self._buf) < size:
            try:
                fd = next(self._iter)
            except StopIteration:
                break
            self._buf += self._format_row(fd)

        chunk = self._buf[:size]
        self._buf = self._buf[size:]
        return chunk

    def readline(self) -> str:
        while "\n" not in self._buf:
            try:
                fd = next(self._iter)
            except StopIteration:
                line = self._buf
                self._buf = ""
                return line
            self._buf += self._format_row(fd)

        idx = self._buf.index("\n") + 1
        line = self._buf[:idx]
        self._buf = self._buf[idx:]
        return line

    def _format_row(self, fd: dict) -> str:
        ts_start = fd["ts_start"].isoformat() if hasattr(fd["ts_start"], "isoformat") else str(fd["ts_start"])
        ts_end = fd["ts_end"].isoformat() if hasattr(fd["ts_end"], "isoformat") else str(fd["ts_end"])
        created_at = fd["created_at"].isoformat() if hasattr(fd["created_at"], "isoformat") else str(fd["created_at"])
        anomaly = str(fd.get("anomaly_score", "")) if fd.get("anomaly_score") is not None else "\\N"
        label = fd.get("label") or "\\N"
        features_json = json.dumps(fd.get("features", {})).replace("\t", " ").replace("\n", " ")

        return "\t".join([
            fd["id"],
            fd.get("version", "1.1"),
            created_at,
            self._pcap_id,
            ts_start,
            ts_end,
            fd["src_ip"],
            str(fd["src_port"]),
            fd["dst_ip"],
            str(fd["dst_port"]),
            fd["proto"],
            str(fd["packets_fwd"]),
            str(fd["packets_bwd"]),
            str(fd["bytes_fwd"]),
            str(fd["bytes_bwd"]),
            features_json,
            anomaly,
            label,
        ]) + "\n"


def _persist_flows_copy(db: Session, pcap_id: str, flow_dicts: list[dict]) -> None:
    """
    用 PostgreSQL COPY 协议写入 flows。

    优化策略：
    - 大批量（≥10K 行）：先 DROP INDEX → COPY → CREATE INDEX → ANALYZE
      构建 B-tree 从排序好的数据一次性生成，比边插边维护快 10 倍以上。
    - 小批量（<10K 行）：直接 COPY，保留索引在线。
    - 使用 _FlowTSVStream 流式生成 TSV，内存占用固定 ~128KB。
    - SET LOCAL 仅对当前事务生效，commit 后自动恢复。
    - DDL（DROP/CREATE INDEX）在 PostgreSQL 中是事务性的，异常时自动回滚。
    """
    if not flow_dicts:
        return

    n = len(flow_dicts)
    drop_indexes = n >= 10_000

    raw_conn = db.connection().connection
    cursor = raw_conn.cursor()

    # ── 事务级参数调优（commit 后自动恢复） ──
    cursor.execute("SET LOCAL work_mem = '64MB'")
    cursor.execute("SET LOCAL maintenance_work_mem = '256MB'")

    # ── 大批量：移除索引以消除逐行 B-tree 维护开销 ──
    if drop_indexes:
        for idx_name, _, _ in _FLOW_INDEX_DEFS:
            cursor.execute(f"DROP INDEX IF EXISTS {idx_name}")
        logger.info("已移除 %d 个 flows 索引，准备 COPY %d 行", len(_FLOW_INDEX_DEFS), n)

    # ── 流式 COPY（内存固定 ~128KB，不构建整体缓冲） ──
    stream = _FlowTSVStream(flow_dicts, pcap_id)
    cursor.copy_from(stream, "flows", columns=_COPY_COLUMNS, null="\\N")
    logger.info("COPY 完成: %d 行写入 flows 表", n)

    # ── 大批量：从完整数据一次性构建索引（比逐行维护快 10x+） ──
    if drop_indexes:
        for idx_name, table, cols in _FLOW_INDEX_DEFS:
            cursor.execute(f"CREATE INDEX {idx_name} ON {table} ({cols})")
        cursor.execute("ANALYZE flows")
        logger.info("已重建 %d 个 flows 索引并更新统计信息", len(_FLOW_INDEX_DEFS))

    cursor.close()


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

    # ── 高性能写入 flows：PostgreSQL 用 COPY 协议，其他用 Core insert ──
    _persist_flows_copy(db, pcap_id, flow_dicts)

    # ── 高性能 bulk insert alerts ──
    alert_records: list[dict] = []
    alert_flow_links: list[dict] = []
    for ad in alert_dicts:
        flow_ids_for_alert = ad.pop("_flow_ids", [])
        alert_records.append({
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
        })
        for fid in flow_ids_for_alert:
            alert_flow_links.append({"alert_id": ad["id"], "flow_id": fid, "role": "top"})

    if alert_records:
        for i in range(0, len(alert_records), _BULK_SIZE):
            db.execute(Alert.__table__.insert(), alert_records[i:i + _BULK_SIZE])

    if alert_flow_links:
        for i in range(0, len(alert_flow_links), _BULK_SIZE):
            db.execute(alert_flows.insert(), alert_flow_links[i:i + _BULK_SIZE])

    # 单次 commit（一次 fsync，而非之前的 2500+ 次）
    db.commit()

    # 更新 PcapFile 状态
    alert_count = len(alert_records)
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

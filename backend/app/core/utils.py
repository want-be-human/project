"""
通用工具函数。
"""

import uuid
import hashlib
from datetime import datetime, timezone
from pathlib import Path


def generate_uuid() -> str:
    """生成新的 UUID 字符串。"""
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """获取当前 UTC 时间。"""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """获取当前 UTC 时间的 ISO8601 字符串。"""
    return datetime_to_iso(utc_now())


def datetime_to_iso(dt: datetime) -> str:
    """将 datetime 转换为 ISO8601 UTC 字符串（保留子秒精度）。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if dt.microsecond:
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_to_datetime(iso_str: str) -> datetime:
    """将 ISO8601 字符串解析为 datetime。"""
    # 同时兼容带微秒和不带微秒的时间格式
    for fmt in ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"]:
        try:
            return datetime.strptime(iso_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Invalid ISO8601 format: {iso_str}")


def compute_file_hash(file_path: Path, algorithm: str = "sha256") -> str:
    """计算文件哈希值。"""
    hash_func = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_func.update(chunk)
    return f"{algorithm}:{hash_func.hexdigest()}"


def is_valid_pcap_filename(filename: str) -> bool:
    """检查文件名是否为有效的 pcap 扩展名。"""
    lower = filename.lower()
    return lower.endswith(".pcap") or lower.endswith(".pcapng")


def sanitize_filename(filename: str) -> str:
    """清洗文件名以便安全存储。"""
    # 去除路径分隔符和潜在危险字符
    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    return "".join(c if c in safe_chars else "_" for c in filename)

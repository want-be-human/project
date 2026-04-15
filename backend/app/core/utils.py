import uuid
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

_CHUNK = 65536  # 64 KB

_PCAP_SUFFIXES = (".pcap", ".pcapng")
_SAFE_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
)


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """带 tzinfo 的当前 UTC 时间，PostgreSQL 兼容。"""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return datetime_to_iso(utc_now())


def datetime_to_iso(dt: datetime) -> str:
    """ISO8601 UTC，保留子秒精度。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if dt.microsecond:
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_to_datetime(iso_str: str) -> datetime:
    # 兼容带微秒与不带微秒两种格式
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            return datetime.strptime(iso_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Invalid ISO8601 format: {iso_str}")


def compute_file_hash(file_path: Path, algorithm: str = "sha256") -> str:
    """流式计算，内存占用固定 64KB。"""
    h = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return f"{algorithm}:{h.hexdigest()}"


def stream_save_and_hash(
    src: BinaryIO,
    dst_path: Path,
    algorithm: str = "sha256",
) -> tuple[int, str, bytes]:
    """流式写入并同步计算哈希；返回 (size, "algo:hex", 前4字节 magic)。"""
    h = hashlib.new(algorithm)
    size = 0
    magic = b""
    with open(dst_path, "wb") as out:
        while True:
            chunk = src.read(_CHUNK)
            if not chunk:
                break
            if size == 0:
                magic = chunk[:4]
            out.write(chunk)
            h.update(chunk)
            size += len(chunk)
    return size, f"{algorithm}:{h.hexdigest()}", magic


def is_valid_pcap_filename(filename: str) -> bool:
    return filename.lower().endswith(_PCAP_SUFFIXES)


def sanitize_filename(filename: str) -> str:
    return "".join(c if c in _SAFE_CHARS else "_" for c in filename)

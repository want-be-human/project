"""
Common utility functions.
"""

import uuid
import hashlib
from datetime import datetime, timezone
from pathlib import Path


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """Get current UTC datetime as ISO8601 string."""
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def datetime_to_iso(dt: datetime) -> str:
    """Convert datetime to ISO8601 UTC string."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_to_datetime(iso_str: str) -> datetime:
    """Parse ISO8601 string to datetime."""
    # Handle both with and without microseconds
    for fmt in ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"]:
        try:
            return datetime.strptime(iso_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Invalid ISO8601 format: {iso_str}")


def compute_file_hash(file_path: Path, algorithm: str = "sha256") -> str:
    """Compute hash of a file."""
    hash_func = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_func.update(chunk)
    return f"{algorithm}:{hash_func.hexdigest()}"


def is_valid_pcap_filename(filename: str) -> bool:
    """Check if filename has valid pcap extension."""
    lower = filename.lower()
    return lower.endswith(".pcap") or lower.endswith(".pcapng")


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe storage."""
    # Remove path separators and dangerous characters
    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    return "".join(c if c in safe_chars else "_" for c in filename)

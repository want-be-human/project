"""批量接入 ORM 模型：Batch → BatchFile → Job 三级管理结构。"""

from typing import Optional

from sqlalchemy import String, BigInteger, Integer, Float, Text, JSON, DateTime, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Batch(BaseModel):
    """批次：批量接入的管理单元，管理多个 PCAP 文件的上传与处理。"""

    __tablename__ = "batches"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="created",
    )
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tags: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    total_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_flow_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_alert_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    started_at: Mapped[Optional[str]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[str]] = mapped_column(DateTime(timezone=True), nullable=True)
    total_latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    files: Mapped[list["BatchFile"]] = relationship(
        "BatchFile", back_populates="batch", cascade="all, delete-orphan",
        order_by="BatchFile.sequence",
    )

    __table_args__ = (
        Index("idx_batch_status", "status"),
        Index("idx_batch_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Batch(id={self.id}, name={self.name}, status={self.status})>"


class BatchFile(BaseModel):
    """批次文件：每个文件对应一个 PCAP；校验通过后关联到 PcapFile 记录。"""

    __tablename__ = "batch_files"

    batch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("batches.id", ondelete="CASCADE"), nullable=False,
    )
    # 关联的 PcapFile（store 阶段后填充；删 pcap 时置 NULL 保留记录）
    pcap_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("pcap_files.id", ondelete="SET NULL"), nullable=True,
    )

    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sha256: Mapped[Optional[str]] = mapped_column(String(72), nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="accepted",
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    flow_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    alert_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reject_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    started_at: Mapped[Optional[str]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[str]] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    batch: Mapped["Batch"] = relationship("Batch", back_populates="files")
    pcap = relationship("PcapFile", lazy="select")
    jobs: Mapped[list["Job"]] = relationship(
        "Job", back_populates="batch_file", cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_bf_batch_id", "batch_id"),
        Index("idx_bf_status", "status"),
        Index("idx_bf_sha256", "sha256"),
    )

    def __repr__(self) -> str:
        return f"<BatchFile(id={self.id}, filename={self.original_filename}, status={self.status})>"


class Job(BaseModel):
    """job：负责处理一个文件的完整 pipeline 执行单元。"""

    __tablename__ = "jobs"

    batch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("batches.id", ondelete="CASCADE"), nullable=False,
    )
    batch_file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("batch_files.id", ondelete="CASCADE"), nullable=False,
    )
    pcap_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending",
    )
    current_stage: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    stages_log: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=2)

    started_at: Mapped[Optional[str]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[str]] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[Optional[str]] = mapped_column(DateTime(timezone=True), nullable=True)

    batch_file: Mapped["BatchFile"] = relationship("BatchFile", back_populates="jobs")

    __table_args__ = (
        Index("idx_job_batch_id", "batch_id"),
        Index("idx_job_status", "status"),
        Index("idx_job_bf", "batch_file_id"),
    )

    def __repr__(self) -> str:
        return f"<Job(id={self.id}, status={self.status}, stage={self.current_stage})>"

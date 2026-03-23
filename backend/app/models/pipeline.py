"""
用于 pipeline run 可观测性记录的 ORM 模型。
保存 PCAP 处理流水线的结构化阶段跟踪数据。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, Float, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class PipelineRunModel(BaseModel):
    """记录单个 PCAP 在所有阶段上的完整流水线执行。"""

    __tablename__ = "pipeline_runs"

    pcap_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        comment="该运行记录所属的 PCAP 文件 ID",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
        comment="pending | running | completed | failed",
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    total_latency_ms: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="流水线总耗时（毫秒）",
    )
    stages_log: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="StageRecord 字典的 JSON 列表",
    )

    __table_args__ = (
        Index("idx_pipeline_pcap_created", "pcap_id", "created_at"),
        Index("idx_pipeline_status", "status"),
    )

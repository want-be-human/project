"""
ORM model for pipeline run observability records.
Stores structured stage-level tracking for PCAP processing pipelines.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, Float, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class PipelineRunModel(BaseModel):
    """Tracks a full pipeline execution across all stages for a PCAP."""

    __tablename__ = "pipeline_runs"

    pcap_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        comment="PCAP file id this run belongs to",
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
        comment="Total pipeline duration in milliseconds",
    )
    stages_log: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="JSON list of StageRecord dicts",
    )

    __table_args__ = (
        Index("idx_pipeline_pcap_created", "pcap_id", "created_at"),
        Index("idx_pipeline_status", "status"),
    )

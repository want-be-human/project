"""
Alert ORM Model and AlertFlow association table.
Follows 附录F Section 3 & 4 - alerts and alert_flows tables.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, Text, ForeignKey, Index, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BaseModel


# Many-to-many association table (附录F Section 4)
alert_flows = Table(
    "alert_flows",
    Base.metadata,
    Column("alert_id", String(36), ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True),
    Column("flow_id", String(36), ForeignKey("flows.id", ondelete="CASCADE"), primary_key=True),
    Column("role", String(20), nullable=True),  # top, related (internal)
    Index("idx_alert_flows_flow", "flow_id"),
)


class Alert(BaseModel):
    """
    Security alert generated from anomaly detection.
    
    Maps to DOC C C1.3 Alert schema.
    """

    __tablename__ = "alerts"

    # Core fields
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )  # low, medium, high, critical

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="new",
    )  # new, triaged, investigating, resolved, false_positive

    type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="anomaly",
    )  # anomaly, scan, dos, bruteforce, exfil, unknown

    # Time window (拆分存储)
    time_window_start: Mapped[datetime] = mapped_column(nullable=False)
    time_window_end: Mapped[datetime] = mapped_column(nullable=False)

    # Primary entities (拆分存储便于索引)
    primary_src_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    primary_dst_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    primary_proto: Mapped[str] = mapped_column(String(10), nullable=False)
    primary_dst_port: Mapped[int] = mapped_column(Integer, nullable=False)

    # JSON blocks - stored as TEXT for SQLite compatibility
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    aggregation: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    agent: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    twin: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Relationships
    flows = relationship(
        "Flow",
        secondary=alert_flows,
        backref="alerts",
    )

    # Indexes (附录F 3.2)
    __table_args__ = (
        Index("idx_alert_status_created", "status", "created_at"),
        Index("idx_alert_sev_created", "severity", "created_at"),
        Index("idx_alert_src_created", "primary_src_ip", "created_at"),
        Index("idx_alert_window", "time_window_start", "time_window_end"),
    )

    def __repr__(self) -> str:
        return f"<Alert(id={self.id}, severity={self.severity}, type={self.type})>"

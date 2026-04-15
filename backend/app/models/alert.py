"""告警 ORM 模型与 AlertFlow 关联表（附录F 第 3、4 节）。"""

from datetime import datetime

from sqlalchemy import Column, ForeignKey, Index, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BaseModel


alert_flows = Table(
    "alert_flows",
    Base.metadata,
    Column("alert_id", String(36), ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True),
    Column("flow_id", String(36), ForeignKey("flows.id", ondelete="CASCADE"), primary_key=True),
    Column("role", String(20), nullable=True),  # top, related (internal)
    Index("idx_alert_flows_flow", "flow_id"),
)


class Alert(BaseModel):
    """由异常检测生成的安全告警（DOC C C1.3 Alert schema）。"""

    __tablename__ = "alerts"

    severity: Mapped[str] = mapped_column(String(20), nullable=False)  
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="new",
    )  
    type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="anomaly",
    ) 

    time_window_start: Mapped[datetime] = mapped_column(nullable=False)
    time_window_end: Mapped[datetime] = mapped_column(nullable=False)

    primary_src_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    primary_dst_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    primary_proto: Mapped[str] = mapped_column(String(10), nullable=False)
    primary_dst_port: Mapped[int] = mapped_column(Integer, nullable=False)

    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    aggregation: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    agent: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    twin: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    flows = relationship("Flow", secondary=alert_flows, backref="alerts")

    __table_args__ = (
        Index("idx_alert_status_created", "status", "created_at"),
        Index("idx_alert_sev_created", "severity", "created_at"),
        Index("idx_alert_src_created", "primary_src_ip", "created_at"),
        Index("idx_alert_window", "time_window_start", "time_window_end"),
    )

    def __repr__(self) -> str:
        return f"<Alert(id={self.id}, severity={self.severity}, type={self.type})>"

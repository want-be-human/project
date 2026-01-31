"""
FlowRecord ORM Model.
Follows 附录F Section 2 - flows table.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, Float, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Flow(BaseModel):
    """
    Flow record representing aggregated network traffic.
    
    Maps to DOC C C1.2 FlowRecord schema.
    """

    __tablename__ = "flows"

    # Foreign key to pcap_files
    pcap_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pcap_files.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Time range
    ts_start: Mapped[datetime] = mapped_column(nullable=False)
    ts_end: Mapped[datetime] = mapped_column(nullable=False)

    # 5-tuple
    src_ip: Mapped[str] = mapped_column(String(45), nullable=False)  # IPv6 max length
    src_port: Mapped[int] = mapped_column(Integer, nullable=False)
    dst_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    dst_port: Mapped[int] = mapped_column(Integer, nullable=False)
    proto: Mapped[str] = mapped_column(String(10), nullable=False)  # TCP, UDP, ICMP, OTHER

    # Packet and byte counts
    packets_fwd: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    packets_bwd: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bytes_fwd: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bytes_bwd: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Features JSON - stored as TEXT for SQLite compatibility
    features: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # Anomaly detection
    anomaly_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    label: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Relationships
    pcap = relationship("PcapFile", backref="flows")

    # Indexes (附录F 2.2)
    __table_args__ = (
        Index("idx_flow_pcap_ts", "pcap_id", "ts_start"),
        Index("idx_flow_pcap_src", "pcap_id", "src_ip"),
        Index("idx_flow_pcap_dst", "pcap_id", "dst_ip"),
        Index("idx_flow_pcap_proto_port", "pcap_id", "proto", "dst_port"),
        Index("idx_flow_score", "anomaly_score"),
    )

    def __repr__(self) -> str:
        return f"<Flow(id={self.id}, {self.src_ip}:{self.src_port} -> {self.dst_ip}:{self.dst_port})>"

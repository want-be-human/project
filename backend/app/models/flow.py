"""
FlowRecord ORM 模型。
遵循附录F第 2 节（flows 表）。
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, BigInteger, Float, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Flow(BaseModel):
    """
    表示聚合网络流量的流记录。

    对应 DOC C C1.2 FlowRecord schema。
    """

    __tablename__ = "flows"

    # 指向 pcap_files 的外键
    pcap_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pcap_files.id", ondelete="CASCADE"),
        nullable=False,
    )

    # 时间范围
    ts_start: Mapped[datetime] = mapped_column(nullable=False)
    ts_end: Mapped[datetime] = mapped_column(nullable=False)

    # 五元组
    src_ip: Mapped[str] = mapped_column(String(45), nullable=False)  # IPv6 max length
    src_port: Mapped[int] = mapped_column(Integer, nullable=False)
    dst_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    dst_port: Mapped[int] = mapped_column(Integer, nullable=False)
    proto: Mapped[str] = mapped_column(String(10), nullable=False)  # TCP, UDP, ICMP, OTHER

    # 报文与字节计数（BigInteger: NFStream 超时制聚合可产生超过 2GB 的大流）
    packets_fwd: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    packets_bwd: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    bytes_fwd: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    bytes_bwd: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    # 特征 JSON：为兼容 SQLite，使用 TEXT 存储
    features: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # 异常检测字段
    anomaly_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    label: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # 关联关系
    pcap = relationship("PcapFile", backref="flows")

    # 索引（附录F 2.2）
    __table_args__ = (
        Index("idx_flow_pcap_ts", "pcap_id", "ts_start"),
        Index("idx_flow_pcap_src", "pcap_id", "src_ip"),
        Index("idx_flow_pcap_dst", "pcap_id", "dst_ip"),
        Index("idx_flow_pcap_proto_port", "pcap_id", "proto", "dst_port"),
        Index("idx_flow_score", "anomaly_score"),
    )

    def __repr__(self) -> str:
        return f"<Flow(id={self.id}, {self.src_ip}:{self.src_port} -> {self.dst_ip}:{self.dst_port})>"

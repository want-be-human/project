"""
PcapFile ORM Model.
Follows 附录F Section 1 - pcap_files table.
"""

from typing import Optional
from sqlalchemy import String, BigInteger, Integer, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class PcapFile(BaseModel):
    """
    PCAP file record.
    
    Maps to DOC C C1.1 PcapFile schema.
    """

    __tablename__ = "pcap_files"

    # DOC C required fields
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="uploaded",
        # Values: uploaded, processing, done, failed
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0-100
    flow_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    alert_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Internal fields (not exposed in DOC C)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[Optional[str]] = mapped_column(String(72), nullable=True)  # "sha256:..." format
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Optional metadata

    def __repr__(self) -> str:
        return f"<PcapFile(id={self.id}, filename={self.filename}, status={self.status})>"

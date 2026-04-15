"""PcapFile ORM 模型（附录F 第 1 节）。"""

from typing import Optional

from sqlalchemy import JSON, BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class PcapFile(BaseModel):
    """PCAP 文件记录（DOC C C1.1 PcapFile schema）。"""

    __tablename__ = "pcap_files"

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="uploaded",
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0-100
    flow_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    alert_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 内部字段（不在 DOC C 中对外暴露）
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[Optional[str]] = mapped_column(String(72), nullable=True)  # "sha256:..." 格式
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<PcapFile(id={self.id}, filename={self.filename}, status={self.status})>"

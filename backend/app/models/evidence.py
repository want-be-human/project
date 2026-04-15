"""EvidenceChain ORM 模型（附录F 第 9 节，可选缓存）。"""

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class EvidenceChain(BaseModel):
    """告警证据链缓存（DOC C C3.1 EvidenceChain schema）。"""

    __tablename__ = "evidence_chains"

    alert_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False,
    )
    payload: Mapped[str] = mapped_column(Text, nullable=False)

    alert = relationship("Alert", backref="evidence_chains")

    __table_args__ = (
        Index("idx_evidence_alert_created", "alert_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<EvidenceChain(id={self.id}, alert_id={self.alert_id})>"

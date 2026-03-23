"""
EvidenceChain ORM Model.
Follows 附录F Section 9 - evidence_chains table (optional cache).
"""

from sqlalchemy import String, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class EvidenceChain(BaseModel):
    """
    Evidence chain cache for alert.
    
    Maps to DOC C C3.1 EvidenceChain schema.
    Can be computed on-the-fly, but caching improves performance.
    """

    __tablename__ = "evidence_chains"

    # 指向 alerts 的外键
    alert_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False,
    )

    # 完整 EvidenceChain JSON 载荷
    payload: Mapped[str] = mapped_column(Text, nullable=False)

    # 关联关系
    alert = relationship("Alert", backref="evidence_chains")

    # 索引（附录F 9.1）
    __table_args__ = (
        Index("idx_evidence_alert_created", "alert_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<EvidenceChain(id={self.id}, alert_id={self.alert_id})>"

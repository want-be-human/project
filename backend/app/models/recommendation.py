"""Recommendation ORM 模型（附录F 第 6 节）。"""

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Recommendation(BaseModel):
    """智能体建议结果（DOC C C1.5 Recommendation schema）。"""

    __tablename__ = "recommendations"

    alert_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False,
    )
    payload: Mapped[str] = mapped_column(Text, nullable=False)

    alert = relationship("Alert", backref="recommendations")

    __table_args__ = (
        Index("idx_rec_alert_created", "alert_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Recommendation(id={self.id}, alert_id={self.alert_id})>"

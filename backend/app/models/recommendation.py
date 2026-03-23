"""
Recommendation ORM 模型。
遵循附录F第 6 节（recommendations 表）。
"""

from sqlalchemy import String, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Recommendation(BaseModel):
    """
    智能体建议结果。

    对应 DOC C C1.5 Recommendation schema。
    """

    __tablename__ = "recommendations"

    # 指向 alerts 的外键
    alert_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False,
    )

    # 完整 Recommendation JSON 载荷
    payload: Mapped[str] = mapped_column(Text, nullable=False)

    # 关联关系
    alert = relationship("Alert", backref="recommendations")

    # 索引（附录F 6.2）
    __table_args__ = (
        Index("idx_rec_alert_created", "alert_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Recommendation(id={self.id}, alert_id={self.alert_id})>"

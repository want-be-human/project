"""Investigation ORM 模型（附录F 第 5 节）。"""

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Investigation(BaseModel):
    """智能体调查结果（DOC C C1.4 Investigation schema）。"""

    __tablename__ = "investigations"

    alert_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False,
    )
    payload: Mapped[str] = mapped_column(Text, nullable=False)

    alert = relationship("Alert", backref="investigations")

    __table_args__ = (
        Index("idx_inv_alert_created", "alert_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Investigation(id={self.id}, alert_id={self.alert_id})>"

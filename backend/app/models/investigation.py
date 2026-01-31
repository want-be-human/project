"""
Investigation ORM Model.
Follows 附录F Section 5 - investigations table.
"""

from sqlalchemy import String, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Investigation(BaseModel):
    """
    Agent investigation result.
    
    Maps to DOC C C1.4 Investigation schema.
    """

    __tablename__ = "investigations"

    # Foreign key to alerts
    alert_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Full Investigation JSON payload
    payload: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationship
    alert = relationship("Alert", backref="investigations")

    # Index (附录F 5.2)
    __table_args__ = (
        Index("idx_inv_alert_created", "alert_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Investigation(id={self.id}, alert_id={self.alert_id})>"

"""
Twin Models: ActionPlan and DryRun.
Follows 附录F Section 7 & 8 - twin_plans and dry_runs tables.
"""

from sqlalchemy import String, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class TwinPlan(BaseModel):
    """
    Action plan for twin dry-run simulation.
    
    Maps to DOC C C2.1 ActionPlan schema.
    """

    __tablename__ = "twin_plans"

    # Foreign key to alerts
    alert_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Source: agent or manual
    source: Mapped[str] = mapped_column(String(20), nullable=False)

    # Actions JSON array
    actions: Mapped[str] = mapped_column(Text, nullable=False)

    # Notes
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Relationship
    alert = relationship("Alert", backref="twin_plans")

    # Index (附录F 7.2)
    __table_args__ = (
        Index("idx_plan_alert_created", "alert_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<TwinPlan(id={self.id}, alert_id={self.alert_id}, source={self.source})>"


class DryRun(BaseModel):
    """
    Dry-run simulation result.
    
    Maps to DOC C C2.2 DryRunResult schema.
    """

    __tablename__ = "dry_runs"

    # Foreign keys
    alert_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("twin_plans.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Full DryRunResult JSON payload
    payload: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    alert = relationship("Alert", backref="dry_runs")
    plan = relationship("TwinPlan", backref="dry_runs")

    # Indexes (附录F 8.2)
    __table_args__ = (
        Index("idx_dry_alert_created", "alert_id", "created_at"),
        Index("idx_dry_plan_created", "plan_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<DryRun(id={self.id}, plan_id={self.plan_id})>"

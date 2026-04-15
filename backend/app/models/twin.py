"""孪生模型：TwinPlan 与 DryRun（附录F 第 7、8 节）。"""

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class TwinPlan(BaseModel):
    """用于孪生 dry-run 仿真的动作方案（DOC C C2.1 ActionPlan schema）。"""

    __tablename__ = "twin_plans"

    alert_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # agent | manual
    actions: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    alert = relationship("Alert", backref="twin_plans")

    __table_args__ = (
        Index("idx_plan_alert_created", "alert_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<TwinPlan(id={self.id}, alert_id={self.alert_id}, source={self.source})>"


class DryRun(BaseModel):
    """dry-run 仿真结果（DOC C C2.2 DryRunResult schema）。"""

    __tablename__ = "dry_runs"

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
    payload: Mapped[str] = mapped_column(Text, nullable=False)

    alert = relationship("Alert", backref="dry_runs")
    plan = relationship("TwinPlan", backref="dry_runs")

    __table_args__ = (
        Index("idx_dry_alert_created", "alert_id", "created_at"),
        Index("idx_dry_plan_created", "plan_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<DryRun(id={self.id}, plan_id={self.plan_id})>"

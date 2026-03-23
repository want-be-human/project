"""
孪生模型：ActionPlan 与 DryRun。
遵循附录F第 7、8 节（twin_plans 与 dry_runs 表）。
"""

from sqlalchemy import String, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class TwinPlan(BaseModel):
    """
    用于孪生 dry-run 仿真的动作方案。

    对应 DOC C C2.1 ActionPlan schema。
    """

    __tablename__ = "twin_plans"

    # 指向 alerts 的外键
    alert_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False,
    )

    # 来源：agent 或 manual
    source: Mapped[str] = mapped_column(String(20), nullable=False)

    # 动作 JSON 数组
    actions: Mapped[str] = mapped_column(Text, nullable=False)

    # 备注
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # 关联关系
    alert = relationship("Alert", backref="twin_plans")

    # 索引（附录F 7.2）
    __table_args__ = (
        Index("idx_plan_alert_created", "alert_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<TwinPlan(id={self.id}, alert_id={self.alert_id}, source={self.source})>"


class DryRun(BaseModel):
    """
    dry-run 仿真结果。

    对应 DOC C C2.2 DryRunResult schema。
    """

    __tablename__ = "dry_runs"

    # 外键
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

    # 完整 DryRunResult JSON 载荷
    payload: Mapped[str] = mapped_column(Text, nullable=False)

    # 关联关系
    alert = relationship("Alert", backref="dry_runs")
    plan = relationship("TwinPlan", backref="dry_runs")

    # 索引（附录F 8.2）
    __table_args__ = (
        Index("idx_dry_alert_created", "alert_id", "created_at"),
        Index("idx_dry_plan_created", "plan_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<DryRun(id={self.id}, plan_id={self.plan_id})>"

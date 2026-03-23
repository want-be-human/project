"""
工作流执行轨迹的 ORM 模型。
在不影响既有表结构的前提下存储编排元数据。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class WorkflowExecution(BaseModel):
    """记录每次工作流引擎调用及其阶段执行结果。"""

    __tablename__ = "workflow_executions"

    alert_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False,
    )
    workflow_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="triage | investigate | recommend | full_pipeline",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
        comment="pending | running | completed | failed",
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    stages_log: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="StageExecutionLog 字典的 JSON 列表",
    )

    __table_args__ = (
        Index("idx_wf_alert_created", "alert_id", "created_at"),
        Index("idx_wf_status_created", "status", "created_at"),
    )

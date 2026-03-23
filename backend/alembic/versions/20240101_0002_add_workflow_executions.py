"""新增 workflow_executions 表

Revision ID: 0002
Revises: 0001
Create Date: 2024-01-01 00:01:00.000000

用于保存智能体工作流引擎执行轨迹的新表。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workflow_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.String(10), nullable=False, server_default="1.1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "alert_id",
            sa.String(36),
            sa.ForeignKey("alerts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("workflow_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("stages_log", sa.Text(), nullable=True),
    )
    op.create_index("idx_wf_alert_created", "workflow_executions", ["alert_id", "created_at"])
    op.create_index("idx_wf_status_created", "workflow_executions", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_wf_status_created", table_name="workflow_executions")
    op.drop_index("idx_wf_alert_created", table_name="workflow_executions")
    op.drop_table("workflow_executions")

"""add pipeline_runs table

Revision ID: 0003
Revises: 0002
Create Date: 2024-01-01 00:02:00.000000

New table for pipeline observability — stage-level tracking.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.String(10), nullable=False, server_default="1.1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("pcap_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("total_latency_ms", sa.Float(), nullable=True),
        sa.Column("stages_log", sa.Text(), nullable=True),
    )
    op.create_index("idx_pipeline_pcap_created", "pipeline_runs", ["pcap_id", "created_at"])
    op.create_index("idx_pipeline_status", "pipeline_runs", ["status"])


def downgrade() -> None:
    op.drop_index("idx_pipeline_status", table_name="pipeline_runs")
    op.drop_index("idx_pipeline_pcap_created", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")

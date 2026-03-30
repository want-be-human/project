"""add scenario run stage fields

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-30 00:00:00.000000

为 scenario_runs 表新增三列：
- stages_log: 阶段时间线 JSON（list[ScenarioStageRecord]）
- validation_latency_ms: 校验耗时（阶段 1-8 之和，毫秒）
- pipeline_latency_ms: Pipeline 耗时（来自 PipelineRunModel，毫秒）

旧记录三列均为 NULL，前端 timeline 字段返回 null，向后兼容。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scenario_runs",
        sa.Column("stages_log", sa.Text(), nullable=True),
    )
    op.add_column(
        "scenario_runs",
        sa.Column("validation_latency_ms", sa.Float(), nullable=True),
    )
    op.add_column(
        "scenario_runs",
        sa.Column("pipeline_latency_ms", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scenario_runs", "pipeline_latency_ms")
    op.drop_column("scenario_runs", "validation_latency_ms")
    op.drop_column("scenario_runs", "stages_log")

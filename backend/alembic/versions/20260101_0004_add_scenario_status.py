"""
新增 scenario status 字段，用于标识场景的状态
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scenarios",
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
    )
    op.create_index("idx_scenario_status", "scenarios", ["status"])


def downgrade() -> None:
    op.drop_index("idx_scenario_status", table_name="scenarios")
    op.drop_column("scenarios", "status")

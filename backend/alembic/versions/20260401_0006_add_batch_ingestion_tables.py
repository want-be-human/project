"""
新增批量接入三张表：
- batches: 批次管理单元
- batch_files: 批次文件处理单元
- jobs: 作业执行单元
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "batches",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("version", sa.String(10), nullable=False, server_default="1.1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="created"),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("total_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_flow_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_alert_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_latency_ms", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
    )
    op.create_index("idx_batch_status", "batches", ["status"])
    op.create_index("idx_batch_created", "batches", ["created_at"])

    op.create_table(
        "batch_files",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("version", sa.String(10), nullable=False, server_default="1.1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("batches.id"), nullable=False),
        sa.Column("pcap_id", sa.String(36), sa.ForeignKey("pcap_files.id"), nullable=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(72), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="accepted"),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("flow_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("alert_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("meta", sa.JSON(), nullable=True),
    )
    op.create_index("idx_bf_batch_id", "batch_files", ["batch_id"])
    op.create_index("idx_bf_status", "batch_files", ["status"])
    op.create_index("idx_bf_sha256", "batch_files", ["sha256"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("version", sa.String(10), nullable=False, server_default="1.1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("batches.id"), nullable=False),
        sa.Column("batch_file_id", sa.String(36), sa.ForeignKey("batch_files.id"), nullable=False),
        sa.Column("pcap_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("current_stage", sa.String(30), nullable=True),
        sa.Column("stages_log", sa.JSON(), nullable=True),
        sa.Column("idempotency_key", sa.String(100), nullable=False, unique=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_job_batch_id", "jobs", ["batch_id"])
    op.create_index("idx_job_status", "jobs", ["status"])
    op.create_index("idx_job_bf", "jobs", ["batch_file_id"])


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("batch_files")
    op.drop_table("batches")

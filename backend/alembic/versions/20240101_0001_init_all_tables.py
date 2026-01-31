"""init all tables per appendix_f

Revision ID: 0001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

Tables created per 附录F specification:
- pcap_files (F1)
- flows (F2)
- alerts (F3)
- alert_flows (F3 association)
- investigations (F4)
- recommendations (F5)
- twin_plans (F6)
- dry_runs (F7)
- scenarios (F8)
- scenario_runs (F9)
- evidence_chains (F10)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # F1: pcap_files
    op.create_table(
        "pcap_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.String(10), nullable=False, default="1.1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("stored_path", sa.String(512), nullable=False),
        sa.Column("file_hash", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, default="pending"),
        sa.Column("progress", sa.Integer(), nullable=False, default=0),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),  # JSON as TEXT for SQLite
    )
    op.create_index("idx_pcap_status", "pcap_files", ["status"])
    op.create_index("idx_pcap_created_at", "pcap_files", ["created_at"])

    # F2: flows
    op.create_table(
        "flows",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.String(10), nullable=False, default="1.1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("pcap_id", sa.String(36), sa.ForeignKey("pcap_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ts_start", sa.DateTime(), nullable=False),
        sa.Column("ts_end", sa.DateTime(), nullable=False),
        sa.Column("src_ip", sa.String(45), nullable=False),
        sa.Column("dst_ip", sa.String(45), nullable=False),
        sa.Column("proto", sa.String(10), nullable=False),
        sa.Column("src_port", sa.Integer(), nullable=True),
        sa.Column("dst_port", sa.Integer(), nullable=True),
        sa.Column("pkt_count", sa.Integer(), nullable=False, default=0),
        sa.Column("byte_count", sa.BigInteger(), nullable=False, default=0),
        sa.Column("features", sa.Text(), nullable=True),  # JSON as TEXT
        sa.Column("anomaly_score", sa.Float(), nullable=True),
        sa.Column("label", sa.String(50), nullable=True),
    )
    op.create_index("idx_flow_pcap_ts", "flows", ["pcap_id", "ts_start"])
    op.create_index("idx_flow_pcap_src", "flows", ["pcap_id", "src_ip"])
    op.create_index("idx_flow_pcap_dst", "flows", ["pcap_id", "dst_ip"])
    op.create_index("idx_flow_pcap_proto_port", "flows", ["pcap_id", "proto", "dst_port"])
    op.create_index("idx_flow_score", "flows", ["anomaly_score"])

    # F3: alerts
    op.create_table(
        "alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.String(10), nullable=False, default="1.1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("time_window_start", sa.DateTime(), nullable=False),
        sa.Column("time_window_end", sa.DateTime(), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, default="medium"),
        sa.Column("status", sa.String(20), nullable=False, default="open"),
        sa.Column("primary_src_ip", sa.String(45), nullable=False),
        sa.Column("primary_dst_ip", sa.String(45), nullable=False),
        sa.Column("primary_proto", sa.String(10), nullable=False),
        sa.Column("primary_dst_port", sa.Integer(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=False),  # JSON as TEXT
        sa.Column("aggregation", sa.Text(), nullable=False),  # JSON as TEXT
        sa.Column("agent", sa.Text(), nullable=False, default="{}"),  # JSON as TEXT
        sa.Column("twin", sa.Text(), nullable=False, default="{}"),  # JSON as TEXT
    )
    op.create_index("idx_alert_status_sev", "alerts", ["status", "severity"])
    op.create_index("idx_alert_time_window", "alerts", ["time_window_start", "time_window_end"])
    op.create_index("idx_alert_src_ip", "alerts", ["primary_src_ip"])
    op.create_index("idx_alert_type", "alerts", ["type"])

    # F3: alert_flows (association table)
    op.create_table(
        "alert_flows",
        sa.Column("alert_id", sa.String(36), sa.ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("flow_id", sa.String(36), sa.ForeignKey("flows.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("idx_af_alert", "alert_flows", ["alert_id"])
    op.create_index("idx_af_flow", "alert_flows", ["flow_id"])

    # F4: investigations
    op.create_table(
        "investigations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.String(10), nullable=False, default="1.1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("alert_id", sa.String(36), sa.ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),  # JSON as TEXT
    )
    op.create_index("idx_inv_alert_created", "investigations", ["alert_id", "created_at"])

    # F5: recommendations
    op.create_table(
        "recommendations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.String(10), nullable=False, default="1.1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("alert_id", sa.String(36), sa.ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),  # JSON as TEXT
    )
    op.create_index("idx_rec_alert_created", "recommendations", ["alert_id", "created_at"])

    # F6: twin_plans
    op.create_table(
        "twin_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.String(10), nullable=False, default="1.1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("alert_id", sa.String(36), sa.ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),  # 'agent' or 'manual'
        sa.Column("actions", sa.Text(), nullable=False),  # JSON as TEXT
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("idx_plan_alert_created", "twin_plans", ["alert_id", "created_at"])

    # F7: dry_runs
    op.create_table(
        "dry_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.String(10), nullable=False, default="1.1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("alert_id", sa.String(36), sa.ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_id", sa.String(36), sa.ForeignKey("twin_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),  # JSON as TEXT
    )
    op.create_index("idx_dryrun_plan_created", "dry_runs", ["plan_id", "created_at"])

    # F8: scenarios
    op.create_table(
        "scenarios",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.String(10), nullable=False, default="1.1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("pcap_id", sa.String(36), sa.ForeignKey("pcap_files.id", ondelete="SET NULL"), nullable=True),
        sa.Column("payload", sa.Text(), nullable=False),  # JSON as TEXT (expectations, tags)
    )
    op.create_index("idx_scenario_name", "scenarios", ["name"], unique=True)

    # F9: scenario_runs
    op.create_table(
        "scenario_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.String(10), nullable=False, default="1.1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("scenario_id", sa.String(36), sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),  # 'pass' or 'fail'
        sa.Column("payload", sa.Text(), nullable=False),  # JSON as TEXT
    )
    op.create_index("idx_scenrun_scenario_created", "scenario_runs", ["scenario_id", "created_at"])

    # F10: evidence_chains
    op.create_table(
        "evidence_chains",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.String(10), nullable=False, default="1.1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("alert_id", sa.String(36), sa.ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),  # JSON as TEXT
    )
    op.create_index("idx_evidence_alert", "evidence_chains", ["alert_id"])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table("evidence_chains")
    op.drop_table("scenario_runs")
    op.drop_table("scenarios")
    op.drop_table("dry_runs")
    op.drop_table("twin_plans")
    op.drop_table("recommendations")
    op.drop_table("investigations")
    op.drop_table("alert_flows")
    op.drop_table("alerts")
    op.drop_table("flows")
    op.drop_table("pcap_files")

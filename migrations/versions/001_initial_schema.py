"""Initial schema — all tables

Revision ID: 001
Revises:
Create Date: 2026-05-08 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── audit_logs ────────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("module", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("input_data", postgresql.JSONB(), nullable=False),
        sa.Column("output_data", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_module", "audit_logs", ["module"])
    op.create_index("ix_audit_logs_task_id", "audit_logs", ["task_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # ── approvals ─────────────────────────────────────────────────────────────
    op.create_table(
        "approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("module", sa.String(64), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "approved", "rejected", "expired", "auto_executed",
                name="approvalstatus",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("resolved_by", sa.String(64), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("whatsapp_message_id", sa.String(128), nullable=True),
        sa.Column("dry_run_result", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approvals_status", "approvals", ["status"])

    # ── kpi_snapshots ─────────────────────────────────────────────────────────
    op.create_table(
        "kpi_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("period", sa.String(16), nullable=False),
        sa.Column("orders_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("orders_target", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revenue_eur", sa.Float(), nullable=False, server_default="0"),
        sa.Column("aov_eur", sa.Float(), nullable=False, server_default="0"),
        sa.Column("ad_spend_eur", sa.Float(), nullable=False, server_default="0"),
        sa.Column("ad_roas", sa.Float(), nullable=False, server_default="0"),
        sa.Column("ad_cpa_eur", sa.Float(), nullable=False, server_default="0"),
        sa.Column("ad_ctr_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("ad_impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("organic_sessions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("organic_clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_position", sa.Float(), nullable=False, server_default="0"),
        sa.Column("sessions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conversion_rate_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cart_abandonment_rate_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("email_revenue_eur", sa.Float(), nullable=False, server_default="0"),
        sa.Column("email_open_rate_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("raw", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kpi_snapshots_snapshot_date", "kpi_snapshots", ["snapshot_date"])
    op.create_index("ix_kpi_snapshots_captured_at", "kpi_snapshots", ["captured_at"])

    # ── tasks ─────────────────────────────────────────────────────────────────
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("trigger", sa.String(64), nullable=False),
        sa.Column(
            "status",
            sa.Enum("queued", "running", "completed", "failed", "cancelled", name="taskstatus"),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("progress_pct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actions_executed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actions_approved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actions_pending", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_name", "tasks", ["name"])
    op.create_index("ix_tasks_status", "tasks", ["status"])

    # ── rollback_records ──────────────────────────────────────────────────────
    op.create_table(
        "rollback_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("action_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("module", sa.String(64), nullable=False),
        sa.Column("forward_payload", postgresql.JSONB(), nullable=False),
        sa.Column("inverse_action", sa.String(128), nullable=False),
        sa.Column("inverse_payload", postgresql.JSONB(), nullable=False),
        sa.Column("rolled_back", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("rolled_back_by", sa.String(64), nullable=True),
        sa.Column("rollback_error", sa.String(512), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rollback_records_action_id", "rollback_records", ["action_id"])
    op.create_index("ix_rollback_records_rolled_back", "rollback_records", ["rolled_back"])
    op.create_index("ix_rollback_records_created_at", "rollback_records", ["created_at"])


def downgrade() -> None:
    op.drop_table("rollback_records")
    op.drop_table("tasks")
    op.drop_table("kpi_snapshots")
    op.drop_table("approvals")
    op.drop_table("audit_logs")
    op.execute("DROP TYPE IF EXISTS approvalstatus")
    op.execute("DROP TYPE IF EXISTS taskstatus")

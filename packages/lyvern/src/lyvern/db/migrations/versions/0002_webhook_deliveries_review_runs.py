"""webhook deliveries and review runs

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("delivery_id", sa.String(80), nullable=False),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64)),
        sa.Column("installation_id", sa.BigInteger()),
        sa.Column("repo_full_name", sa.String(200)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("detail", sa.Text()),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_webhook_deliveries"),
        sa.UniqueConstraint("delivery_id", name="uq_webhook_deliveries_delivery_id"),
    )
    op.create_table(
        "review_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repo_full_name", sa.String(200), nullable=False),
        sa.Column("pr_number", sa.Integer(), nullable=False),
        sa.Column("head_sha", sa.String(64), nullable=False),
        sa.Column("installation_id", sa.BigInteger(), nullable=False),
        sa.Column("trigger_delivery_id", sa.String(80), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("event_posted", sa.String(24)),
        sa.Column("github_review_id", sa.BigInteger()),
        sa.Column("findings_count", sa.Integer()),
        sa.Column("inline_posted", sa.Integer()),
        sa.Column("error", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_review_runs"),
        sa.UniqueConstraint(
            "repo_full_name", "pr_number", "head_sha", name="uq_review_runs_pr_head"
        ),
    )


def downgrade() -> None:
    op.drop_table("review_runs")
    op.drop_table("webhook_deliveries")

"""add rate limit events

Revision ID: 0011_rate_limit_events
Revises: 0010_nft_withdrawals
Create Date: 2026-06-09 00:00:11.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0011_rate_limit_events"
down_revision = "0010_nft_withdrawals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope_key", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rate_limit_events_action_scope_created_at",
        "rate_limit_events",
        ["action", "scope_key", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_rate_limit_events_action_scope_created_at",
        table_name="rate_limit_events",
    )
    op.drop_table("rate_limit_events")

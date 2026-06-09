"""add withdrawal unmined since marker

Revision ID: 0012_withdrawal_unmined_since
Revises: 0011_rate_limit_events
Create Date: 2026-06-09 00:00:12.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "0012_withdrawal_unmined_since"
down_revision = "0011_rate_limit_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "withdrawal_requests",
        sa.Column("unmined_since_block", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "nft_withdrawal_requests",
        sa.Column("unmined_since_block", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("nft_withdrawal_requests", "unmined_since_block")
    op.drop_column("withdrawal_requests", "unmined_since_block")

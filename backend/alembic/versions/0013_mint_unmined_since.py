"""add mint unmined since marker

Revision ID: 0013_mint_unmined_since
Revises: 0012_withdrawal_unmined_since
Create Date: 2026-06-09 00:00:13.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "0013_mint_unmined_since"
down_revision = "0012_withdrawal_unmined_since"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "nft_mint_requests",
        sa.Column("unmined_since_block", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("nft_mint_requests", "unmined_since_block")

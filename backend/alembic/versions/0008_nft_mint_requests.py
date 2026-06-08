"""add nft mint requests

Revision ID: 0008_nft_mint_requests
Revises: 0007_nft_holdings
Create Date: 2026-06-08 00:00:07.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0008_nft_mint_requests"
down_revision = "0007_nft_holdings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "nft_mint_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("contract", sa.Text(), nullable=False),
        sa.Column("to_address", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("nonce", sa.BigInteger(), nullable=True),
        sa.Column("signed_tx", sa.Text(), nullable=True),
        sa.Column("tx_hash", sa.Text(), nullable=True),
        sa.Column("token_id", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('requested','signing','broadcast','confirmed','failed')",
            name="ck_nft_mint_requests_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("nft_mint_requests")

"""add nft deposits

Revision ID: 0009_nft_deposits
Revises: 0008_nft_mint_requests
Create Date: 2026-06-08 00:00:08.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0009_nft_deposits"
down_revision = "0008_nft_mint_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "nft_deposits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("contract", sa.Text(), nullable=False),
        sa.Column("token_id", sa.Text(), nullable=False),
        sa.Column("from_address", sa.Text(), nullable=False),
        sa.Column("to_address", sa.Text(), nullable=False),
        sa.Column("tx_hash", sa.Text(), nullable=False),
        sa.Column("log_index", sa.Integer(), nullable=True),
        sa.Column("block_number", sa.BigInteger(), nullable=False),
        sa.Column("block_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("credit_revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('seen','confirmed','credited','orphaned')",
            name="ck_nft_deposits_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "chain_id",
            "tx_hash",
            "log_index",
            name="uq_nft_deposits_chain_tx_log",
        ),
    )


def downgrade() -> None:
    op.drop_table("nft_deposits")

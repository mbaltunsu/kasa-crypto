"""add nft withdrawals

Revision ID: 0010_nft_withdrawals
Revises: 0009_nft_deposits
Create Date: 2026-06-09 00:00:10.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0010_nft_withdrawals"
down_revision = "0009_nft_deposits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "nft_withdrawal_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nft_holding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("contract", sa.Text(), nullable=False),
        sa.Column("token_id", sa.Text(), nullable=False),
        sa.Column("to_address", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("nonce", sa.BigInteger(), nullable=True),
        sa.Column("signed_tx", sa.Text(), nullable=True),
        sa.Column("tx_hash", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('requested','approved','signing','broadcast','confirmed','failed')",
            name="ck_nft_withdrawal_requests_status",
        ),
        sa.ForeignKeyConstraint(["nft_holding_id"], ["nft_holdings.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_nft_withdrawal_requests_idempotency_key",
        ),
    )


def downgrade() -> None:
    op.drop_table("nft_withdrawal_requests")

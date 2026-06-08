"""add nft holdings and transfer audit

Revision ID: 0007_nft_holdings
Revises: 0006_withdrawal_signed_tx
Create Date: 2026-06-08 00:00:06.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007_nft_holdings"
down_revision = "0006_withdrawal_signed_tx"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "nft_holdings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("contract", sa.Text(), nullable=False),
        sa.Column("token_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "acquired_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('held','withdrawing','withdrawn')",
            name="ck_nft_holdings_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_nft_holdings_chain_contract_token",
        "nft_holdings",
        [sa.text("chain_id"), sa.text("lower(contract)"), sa.text("token_id")],
        unique=True,
    )

    op.create_table(
        "nft_transfers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nft_holding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('pending','submitted','confirmed','failed')",
            name="ck_nft_transfers_status",
        ),
        sa.ForeignKeyConstraint(["nft_holding_id"], ["nft_holdings.id"]),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["sender_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_nft_transfers_idempotency_key"),
    )


def downgrade() -> None:
    op.drop_table("nft_transfers")
    op.drop_index("uq_nft_holdings_chain_contract_token", table_name="nft_holdings")
    op.drop_table("nft_holdings")

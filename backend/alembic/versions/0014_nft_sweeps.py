"""add nft sweeps

Revision ID: 0014_nft_sweeps
Revises: 0013_mint_unmined_since
Create Date: 2026-06-09 00:00:14.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0014_nft_sweeps"
down_revision = "0013_mint_unmined_since"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "nft_sweeps",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("contract", sa.Text(), nullable=False),
        sa.Column("token_id", sa.Text(), nullable=False),
        sa.Column("deposit_address", sa.Text(), nullable=False),
        sa.Column("hd_index", sa.Integer(), nullable=False),
        sa.Column("nft_deposit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("gas_fund_tx_hash", sa.Text(), nullable=True),
        sa.Column("gas_fund_nonce", sa.BigInteger(), nullable=True),
        sa.Column("sweep_signed_tx", sa.Text(), nullable=True),
        sa.Column("sweep_tx_hash", sa.Text(), nullable=True),
        sa.Column("sweep_nonce", sa.BigInteger(), nullable=True),
        sa.Column("unmined_since_block", sa.BigInteger(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('pending','funding','funded','sweeping','swept','failed')",
            name="ck_nft_sweeps_status",
        ),
        sa.ForeignKeyConstraint(["nft_deposit_id"], ["nft_deposits.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_nft_sweeps_chain_contract_token",
        "nft_sweeps",
        [sa.text("chain_id"), sa.text("lower(contract)"), sa.text("token_id")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_nft_sweeps_chain_contract_token", table_name="nft_sweeps")
    op.drop_table("nft_sweeps")

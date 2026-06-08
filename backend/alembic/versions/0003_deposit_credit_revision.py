"""add onchain_deposits.credit_revision

Revision ID: 0003_deposit_credit_revision
Revises: 0002_seed_registry_assets
Create Date: 2026-06-08 00:00:02.000000

Per-deposit reorg revision so the credit/reversal ledger idempotency keys stay unique across
re-mines even when the block re-converges to the same hash (finding #6).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0003_deposit_credit_revision"
down_revision = "0002_seed_registry_assets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "onchain_deposits",
        sa.Column("credit_revision", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("onchain_deposits", "credit_revision")

"""add withdrawal_requests.signed_tx

Revision ID: 0006_withdrawal_signed_tx
Revises: 0005_deposit_addr_unique
Create Date: 2026-06-08 00:00:05.000000

Durable signed raw tx for the withdrawer outbox: the payout is signed and persisted (with its nonce)
before broadcast, so a crash between broadcast and commit re-broadcasts the identical tx rather than
re-signing at a fresh nonce — no double-pay, no stranded nonce (finding #3).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0006_withdrawal_signed_tx"
down_revision = "0005_deposit_addr_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("withdrawal_requests", sa.Column("signed_tx", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("withdrawal_requests", "signed_tx")

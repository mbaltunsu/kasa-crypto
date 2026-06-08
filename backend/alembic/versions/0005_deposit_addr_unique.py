"""case-insensitive unique index for deposit addresses

Revision ID: 0005_deposit_addr_unique
Revises: 0004_ledger_system_unique
Create Date: 2026-06-08 00:00:04.000000

Deposit-address ownership is looked up case-insensitively (`address.lower()` in the watcher), but the
uniqueness was a case-sensitive constraint — two rows differing only in case could shadow each other
in the owner map and credit the wrong user. Replace it with a `lower(address)` functional unique
index so casing can never fork ownership (finding #8/#16). Addresses are already stored EIP-55.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0005_deposit_addr_unique"
down_revision = "0004_ledger_system_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_deposit_addresses_address", "deposit_addresses", type_="unique")
    op.create_index(
        "uq_deposit_addresses_address_lower",
        "deposit_addresses",
        [sa.text("lower(address)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_deposit_addresses_address_lower", table_name="deposit_addresses")
    op.create_unique_constraint("uq_deposit_addresses_address", "deposit_addresses", ["address"])

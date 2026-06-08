"""partial unique index for system ledger accounts

Revision ID: 0004_ledger_system_unique
Revises: 0003_deposit_credit_revision
Create Date: 2026-06-08 00:00:03.000000

The composite unique constraint on (owner_type, user_id, asset_id, name) does not prevent duplicate
`system` accounts because their user_id is NULL and Postgres treats NULLs as distinct. Add a partial
unique index over the non-null discriminators so concurrent get-or-create cannot fork a system
account (finding #10).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0004_ledger_system_unique"
down_revision = "0003_deposit_credit_revision"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_ledger_accounts_system_owner_asset_name",
        "ledger_accounts",
        [sa.text("owner_type"), sa.text("asset_id"), sa.text("name")],
        unique=True,
        postgresql_where=sa.text("user_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_ledger_accounts_system_owner_asset_name", table_name="ledger_accounts")

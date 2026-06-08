"""seed registry assets

Revision ID: 0002_seed_registry_assets
Revises: 0001_initial_schema
Create Date: 2026-06-08 00:00:01.000000
"""

from collections.abc import Sequence
from pathlib import Path
import sys
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert

revision = "0002_seed_registry_assets"
down_revision = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROOT = Path(__file__).resolve().parents[2]
SHARED_PYTHON = ROOT.parent / "packages" / "shared" / "python"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SHARED_PYTHON))

ASSET_NAMESPACE = uuid.UUID("c38a8b6f-7c61-4b83-9353-265a9e859c2f")


def _asset_id(chain_id: int, asset_type: str, symbol: str, address: str | None) -> uuid.UUID:
    key = f"{chain_id}:{asset_type}:{symbol.upper()}:{(address or '').lower()}"
    return uuid.uuid5(ASSET_NAMESPACE, key)


def upgrade() -> None:
    from kasa_shared.registry import load_registry

    assets = sa.table(
        "assets",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("chain_id", sa.Integer()),
        sa.column("symbol", sa.Text()),
        sa.column("type", sa.Text()),
        sa.column("contract_address", sa.Text()),
        sa.column("decimals", sa.Integer()),
    )
    rows = []
    for chain in load_registry().chains.values():
        for asset in chain.assets:
            address = getattr(asset, "address", None)
            rows.append(
                {
                    "id": _asset_id(chain.chain_id, asset.type.value, asset.symbol, address),
                    "chain_id": chain.chain_id,
                    "symbol": asset.symbol.upper(),
                    "type": asset.type.value,
                    "contract_address": address,
                    "decimals": asset.decimals,
                },
            )

    if not rows:
        return

    statement = insert(assets).values(rows)
    op.execute(
        statement.on_conflict_do_update(
            constraint="uq_assets_chain_symbol",
            set_={
                "type": statement.excluded.type,
                "contract_address": statement.excluded.contract_address,
                "decimals": statement.excluded.decimals,
            },
        ),
    )


def downgrade() -> None:
    from kasa_shared.registry import load_registry

    bind = op.get_bind()
    keys = [(chain.chain_id, asset.symbol.upper()) for chain in load_registry().chains.values() for asset in chain.assets]
    for chain_id, symbol in keys:
        bind.execute(
            sa.text("DELETE FROM assets WHERE chain_id = :chain_id AND symbol = :symbol"),
            {"chain_id": chain_id, "symbol": symbol},
        )

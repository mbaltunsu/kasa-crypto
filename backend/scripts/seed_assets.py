from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.dialects.postgresql import insert

ROOT = Path(__file__).resolve().parents[1]
SHARED_PYTHON = ROOT.parent / "packages" / "shared" / "python"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SHARED_PYTHON))

from app.core.config import get_settings  # noqa: E402
from app.models.tables import Asset  # noqa: E402
from kasa_shared.registry import load_registry  # noqa: E402

ASSET_NAMESPACE = uuid.UUID("c38a8b6f-7c61-4b83-9353-265a9e859c2f")


def _async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _asset_id(chain_id: int, asset_type: str, symbol: str, address: str | None) -> uuid.UUID:
    key = f"{chain_id}:{asset_type}:{symbol.upper()}:{(address or '').lower()}"
    return uuid.uuid5(ASSET_NAMESPACE, key)


def _asset_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
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
    return rows


async def seed_assets(database_url: str) -> None:
    engine = create_async_engine(_async_url(database_url))
    rows = _asset_rows()
    if not rows:
        await engine.dispose()
        return

    statement = insert(Asset).values(rows)
    upsert = statement.on_conflict_do_update(
        constraint="uq_assets_chain_symbol",
        set_={
            "type": statement.excluded.type,
            "contract_address": statement.excluded.contract_address,
            "decimals": statement.excluded.decimals,
        },
    )
    async with engine.begin() as connection:
        await connection.execute(upsert)
    await engine.dispose()


async def main() -> None:
    await seed_assets(get_settings().database_url)


if __name__ == "__main__":
    asyncio.run(main())

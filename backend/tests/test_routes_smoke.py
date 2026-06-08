import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("sqlalchemy")
pytest.importorskip("eth_utils")

from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.mark.asyncio
async def test_health_and_registry_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv(
        "MASTER_MNEMONIC",
        "test test test test test test test test test test test junk",
    )
    monkeypatch.setenv("RPC_ETHEREUM_SEPOLIA", "http://localhost")
    monkeypatch.setenv("RPC_AVALANCHE_FUJI", "http://localhost")

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/api/v1/health")
        chains = await client.get("/api/v1/chains")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert chains.status_code == 200
    assert {chain["chain_id"] for chain in chains.json()} == {11_155_111, 43_113}

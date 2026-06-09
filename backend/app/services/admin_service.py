from __future__ import annotations

import hashlib
from http import HTTPStatus
from typing import TYPE_CHECKING

from eth_utils import to_checksum_address
from kasa_shared.consts import ZERO_ADDRESS
from kasa_shared.registry import nfts_of_chain
from sqlalchemy import case, func, select

from app.chain.client import ChainRpcError
from app.core.enums import ErrorCode, NftHoldingStatus, NftMintStatus
from app.models.tables import (
    Asset,
    DepositAddress,
    LedgerAccount,
    LedgerEntry,
    NftHolding,
    NftMintRequest,
    User,
    WithdrawalRequest,
)
from app.schemas.admin import ReserveAssetResponse, ReservesResponse
from app.schemas.nft import AdminMintNftResponse
from app.services import ledger
from app.services.errors import raise_api_error
from app.services.rate_limit import enforce_rate_limit

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.chain.types import BalanceClient


def _checksum_contract_address(address: str) -> str:
    try:
        return str(to_checksum_address(address))
    except ValueError as exc:
        raise_api_error(HTTPStatus.UNPROCESSABLE_ENTITY, ErrorCode.VALIDATION_ERROR, str(exc))


async def _liabilities(session: AsyncSession, asset: Asset) -> int:
    # Sum each user wallet's balance, then keep only the POSITIVE ones (finding #17). Clamping the
    # grand total instead would let a negative/anomalous account net against others and understate
    # the true liability — negative balances are operational exceptions, not a discount on reserves.
    per_account = (
        select(func.coalesce(func.sum(LedgerEntry.amount), 0).label("balance"))
        .join(LedgerAccount, LedgerAccount.id == LedgerEntry.account_id)
        .where(
            LedgerAccount.owner_type == "user",
            LedgerAccount.name == ledger.USER_WALLET_ACCOUNT,
            LedgerEntry.asset_id == asset.id,
        )
        .group_by(LedgerEntry.account_id)
        .subquery()
    )
    positive = case((per_account.c.balance > 0, per_account.c.balance), else_=0)
    statement = select(func.coalesce(func.sum(positive), 0))
    return int((await session.execute(statement)).scalar_one())


def _sum_onchain(
    client: BalanceClient,
    asset: Asset,
    addresses: list[str],
    *,
    fallback: int,
) -> int:
    try:
        if asset.type == "native":
            return sum(client.native_balance(address) for address in addresses)
        if asset.contract_address is not None:
            return sum(
                client.erc20_balance(token_address=asset.contract_address, address=address)
                for address in addresses
            )
    except ChainRpcError:
        return fallback
    return fallback


async def reserves(
    session: AsyncSession,
    *,
    hot_wallet_address: str | None = None,
    balance_factory: Callable[[int], BalanceClient] | None = None,
) -> ReservesResponse:
    """Proof-of-reserves: ledger liabilities (Σ user wallets) vs custodied on-chain balances.

    When `balance_factory` is provided the reserve figure sums the live native/ERC-20 balances of
    every deposit address plus the hot wallet; otherwise it falls back to liabilities (delta 0).
    """
    assets = (
        await session.execute(select(Asset).order_by(Asset.chain_id, Asset.symbol))
    ).scalars().all()
    deposit_addresses = list((await session.execute(select(DepositAddress.address))).scalars())
    custody_addresses = list(deposit_addresses)
    if hot_wallet_address is not None:
        custody_addresses.append(hot_wallet_address)

    clients: dict[int, BalanceClient] = {}
    rows: list[ReserveAssetResponse] = []
    for asset in assets:
        liabilities = await _liabilities(session, asset)
        chain_reserves = liabilities
        if balance_factory is not None and asset.type in {"native", "erc20"}:
            client = clients.get(asset.chain_id)
            if client is None:
                client = balance_factory(asset.chain_id)
                clients[asset.chain_id] = client
            chain_reserves = _sum_onchain(client, asset, custody_addresses, fallback=liabilities)
        rows.append(
            ReserveAssetResponse(
                asset_id=asset.id,
                liabilities=liabilities,
                reserves=chain_reserves,
                delta=chain_reserves - liabilities,
            ),
        )
    return ReservesResponse(assets=rows)


async def list_withdrawals(
    session: AsyncSession,
    *,
    offset: int,
    limit: int,
) -> list[WithdrawalRequest]:
    return list(
        (
            await session.execute(
                select(WithdrawalRequest)
                .order_by(WithdrawalRequest.created_at.desc(), WithdrawalRequest.id.desc())
                .offset(offset)
                .limit(limit),
            )
        ).scalars(),
    )


async def mint_nft_stub(
    session: AsyncSession,
    *,
    user_email: str,
    chain_id: int,
) -> AdminMintNftResponse:
    user = (
        await session.execute(select(User).where(User.email == user_email.strip().lower()))
    ).scalar_one_or_none()
    if user is None:
        raise_api_error(HTTPStatus.NOT_FOUND, ErrorCode.NOT_FOUND, "User not found")

    asset = (
        await session.execute(
            select(Asset)
            .where(Asset.chain_id == chain_id, Asset.type == "erc721")
            .order_by(Asset.symbol),
        )
    ).scalars().first()
    if asset is None or asset.contract_address is None:
        raise_api_error(HTTPStatus.NOT_FOUND, ErrorCode.UNKNOWN_ASSET, "Unknown NFT asset")
    contract = _checksum_contract_address(asset.contract_address)

    existing_count = (
        await session.execute(
            select(func.count(NftHolding.id)).where(
                NftHolding.chain_id == chain_id,
                func.lower(NftHolding.contract) == contract.lower(),
            ),
        )
    ).scalar_one()
    # Deterministic placeholder receipt for offline demos.
    digest = hashlib.sha256(f"{user.id}:{chain_id}:{existing_count}".encode()).hexdigest()
    token_id = str(int(digest[:16], 16))
    session.add(
        NftHolding(
            user_id=user.id,
            chain_id=chain_id,
            contract=contract,
            token_id=token_id,
            status=NftHoldingStatus.HELD.value,
        ),
    )
    await session.flush()
    return AdminMintNftResponse(
        status=NftMintStatus.CONFIRMED,
        tx_hash="0x" + digest,
        token_id=token_id,
    )


def _registry_nft_contract(chain_id: int) -> str:
    try:
        asset = next(
            (nft for nft in nfts_of_chain(chain_id) if nft.symbol.upper() == "KASA"),
            None,
        )
    except KeyError:
        asset = None
    if asset is None or asset.address.lower() == ZERO_ADDRESS.lower():
        raise_api_error(HTTPStatus.NOT_FOUND, ErrorCode.UNKNOWN_ASSET, "Unknown NFT asset")
    return _checksum_contract_address(asset.address)


async def mint_nft(  # noqa: PLR0913
    session: AsyncSession,
    *,
    admin_user_id: UUID,
    user_email: str,
    chain_id: int,
    onchain: bool,
    hot_wallet_address: str | None = None,
) -> AdminMintNftResponse:
    if not onchain:
        return await mint_nft_stub(session, user_email=user_email, chain_id=chain_id)

    await enforce_rate_limit(session, action="nft_mint", user_id=admin_user_id)

    user = (
        await session.execute(select(User).where(User.email == user_email.strip().lower()))
    ).scalar_one_or_none()
    if user is None:
        raise_api_error(HTTPStatus.NOT_FOUND, ErrorCode.NOT_FOUND, "User not found")
    if hot_wallet_address is None:
        raise_api_error(
            HTTPStatus.INTERNAL_SERVER_ERROR, ErrorCode.VALIDATION_ERROR, "Hot wallet unavailable",
        )

    # Custodial model: mint to the custodian hot wallet so it holds the token on-chain and can later
    # sign safeTransferFrom on withdrawal; the user owns the off-chain holding the worker creates on
    # confirmation. (Internal transfers only move that off-chain claim.)
    request = NftMintRequest(
        user_id=user.id,
        chain_id=chain_id,
        contract=_registry_nft_contract(chain_id),
        to_address=to_checksum_address(hot_wallet_address),
        status=NftMintStatus.REQUESTED.value,
    )
    session.add(request)
    await session.flush()
    return AdminMintNftResponse(request_id=request.id, status=NftMintStatus.REQUESTED)

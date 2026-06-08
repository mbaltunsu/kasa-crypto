from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from http import HTTPStatus
from typing import TYPE_CHECKING
from uuid import UUID

from kasa_shared.registry import explorer_tx_url, list_chains
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain.types import NATIVE_LOG_INDEX
from app.core.enums import DepositStatus, ErrorCode, LedgerEntryType
from app.models.tables import Asset, DepositAddress, OnchainDeposit, User
from app.schemas.faucet import FaucetResponse
from app.schemas.wallet import BalanceResponse, DepositAddressResponse
from app.services import ledger
from app.services.errors import raise_api_error, raise_not_found
from app.services.idempotency import scoped_idempotency_key

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.chain.types import SenderClient

# ref_type tags distinguishing instant simulation faucet credits from real on-chain sends.
_FAUCET_SIM_REF = "faucet_sim"
_FAUCET_REAL_REF = "faucet_real"
_FAUCET_DISPATCHED_ACCOUNT = "faucet_dispatched"
# Length of a 0x-prefixed 32-byte transaction hash ("0x" + 64 hex chars).
_TX_HASH_HEX_LEN = 66


async def get_asset(session: AsyncSession, asset_id: UUID) -> Asset:
    asset = (await session.execute(select(Asset).where(Asset.id == asset_id))).scalar_one_or_none()
    if asset is None:
        raise_api_error(HTTPStatus.NOT_FOUND, ErrorCode.UNKNOWN_ASSET, "Unknown asset")
    return asset


async def list_deposit_addresses(
    session: AsyncSession,
    *,
    user: User,
) -> list[DepositAddressResponse]:
    address = (
        await session.execute(select(DepositAddress).where(DepositAddress.user_id == user.id))
    ).scalar_one_or_none()
    if address is None:
        raise_not_found("Deposit address not found")
    return [
        DepositAddressResponse(chain_id=chain.chain_id, address=address.address)
        for chain in list_chains()
    ]


async def list_balances(session: AsyncSession, *, user: User) -> list[BalanceResponse]:
    assets = (await session.execute(select(Asset).order_by(Asset.chain_id, Asset.symbol))).scalars().all()
    responses: list[BalanceResponse] = []
    for asset in assets:
        available, pending = await ledger.balance(session, user=user, asset=asset)
        responses.append(
            BalanceResponse(
                asset_id=asset.id,
                chain_id=asset.chain_id,
                symbol=asset.symbol,
                available=max(0, available),
                pending=max(0, pending),
            ),
        )
    return responses


def _placeholder_tx_hash(idempotency_key: str) -> str:
    return "0x" + hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()


async def request_faucet(
    session: AsyncSession,
    *,
    user: User,
    asset_id: UUID,
    amount: int,
    idempotency_key: str,
    faucet_private_key: str | None = None,
    sender_factory: Callable[[int], SenderClient] | None = None,
) -> FaucetResponse:
    """Top up a user's deposit address with testnet funds.

    Real mode (a `FAUCET_PRIVATE_KEY` + sender are supplied): broadcast a funded testnet
    transaction to the user's deposit address and let the watcher record + credit it like any
    other deposit. Simulation mode (offline / no key): immediately credit the ledger so the demo
    is usable without a live chain.
    """
    if amount <= 0:
        raise_api_error(
            HTTPStatus.UNPROCESSABLE_ENTITY, ErrorCode.VALIDATION_ERROR, "Amount must be positive",
        )
    asset = await get_asset(session, asset_id)

    scoped_key = scoped_idempotency_key(domain="faucet", user_id=user.id, client_key=idempotency_key)
    existing_tx = await ledger.find_transaction_by_idempotency_key(session, scoped_key)
    if existing_tx is not None:
        is_sim = existing_tx.ref_type == _FAUCET_SIM_REF
        status = DepositStatus.CREDITED if is_sim else DepositStatus.SEEN
        return FaucetResponse(tx_hash=existing_tx.ref_id, status=status)

    address = (
        await session.execute(select(DepositAddress).where(DepositAddress.user_id == user.id))
    ).scalar_one_or_none()
    if address is None:
        raise_not_found("Deposit address not found")

    if faucet_private_key and sender_factory is not None:
        return await _faucet_send(
            session,
            asset=asset,
            to_address=address.address,
            amount=amount,
            idempotency_key=scoped_key,
            faucet_private_key=faucet_private_key,
            sender=sender_factory(asset.chain_id),
        )
    return await _faucet_simulate(
        session,
        user=user,
        asset=asset,
        to_address=address.address,
        amount=amount,
        idempotency_key=scoped_key,
    )


async def _faucet_send(
    session: AsyncSession,
    *,
    asset: Asset,
    to_address: str,
    amount: int,
    idempotency_key: str,
    faucet_private_key: str,
    sender: SenderClient,
) -> FaucetResponse:
    from eth_account import Account

    faucet_address = Account.from_key(faucet_private_key).address
    nonce = sender.pending_nonce(faucet_address)
    gas_price = sender.suggested_gas_price()
    if asset.type == "native":
        tx_hash = sender.send_native(
            private_key=faucet_private_key,
            to_address=to_address,
            value=amount,
            nonce=nonce,
            gas_price=gas_price,
        )
    elif asset.type == "erc20" and asset.contract_address is not None:
        tx_hash = sender.send_erc20(
            private_key=faucet_private_key,
            token_address=asset.contract_address,
            to_address=to_address,
            value=amount,
            nonce=nonce,
            gas_price=gas_price,
        )
    else:
        raise_api_error(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            ErrorCode.VALIDATION_ERROR,
            "Asset is not faucet-claimable",
        )
    # Record a marker keyed by the idempotency key (the unique idempotency_key column makes a
    # retry with the same key short-circuit at request_faucet rather than re-broadcasting). The
    # watcher still records + credits the actual deposit independently from the on-chain tx.
    source = await ledger.get_or_create_account(
        session, asset=asset, name=ledger.FAUCET_SOURCE_ACCOUNT, owner_type="system",
    )
    dispatched = await ledger.get_or_create_account(
        session, asset=asset, name=_FAUCET_DISPATCHED_ACCOUNT, owner_type="system",
    )
    await ledger.post(
        session,
        transaction_type=LedgerEntryType.DEPOSIT,
        idempotency_key=idempotency_key,
        ref_type=_FAUCET_REAL_REF,
        ref_id=tx_hash,
        legs=[
            ledger.LedgerLeg(source, asset, -amount),
            ledger.LedgerLeg(dispatched, asset, amount),
        ],
    )
    return FaucetResponse(tx_hash=tx_hash, status=DepositStatus.SEEN)


async def _faucet_simulate(
    session: AsyncSession,
    *,
    user: User,
    asset: Asset,
    to_address: str,
    amount: int,
    idempotency_key: str,
) -> FaucetResponse:
    tx_hash = _placeholder_tx_hash(idempotency_key)
    session.add(
        OnchainDeposit(
            chain_id=asset.chain_id,
            tx_hash=tx_hash,
            log_index=NATIVE_LOG_INDEX,
            block_number=0,
            block_hash="0x" + ("0" * 64),
            to_address=to_address,
            asset_id=asset.id,
            amount=amount,
            status=DepositStatus.CREDITED.value,
            user_id=user.id,
        ),
    )
    await session.flush()

    source = await ledger.get_or_create_account(
        session,
        asset=asset,
        name=ledger.FAUCET_SOURCE_ACCOUNT,
        owner_type="system",
    )
    wallet = await ledger.get_user_wallet_account(session, user=user, asset=asset)
    await ledger.post(
        session,
        transaction_type=LedgerEntryType.DEPOSIT,
        idempotency_key=idempotency_key,
        ref_type=_FAUCET_SIM_REF,
        ref_id=tx_hash,
        legs=[
            ledger.LedgerLeg(source, asset, -amount),
            ledger.LedgerLeg(wallet, asset, amount),
        ],
    )
    return FaucetResponse(tx_hash=tx_hash, status=DepositStatus.CREDITED)


def deposit_confirmations(deposit: OnchainDeposit, last_scanned_block: int | None) -> int:
    """Confirmation depth (head - block), matching the watcher's `head - block >= N` credit gate.

    0 for simulated/unscanned deposits. Uses the same 0-indexed depth the watcher credits on, so the
    displayed count reaching DEPOSIT_CONFIRMATIONS lines up exactly with the deposit being credited.
    """
    if deposit.block_number <= 0 or last_scanned_block is None:
        return 0
    return max(0, last_scanned_block - deposit.block_number)


def deposit_explorer_url(deposit: OnchainDeposit) -> str:
    if deposit.tx_hash.startswith("0x") and len(deposit.tx_hash) == _TX_HASH_HEX_LEN:
        return explorer_tx_url(deposit.chain_id, deposit.tx_hash)
    return ""


def now_utc() -> datetime:
    return datetime.now(UTC)

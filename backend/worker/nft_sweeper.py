"""ERC-721 deposit sweeper.

Credited NFT deposits represent tokens physically owned by a user's derived deposit address. This
worker funds that address for gas, then has the deposit address sign safeTransferFrom into the
custody hot wallet so the normal NFT withdrawal outbox can later spend from custody.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import Select, func, select

from app.chain.client import ChainRpcError
from app.chain.types import BalanceClient, SenderClient
from app.core.config import get_settings
from app.core.enums import NftDepositStatus, NftSweepStatus
from app.core.hd_wallet import derive_account
from app.models.tables import DepositAddress, NftDeposit, NftSweep
from worker._nonce import nonce_row, supports_skip_locked

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class SweepClient(SenderClient, BalanceClient, Protocol):
    pass


logger = logging.getLogger("kasa.worker.nft_sweeper")

GAS_BUDGET_WEI = 2_000_000_000_000_000
_DEFAULT_BATCH = 20


def _hd_index(derivation_path: str) -> int:
    return int(derivation_path.rsplit("/", 1)[1])


async def discover_sweeps(session: AsyncSession, client: SweepClient) -> int:
    sweep_exists = (
        select(NftSweep.id)
        .where(
            NftSweep.chain_id == NftDeposit.chain_id,
            func.lower(NftSweep.contract) == func.lower(NftDeposit.contract),
            NftSweep.token_id == NftDeposit.token_id,
        )
        .exists()
    )
    rows = (
        await session.execute(
            select(NftDeposit, DepositAddress)
            .join(
                DepositAddress,
                func.lower(DepositAddress.address) == func.lower(NftDeposit.to_address),
            )
            .where(
                NftDeposit.chain_id == client.chain_id,
                NftDeposit.status == NftDepositStatus.CREDITED.value,
                ~sweep_exists,
            )
            .order_by(NftDeposit.created_at, NftDeposit.id),
        )
    ).all()

    discovered = 0
    for deposit, address in rows:
        session.add(
            NftSweep(
                chain_id=deposit.chain_id,
                contract=deposit.contract,
                token_id=deposit.token_id,
                deposit_address=deposit.to_address,
                hd_index=_hd_index(address.derivation_path),
                nft_deposit_id=deposit.id,
                status=NftSweepStatus.PENDING.value,
            ),
        )
        discovered += 1
    await session.flush()
    return discovered


async def _claim_sweeps(
    session: AsyncSession,
    chain_id: int,
    statuses: list[str],
    batch: int,
) -> list[NftSweep]:
    statement: Select[tuple[NftSweep]] = (
        select(NftSweep)
        .where(NftSweep.chain_id == chain_id, NftSweep.status.in_(statuses))
        .order_by(NftSweep.created_at, NftSweep.id)
        .limit(batch)
    )
    if supports_skip_locked(session):
        statement = statement.with_for_update(skip_locked=True)
    return list((await session.execute(statement)).scalars())


async def fund_pending(
    session: AsyncSession,
    client: SweepClient,
    *,
    hot_wallet_key: str,
    hot_wallet_address: str,
    batch: int = _DEFAULT_BATCH,
) -> int:
    sweeps = await _claim_sweeps(
        session,
        client.chain_id,
        [NftSweepStatus.PENDING.value, NftSweepStatus.FUNDING.value],
        batch,
    )
    if not sweeps:
        return 0
    progressed = 0
    hot_nonce = None
    gas_price = client.suggested_gas_price()
    for sweep in sweeps:
        if client.native_balance(sweep.deposit_address) >= GAS_BUDGET_WEI:
            sweep.status = NftSweepStatus.FUNDED.value
            progressed += 1
            continue
        if sweep.status != NftSweepStatus.PENDING.value:
            continue
        if hot_nonce is None:
            hot_nonce = await nonce_row(session, client, hot_wallet_address)
        nonce = hot_nonce.next_nonce
        try:
            sweep.attempts += 1
            tx = client.sign_native(
                private_key=hot_wallet_key,
                to_address=sweep.deposit_address,
                value=GAS_BUDGET_WEI,
                nonce=nonce,
                gas_price=gas_price,
            )
            sweep.gas_fund_tx_hash = tx.tx_hash
            sweep.gas_fund_nonce = nonce
            hot_nonce.next_nonce = nonce + 1
            sweep.status = NftSweepStatus.FUNDING.value
            client.broadcast_raw(tx.raw)
        except Exception:
            logger.exception(
                "nft sweep %s gas funding failed on chain %s",
                sweep.id,
                client.chain_id,
            )
            continue
        progressed += 1
    await session.flush()
    return progressed


async def sweep_funded(
    session: AsyncSession,
    client: SweepClient,
    *,
    hot_wallet_address: str,
    batch: int = _DEFAULT_BATCH,
) -> int:
    sweeps = await _claim_sweeps(
        session,
        client.chain_id,
        [NftSweepStatus.FUNDED.value],
        batch,
    )
    if not sweeps:
        return 0
    settings = get_settings()
    gas_price = client.suggested_gas_price()
    broadcast = 0
    for sweep in sweeps:
        try:
            sweep.attempts += 1
            raw = sweep.sweep_signed_tx
            if raw is None:
                account = derive_account(
                    settings.master_mnemonic,
                    chain_id=client.chain_id,
                    hd_index=sweep.hd_index,
                )
                nonce = client.pending_nonce(sweep.deposit_address)
                tx = client.sign_erc721_transfer(
                    private_key=account.private_key,
                    contract_address=sweep.contract,
                    from_address=sweep.deposit_address,
                    to_address=hot_wallet_address,
                    token_id=sweep.token_id,
                    nonce=nonce,
                    gas_price=gas_price,
                )
                sweep.sweep_signed_tx = tx.raw
                sweep.sweep_tx_hash = tx.tx_hash
                sweep.sweep_nonce = nonce
                raw = tx.raw
            sweep.sweep_tx_hash = client.broadcast_raw(raw)
        except ChainRpcError:
            logger.warning("nft sweep %s broadcast failed; will retry next pass", sweep.id)
            continue
        except Exception:
            logger.exception(
                "nft sweep %s failed pre-broadcast on chain %s",
                sweep.id,
                client.chain_id,
            )
            continue
        sweep.status = NftSweepStatus.SWEEPING.value
        broadcast += 1
    await session.flush()
    return broadcast


async def confirm_sweeps(
    session: AsyncSession,
    client: SweepClient,
    *,
    confirmations: int,
    hot_wallet_address: str,
    batch: int = _DEFAULT_BATCH,
) -> int:
    head = client.block_number()
    sweeps = await _claim_sweeps(
        session,
        client.chain_id,
        [NftSweepStatus.SWEEPING.value],
        batch,
    )
    swept = 0
    for sweep in sweeps:
        if sweep.sweep_tx_hash is None:
            continue
        receipt = client.get_receipt(sweep.sweep_tx_hash)
        if receipt is None:
            _reconcile_unmined(client, sweep, head=head, confirmations=confirmations)
            continue
        sweep.unmined_since_block = None
        if head - receipt.block_number < confirmations:
            continue
        canonical = client.block_hash(receipt.block_number)
        if canonical is None or canonical != receipt.block_hash:
            continue
        if receipt.status == 0:
            sweep.status = NftSweepStatus.FAILED.value
            sweep.error = "sweep reverted"
            continue
        if not _owner_is_hot_wallet(client, sweep=sweep, hot_wallet_address=hot_wallet_address):
            continue
        sweep.status = NftSweepStatus.SWEPT.value
        swept += 1
    await session.flush()
    return swept


def _reconcile_unmined(
    client: SweepClient,
    sweep: NftSweep,
    *,
    head: int,
    confirmations: int,
) -> None:
    """Mark a receipt-absent sweep dropped only after nonce advancement persists."""
    if sweep.sweep_nonce is None:
        return
    if client.latest_nonce(sweep.deposit_address) <= sweep.sweep_nonce:
        sweep.unmined_since_block = None
        return
    if sweep.unmined_since_block is None:
        sweep.unmined_since_block = head
        return
    if head - sweep.unmined_since_block >= confirmations:
        sweep.status = NftSweepStatus.FAILED.value
        sweep.error = "sweep tx dropped (nonce superseded)"


def _owner_is_hot_wallet(
    client: SweepClient,
    *,
    sweep: NftSweep,
    hot_wallet_address: str,
) -> bool:
    owner_of = getattr(client, "erc721_owner_of", None)
    if owner_of is None:
        return True
    owner = owner_of(contract_address=sweep.contract, token_id=sweep.token_id)
    if owner is None:
        return False
    return bool(owner.lower() == hot_wallet_address.lower())

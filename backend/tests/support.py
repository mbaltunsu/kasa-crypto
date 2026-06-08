"""Shared test support: an in-memory fake chain client + DB seed helpers.

The fake structurally satisfies the WatcherClient / SenderClient / BalanceClient protocols, so the
worker logic can be exercised end-to-end against canned chain data with zero network access.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.chain.client import ChainRpcError, erc721_minted_token_id_from_receipt
from app.chain.types import Erc20Transfer, Erc721Transfer, NativeTransfer, SignedTx, TxReceipt
from app.core.enums import UserRole
from app.models.tables import Asset, DepositAddress, User


@dataclass(frozen=True)
class SentTx:
    kind: str  # "native" | "erc20" | "erc721_mint" | "erc721_transfer"
    to_address: str
    value: int
    nonce: int
    token_address: str | None
    tx_hash: str


@dataclass
class FakeChainClient:
    """Canned, deterministic stand-in for `ChainClient`. No network, no randomness."""

    chain_id: int
    head: int = 0
    block_hashes: dict[int, str] = field(default_factory=dict)
    erc20_transfers: list[Erc20Transfer] = field(default_factory=list)
    erc721_transfers: list[Erc721Transfer] = field(default_factory=list)
    native_transfers: list[NativeTransfer] = field(default_factory=list)
    internal_transfers: list[NativeTransfer] = field(default_factory=list)
    receipts: dict[str, TxReceipt] = field(default_factory=dict)
    nonces: dict[str, int] = field(default_factory=dict)
    latest_nonces: dict[str, int] = field(default_factory=dict)
    gas_price: int = 1_000_000_000
    native_balances: dict[str, int] = field(default_factory=dict)
    erc20_balances: dict[tuple[str, str], int] = field(default_factory=dict)
    send_error: str | None = None
    sent: list[SentTx] = field(default_factory=list)
    _signed: dict[str, SentTx] = field(default_factory=dict)

    # ── WatcherClient ──────────────────────────────────────────────────────────
    def block_number(self) -> int:
        return self.head

    def block_hash(self, block_number: int) -> str | None:
        return self.block_hashes.get(block_number)

    def fetch_erc20_transfers(
        self,
        *,
        token_addresses: list[str],
        to_addresses: list[str],
        from_block: int,
        to_block: int,
    ) -> list[Erc20Transfer]:
        tokens = {a.lower() for a in token_addresses}
        recipients = {a.lower() for a in to_addresses}
        return [
            transfer
            for transfer in self.erc20_transfers
            if transfer.token_address.lower() in tokens
            and transfer.to_address.lower() in recipients
            and from_block <= transfer.block_number <= to_block
        ]

    def fetch_native_transfers(
        self,
        *,
        to_addresses: list[str],
        from_block: int,
        to_block: int,
    ) -> list[NativeTransfer]:
        recipients = {a.lower() for a in to_addresses}
        return [
            transfer
            for transfer in self.native_transfers
            if transfer.to_address.lower() in recipients
            and from_block <= transfer.block_number <= to_block
        ]

    def fetch_erc721_transfers(
        self,
        *,
        contract_addresses: list[str],
        to_addresses: list[str],
        from_block: int,
        to_block: int,
    ) -> list[Erc721Transfer]:
        contracts = {a.lower() for a in contract_addresses}
        recipients = {a.lower() for a in to_addresses}
        return [
            transfer
            for transfer in self.erc721_transfers
            if transfer.contract_address.lower() in contracts
            and transfer.to_address.lower() in recipients
            and from_block <= transfer.block_number <= to_block
        ]

    def fetch_internal_transfers(
        self,
        *,
        to_addresses: list[str],
        from_block: int,
        to_block: int,
    ) -> list[NativeTransfer]:
        recipients = {a.lower() for a in to_addresses}
        return [
            transfer
            for transfer in self.internal_transfers
            if transfer.to_address.lower() in recipients
            and from_block <= transfer.block_number <= to_block
        ]

    # ── BalanceClient ──────────────────────────────────────────────────────────
    def native_balance(self, address: str) -> int:
        return self.native_balances.get(address.lower(), 0)

    def erc20_balance(self, *, token_address: str, address: str) -> int:
        return self.erc20_balances.get((token_address.lower(), address.lower()), 0)

    # ── SenderClient ───────────────────────────────────────────────────────────
    def pending_nonce(self, address: str) -> int:
        return self.nonces.get(address.lower(), 0)

    def latest_nonce(self, address: str) -> int:
        return self.latest_nonces.get(address.lower(), 0)

    def suggested_gas_price(self) -> int:
        return self.gas_price

    def sign_native(
        self,
        *,
        private_key: str,
        to_address: str,
        value: int,
        nonce: int,
        gas_price: int,
    ) -> SignedTx:
        return self._sign("native", to_address=to_address, value=value, nonce=nonce, token=None)

    def sign_erc20(
        self,
        *,
        private_key: str,
        token_address: str,
        to_address: str,
        value: int,
        nonce: int,
        gas_price: int,
    ) -> SignedTx:
        return self._sign("erc20", to_address=to_address, value=value, nonce=nonce, token=token_address)

    def sign_erc721_mint(
        self,
        *,
        private_key: str,
        contract_address: str,
        to_address: str,
        nonce: int,
        gas_price: int,
    ) -> SignedTx:
        _ = private_key, gas_price
        return self._sign(
            "erc721_mint", to_address=to_address, value=0, nonce=nonce, token=contract_address,
        )

    def sign_erc721_transfer(  # noqa: PLR0913
        self,
        *,
        private_key: str,
        contract_address: str,
        from_address: str,
        to_address: str,
        token_id: str,
        nonce: int,
        gas_price: int,
    ) -> SignedTx:
        _ = private_key, from_address, gas_price
        return self._sign(
            "erc721_transfer",
            to_address=to_address,
            value=int(token_id),
            nonce=nonce,
            token=contract_address,
        )

    def broadcast_raw(self, raw: str) -> str:
        if self.send_error is not None:
            raise ChainRpcError(self.send_error)
        sent = self._signed[raw]
        self.sent.append(sent)
        return sent.tx_hash

    def send_native(
        self,
        *,
        private_key: str,
        to_address: str,
        value: int,
        nonce: int,
        gas_price: int,
    ) -> str:
        return self.broadcast_raw(
            self.sign_native(
                private_key=private_key, to_address=to_address, value=value, nonce=nonce, gas_price=gas_price,
            ).raw,
        )

    def send_erc20(
        self,
        *,
        private_key: str,
        token_address: str,
        to_address: str,
        value: int,
        nonce: int,
        gas_price: int,
    ) -> str:
        return self.broadcast_raw(
            self.sign_erc20(
                private_key=private_key,
                token_address=token_address,
                to_address=to_address,
                value=value,
                nonce=nonce,
                gas_price=gas_price,
            ).raw,
        )

    def get_receipt(self, tx_hash: str) -> TxReceipt | None:
        return self.receipts.get(tx_hash)

    def erc721_minted_token_id(
        self,
        *,
        tx_hash: str,
        contract_address: str,
        to_address: str,
    ) -> str | None:
        receipt = self.get_receipt(tx_hash)
        if receipt is None:
            return None
        return erc721_minted_token_id_from_receipt(
            receipt, contract_address=contract_address, to_address=to_address,
        )

    def _sign(
        self,
        kind: str,
        *,
        to_address: str,
        value: int,
        nonce: int,
        token: str | None,
    ) -> SignedTx:
        # Deterministic raw payload so re-signing identical inputs yields the same tx (idempotent
        # re-broadcast), mirroring the real client. The raw string also carries the structured fields
        # so broadcast_raw can record a faithful SentTx.
        raw = f"0xsigned:{kind}:{to_address}:{value}:{nonce}:{token}"
        tx_hash = "0x" + hashlib.sha256(raw.encode()).hexdigest()
        self._signed[raw] = SentTx(
            kind=kind, to_address=to_address, value=value, nonce=nonce, token_address=token, tx_hash=tx_hash,
        )
        return SignedTx(raw=raw, tx_hash=tx_hash)


# ─────────────────────────── DB seed helpers ───────────────────────────


async def seed_asset(
    session: AsyncSession,
    *,
    chain_id: int,
    asset_type: str,
    symbol: str,
    decimals: int,
    contract_address: str | None = None,
) -> Asset:
    asset = Asset(
        id=uuid.uuid4(),
        chain_id=chain_id,
        symbol=symbol,
        type=asset_type,
        contract_address=contract_address,
        decimals=decimals,
    )
    session.add(asset)
    await session.flush()
    return asset


async def seed_user(
    session: AsyncSession,
    *,
    email: str,
    hd_index: int,
    role: str = UserRole.USER.value,
) -> User:
    user = User(email=email, password_hash="hash", role=role, hd_index=hd_index)
    session.add(user)
    await session.flush()
    return user


async def seed_deposit_address(
    session: AsyncSession,
    *,
    user: User,
    address: str,
) -> DepositAddress:
    deposit_address = DepositAddress(
        user_id=user.id,
        address=address,
        derivation_path=f"m/44'/60'/0'/0/{user.hd_index}",
    )
    session.add(deposit_address)
    await session.flush()
    return deposit_address

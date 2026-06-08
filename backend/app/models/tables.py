import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    Uuid,
    and_,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

AmountNumeric = Numeric(78, 0)
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
EmailType = CITEXT().with_variant(Text(), "sqlite")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role in ('user','admin')", name="ck_users_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(EmailType, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    hd_index: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    deposit_address: Mapped["DepositAddress | None"] = relationship(back_populates="user")
    ledger_accounts: Mapped[list["LedgerAccount"]] = relationship(back_populates="user")


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chain_id: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    contract_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    decimals: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("type in ('native','erc20','erc721')", name="ck_assets_type"),
        UniqueConstraint("chain_id", "symbol", name="uq_assets_chain_symbol"),
        Index("uq_assets_chain_symbol_upper", "chain_id", func.upper(symbol), unique=True),
        Index(
            "uq_assets_chain_contract_lower",
            "chain_id",
            func.lower(contract_address),
            unique=True,
            postgresql_where=and_(
                contract_address.is_not(None),
                func.lower(contract_address) != ZERO_ADDRESS,
            ),
        ),
    )

    ledger_accounts: Mapped[list["LedgerAccount"]] = relationship(back_populates="asset")


class DepositAddress(Base):
    __tablename__ = "deposit_addresses"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_deposit_addresses_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    derivation_path: Mapped[str] = mapped_column(Text, nullable=False)

    user: Mapped[User] = relationship(back_populates="deposit_address")


class LedgerAccount(Base):
    __tablename__ = "ledger_accounts"
    __table_args__ = (
        CheckConstraint("owner_type in ('user','system')", name="ck_ledger_accounts_owner_type"),
        UniqueConstraint(
            "owner_type",
            "user_id",
            "asset_id",
            "name",
            name="uq_ledger_accounts_owner_user_asset_name",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_type: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)

    user: Mapped[User | None] = relationship(back_populates="ledger_accounts")
    asset: Mapped[Asset] = relationship(back_populates="ledger_accounts")
    entries: Mapped[list["LedgerEntry"]] = relationship(back_populates="account")


class LedgerTransaction(Base):
    __tablename__ = "ledger_transactions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    ref_type: Mapped[str] = mapped_column(Text, nullable=False)
    ref_id: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    entries: Mapped[list["LedgerEntry"]] = relationship(back_populates="transaction")


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ledger_transactions.id"),
        nullable=False,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ledger_accounts.id"), nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"), nullable=False)
    amount: Mapped[int] = mapped_column(AmountNumeric, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    transaction: Mapped[LedgerTransaction] = relationship(back_populates="entries")
    account: Mapped[LedgerAccount] = relationship(back_populates="entries")


class OnchainDeposit(Base):
    __tablename__ = "onchain_deposits"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_onchain_deposits_amount_nonnegative"),
        CheckConstraint(
            "status in ('seen','confirmed','credited','orphaned')",
            name="ck_onchain_deposits_status",
        ),
        UniqueConstraint(
            "chain_id",
            "tx_hash",
            "log_index",
            name="uq_onchain_deposits_chain_tx_log",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chain_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tx_hash: Mapped[str] = mapped_column(Text, nullable=False)
    log_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    block_hash: Mapped[str] = mapped_column(Text, nullable=False)
    to_address: Mapped[str] = mapped_column(Text, nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"), nullable=False)
    amount: Mapped[int] = mapped_column(AmountNumeric, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class WithdrawalRequest(Base):
    __tablename__ = "withdrawal_requests"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_withdrawal_requests_amount_positive"),
        CheckConstraint(
            "status in ('requested','approved','signing','broadcast','confirmed','failed','rejected')",
            name="ck_withdrawal_requests_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"), nullable=False)
    chain_id: Mapped[int] = mapped_column(Integer, nullable=False)
    to_address: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[int] = mapped_column(AmountNumeric, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    tx_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    nonce: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ChainCursor(Base):
    __tablename__ = "chain_cursors"

    chain_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_scanned_block: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_finalized_block: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class HotWalletNonce(Base):
    __tablename__ = "hot_wallet_nonces"

    chain_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    next_nonce: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

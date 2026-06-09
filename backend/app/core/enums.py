from enum import StrEnum


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class AssetType(StrEnum):
    NATIVE = "native"
    ERC20 = "erc20"
    ERC721 = "erc721"


class DepositStatus(StrEnum):
    SEEN = "seen"
    CONFIRMED = "confirmed"
    CREDITED = "credited"
    ORPHANED = "orphaned"


class NftDepositStatus(StrEnum):
    SEEN = "seen"
    CONFIRMED = "confirmed"
    CREDITED = "credited"
    ORPHANED = "orphaned"


class WithdrawalStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    SIGNING = "signing"
    BROADCAST = "broadcast"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    REJECTED = "rejected"


class TransferStatus(StrEnum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class NftHoldingStatus(StrEnum):
    HELD = "held"
    WITHDRAWING = "withdrawing"
    WITHDRAWN = "withdrawn"


class NftMintStatus(StrEnum):
    REQUESTED = "requested"
    SIGNING = "signing"
    BROADCAST = "broadcast"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class NftWithdrawalStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    SIGNING = "signing"
    BROADCAST = "broadcast"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class NftSweepStatus(StrEnum):
    PENDING = "pending"
    FUNDING = "funding"
    FUNDED = "funded"
    SWEEPING = "sweeping"
    SWEPT = "swept"
    FAILED = "failed"


class GasStatus(StrEnum):
    OK = "ok"
    LOW = "low"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class LedgerEntryType(StrEnum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    FEE = "fee"
    ADJUSTMENT = "adjustment"
    REVERSAL = "reversal"


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "validation_error"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    UNKNOWN_ASSET = "unknown_asset"
    UNSUPPORTED_CHAIN = "unsupported_chain"
    WITHDRAWAL_REJECTED = "withdrawal_rejected"
    NOT_FOUND = "not_found"
    UNAUTHORIZED = "unauthorized"
    RATE_LIMITED = "rate_limited"
    INTERNAL_ERROR = "internal_error"

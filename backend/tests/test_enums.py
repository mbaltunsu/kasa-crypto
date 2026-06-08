from app.core.enums import (
    AssetType,
    DepositStatus,
    ErrorCode,
    LedgerEntryType,
    TransferStatus,
    UserRole,
    WithdrawalStatus,
)


def test_enum_values_match_contract() -> None:
    assert [item.value for item in AssetType] == ["native", "erc20", "erc721"]
    assert [item.value for item in UserRole] == ["user", "admin"]
    assert [item.value for item in DepositStatus] == ["seen", "confirmed", "credited", "orphaned"]
    assert [item.value for item in WithdrawalStatus] == [
        "requested",
        "approved",
        "signing",
        "broadcast",
        "confirmed",
        "failed",
        "rejected",
    ]
    assert [item.value for item in TransferStatus] == ["pending", "submitted", "confirmed", "failed"]
    assert [item.value for item in LedgerEntryType] == [
        "deposit",
        "withdrawal",
        "transfer_in",
        "transfer_out",
        "fee",
        "adjustment",
        "reversal",
    ]
    assert [item.value for item in ErrorCode] == [
        "validation_error",
        "insufficient_funds",
        "unknown_asset",
        "unsupported_chain",
        "withdrawal_rejected",
        "not_found",
        "unauthorized",
        "rate_limited",
        "internal_error",
    ]

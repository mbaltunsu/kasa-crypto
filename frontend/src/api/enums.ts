// Stable barrel for the backend-owned status/role enums. App code imports from here, never from
// the generated schema.gen.ts directly. A new backend enum value flows through here and breaks any
// non-exhaustive switch at compile time (intended).
import type { components } from "./schema.gen";

export type AssetType = components["schemas"]["AssetType"];
export type UserRole = components["schemas"]["UserRole"];
export type DepositStatus = components["schemas"]["DepositStatus"];
export type WithdrawalStatus = components["schemas"]["WithdrawalStatus"];
export type TransferStatus = components["schemas"]["TransferStatus"];
export type NftWithdrawalStatus = components["schemas"]["NftWithdrawalStatus"];
export type LedgerEntryType = components["schemas"]["LedgerEntryType"];
export type ErrorCode = components["schemas"]["ErrorCode"];

// Convenience response aliases used across pages.
export type Balance = components["schemas"]["BalanceResponse"];
export type ChainInfo = components["schemas"]["ChainResponse"];
export type AssetInfo = components["schemas"]["AssetResponse"];

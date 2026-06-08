// The ONLY place chain/asset literals live. Adding a chain/token/NFT is a data edit
// (packages/shared/data/**), never a source edit — these consts are stable infrastructure.

/** EVM coin type (BIP-44). Kasa reuses one EVM address across all EVM chains. */
export const EVM_COIN_TYPE = 60 as const;

/** Asset kinds. Single source for the data-domain enum; the Python side mirrors this (CI-asserted). */
export const ASSET_TYPES = ["native", "erc20", "erc721"] as const;
export type AssetType = (typeof ASSET_TYPES)[number];

/** Some token lists / aggregators denote a chain's native coin with this sentinel address. */
export const NATIVE_SENTINEL = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE" as const;

/** Strict EVM address shape — used to disambiguate address vs symbol in getAsset(). */
export const ADDRESS_RE = /^0x[0-9a-fA-F]{40}$/;

/** Pre-deploy placeholder; deploy.ts overwrites token addresses with the real checksummed value. */
export const ZERO_ADDRESS = "0x0000000000000000000000000000000000000000" as const;

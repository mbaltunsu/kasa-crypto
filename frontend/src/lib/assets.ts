import { formatAmount, getChain } from "@kasa/shared";

type AmountCapAsset = { symbol: string; decimals: number; max_amount?: string | null };

/** Per-transaction cap as a human label, e.g. "0.001 ETH", or null if the asset is uncapped. */
export function maxAmountLabel(asset: AmountCapAsset): string | null {
  if (asset.max_amount == null) return null;
  return `${formatAmount(asset, asset.max_amount)} ${asset.symbol}`;
}

/** Validate a base-unit amount against the asset's per-transaction cap. Error message, or null. */
export function amountCapError(asset: AmountCapAsset, base: bigint): string | null {
  if (asset.max_amount == null) return null;
  if (base > BigInt(asset.max_amount)) {
    return `Max ${maxAmountLabel(asset)} per transaction.`;
  }
  return null;
}

/** Full chain display name from the shared registry, e.g. "Ethereum Sepolia". */
export function chainLabel(chainId: number): string {
  try {
    return getChain(chainId).displayName;
  } catch {
    return `chain ${chainId}`;
  }
}

/** Short network label, e.g. "Sepolia" / "Fuji". */
export function shortChain(chainId: number): string {
  return chainLabel(chainId).replace(/^Ethereum\s+/, "").replace(/^Avalanche\s+/, "");
}

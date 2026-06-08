import { getChain } from "@kasa/shared";

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

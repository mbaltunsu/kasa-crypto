import { getAddress, isAddress as viemIsAddress, isAddressEqual as viemIsAddressEqual } from "viem";
import type { Address } from "viem";

/** Plain EIP-55 checksum. NEVER pass chainId (EIP-1191) — it diverges from eth_utils on the Py side. */
export function toChecksum(addr: string): Address {
  return getAddress(addr);
}

/** Canonical lowercase key for all cross-store address lookups/comparisons. */
export function toLookupKey(addr: string): string {
  return addr.toLowerCase();
}

export function isAddress(value: string): value is Address {
  return viemIsAddress(value);
}

/** Case-insensitive equality via EIP-55 normalization; false for malformed input. */
export function isAddressEqual(a: string, b: string): boolean {
  if (!viemIsAddress(a) || !viemIsAddress(b)) return false;
  return viemIsAddressEqual(getAddress(a), getAddress(b));
}

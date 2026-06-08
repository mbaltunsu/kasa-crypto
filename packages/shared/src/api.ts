import { REGISTRY, chainIndex } from "./registry.js";
import { ADDRESS_RE, EVM_COIN_TYPE, NATIVE_SENTINEL } from "./consts.js";
import { toChecksum, toLookupKey } from "./address.js";
import type { Asset, Chain, ChainId, Erc20Asset, Erc721Asset, NativeAsset } from "./types.js";

// ── type guards ──────────────────────────────────────────────────────────────
export function isNative(a: Asset): a is NativeAsset {
  return a.type === "native";
}
export function isErc20(a: Asset): a is Erc20Asset {
  return a.type === "erc20";
}
export function isErc721(a: Asset): a is Erc721Asset {
  return a.type === "erc721";
}

// ── chains ───────────────────────────────────────────────────────────────────
export function getChain(chainId: ChainId): Chain {
  return chainIndex(chainId).chain;
}
export function listChains(): Chain[] {
  return [...REGISTRY.values()].map((i) => i.chain);
}
export function chainIds(): ChainId[] {
  return [...REGISTRY.keys()];
}

// ── assets ───────────────────────────────────────────────────────────────────
export function tokensOfChain(chainId: ChainId): Asset[] {
  return chainIndex(chainId).chain.assets;
}
export function erc20sOfChain(chainId: ChainId): Erc20Asset[] {
  return chainIndex(chainId).chain.assets.filter(isErc20);
}
export function nftsOfChain(chainId: ChainId): Erc721Asset[] {
  return chainIndex(chainId).chain.assets.filter(isErc721);
}
export function nativeAsset(chainId: ChainId): NativeAsset {
  return chainIndex(chainId).native;
}

function isNativeSentinel(addr: string): boolean {
  return toLookupKey(addr) === toLookupKey(NATIVE_SENTINEL);
}

export function assetBySymbol(chainId: ChainId, symbol: string): Asset | undefined {
  return chainIndex(chainId).bySymbol.get(symbol.toUpperCase());
}
export function assetByAddress(chainId: ChainId, address: string): Asset | undefined {
  if (isNativeSentinel(address)) return chainIndex(chainId).native;
  return chainIndex(chainId).byAddress.get(toLookupKey(address));
}

/** Resolve by address (strict 0x[40] or native sentinel) else by symbol. Throws if unknown. */
export function getAsset(chainId: ChainId, key: string): Asset {
  const found = ADDRESS_RE.test(key) ? assetByAddress(chainId, key) : assetBySymbol(chainId, key);
  if (!found) throw new Error(`unknown asset '${key}' on chain ${chainId}`);
  return found;
}

export function decimalsOf(a: Asset): number {
  return a.decimals;
}

// ── explorer / derivation ──────────────────────────────────────────────────────
export function explorerTxUrl(chainId: ChainId, hash: string): string {
  return getChain(chainId).explorerTxUrl.replace("{hash}", hash);
}
export function explorerAddressUrl(chainId: ChainId, address: string): string {
  return getChain(chainId).explorerAddressUrl.replace("{address}", toChecksum(address));
}
export function derivationPath(chainId: ChainId, hdIndex: number): string {
  const { coinType } = getChain(chainId);
  return `m/44'/${coinType}'/0'/0/${hdIndex}`;
}
export { EVM_COIN_TYPE };

// ── parity ─────────────────────────────────────────────────────────────────────
/**
 * Canonical, stable serialization of all assets — hashed in CI and at backend boot to assert
 * registry == DB. Mirrored byte-for-byte by the Python `canonical_rows`.
 */
export function canonicalRows(): string {
  const rows: string[] = [];
  for (const chainId of [...REGISTRY.keys()].sort((a, b) => a - b)) {
    for (const a of tokensOfChain(chainId)) {
      const addr = a.type === "native" ? "" : toLookupKey(a.address);
      rows.push([chainId, a.type, addr, a.symbol.toUpperCase(), a.decimals].join("|"));
    }
  }
  return rows.sort().join("\n");
}

import { describe, expect, it } from "vitest";
import {
  assetByAddress,
  assetBySymbol,
  canonicalRows,
  chainIds,
  derivationPath,
  explorerAddressUrl,
  explorerTxUrl,
  getAsset,
  getChain,
  nativeAsset,
} from "../api.js";
import { NATIVE_SENTINEL, ZERO_ADDRESS } from "../consts.js";

const SEPOLIA = 11155111;
const FUJI = 43113;
const HARDHAT = 31337;

describe("registry", () => {
  it("loads exactly the manifest chains", () => {
    expect(chainIds().slice().sort((a, b) => a - b)).toEqual(
      [SEPOLIA, FUJI, HARDHAT].sort((a, b) => a - b),
    );
    expect(getChain(SEPOLIA).name).toBe("ethereum-sepolia");
    expect(getChain(FUJI).nativeSymbol).toBe("AVAX");
    expect(getChain(HARDHAT).name).toBe("hardhat-local");
  });

  it("native asset has no address field", () => {
    const eth = nativeAsset(SEPOLIA);
    expect(eth.type).toBe("native");
    expect(eth.symbol).toBe("ETH");
    expect("address" in eth).toBe(false);
  });

  it("symbol lookup is case-insensitive", () => {
    expect(assetBySymbol(SEPOLIA, "demo")?.type).toBe("erc20");
    expect(assetBySymbol(SEPOLIA, "DEMO")?.symbol).toBe("DEMO");
  });

  it("native sentinel resolves to the native asset", () => {
    expect(assetByAddress(SEPOLIA, NATIVE_SENTINEL)?.symbol).toBe("ETH");
    expect(getAsset(SEPOLIA, NATIVE_SENTINEL).type).toBe("native");
  });

  it("undeployed (zero-address) tokens are not address-indexed", () => {
    expect(assetByAddress(SEPOLIA, ZERO_ADDRESS)).toBeUndefined();
  });

  it("getAsset dispatches symbol vs address and throws on unknown", () => {
    expect(getAsset(SEPOLIA, "DEMO").symbol).toBe("DEMO");
    expect(() => getAsset(SEPOLIA, "NOPE")).toThrow();
    expect(() => getChain(999)).toThrow();
  });

  it("explorer + derivation builders use templates, not concat", () => {
    expect(explorerTxUrl(SEPOLIA, "0xabc")).toBe("https://sepolia.etherscan.io/tx/0xabc");
    expect(explorerAddressUrl(FUJI, ZERO_ADDRESS)).toBe(
      `https://testnet.snowtrace.io/address/${ZERO_ADDRESS}`,
    );
    expect(derivationPath(SEPOLIA, 7)).toBe("m/44'/60'/0'/0/7");
  });

  it("canonicalRows is sorted, stable, and includes native", () => {
    const rows = canonicalRows();
    expect(rows).toBe(rows.split("\n").sort().join("\n"));
    expect(rows).toContain("11155111|native||ETH|18");
    expect(rows).toContain("43113|erc721||KASA|0".replace("||", `|${ZERO_ADDRESS.toLowerCase()}|`));
  });
});

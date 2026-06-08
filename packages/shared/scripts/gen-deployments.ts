// Project the registry into the LOCKED deployments.json shape (addresses, decimals, deploymentBlock)
// consumed by the backend watcher. deploymentsSchema.strict() guarantees no registry-only field
// (coinType, derivation, …) ever leaks into this artifact. Committed; deploy.ts refreshes addresses.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chainSchema, deploymentsSchema, manifestSchema } from "../src/schema.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (p: string): unknown => JSON.parse(readFileSync(join(root, p), "utf8"));

const manifest = manifestSchema.parse(read("data/registry.json"));
const chains = manifest.chainIds.map((id) => chainSchema.parse(read(`data/chains/${id}.json`)));

// Registry symbol -> deployments.json contract name.
const CONTRACT_BY_SYMBOL: Record<string, string> = { DEMO: "DemoToken", KASA: "DemoCollectible" };

const networks: Record<string, unknown> = {};
for (const chain of chains) {
  const contracts: Record<string, { address: string; decimals?: number; deploymentBlock: number }> = {};
  for (const asset of chain.assets) {
    if (asset.type === "native") continue;
    const name = CONTRACT_BY_SYMBOL[asset.symbol];
    if (!name) continue;
    contracts[name] =
      asset.type === "erc20"
        ? { address: asset.address, decimals: asset.decimals, deploymentBlock: asset.deploymentBlock }
        : { address: asset.address, deploymentBlock: asset.deploymentBlock };
  }
  networks[String(chain.chainId)] = {
    name: chain.name,
    nativeSymbol: chain.nativeSymbol,
    rpcEnv: chain.rpcEnv,
    explorerTxUrl: chain.explorerTxUrl,
    explorerAddressUrl: chain.explorerAddressUrl,
    contracts,
  };
}

const out = deploymentsSchema.parse({ version: manifest.version, updatedAt: manifest.updatedAt, networks });
writeFileSync(join(root, "deployments.json"), JSON.stringify(out, null, 2) + "\n");
console.log(`deployments.json written: ${Object.keys(networks).length} networks`);

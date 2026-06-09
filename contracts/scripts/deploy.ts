// Deploy DemoToken + DemoCollectible, then write their checksummed addresses + deployment blocks
// back into the registry master (packages/shared/data/chains/<chainId>.json) and regenerate the
// bundle + locked deployments.json. The registry stays the single source of truth.
import { execSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { ethers, network } from "hardhat";

interface AssetEntry {
  type: string;
  symbol: string;
  address?: string;
  deploymentBlock?: number;
  [k: string]: unknown;
}

async function blockOf(tx: { hash: string } | null): Promise<number> {
  if (!tx) throw new Error("missing deployment transaction");
  const receipt = await ethers.provider.getTransactionReceipt(tx.hash);
  if (!receipt) throw new Error(`no receipt for ${tx.hash}`);
  return receipt.blockNumber;
}

async function main(): Promise<void> {
  const [deployer] = await ethers.getSigners();
  const chainId = Number((await ethers.provider.getNetwork()).chainId);
  // The contract owner (= service hot wallet) signs onlyOwner mints and holds the DEMO faucet
  // supply. Defaults to the deployer (local/dev); set HOT_WALLET_OWNER to the custody wallet on
  // testnets so the worker's mint and the faucet sends work from the hot wallet.
  const owner = process.env.HOT_WALLET_OWNER
    ? ethers.getAddress(process.env.HOT_WALLET_OWNER)
    : deployer.address;
  console.log(
    `Deploying to chainId ${chainId} (${network.name}) as ${deployer.address}; owner=${owner}`,
  );

  const token = await ethers.deployContract("DemoToken", [owner]);
  await token.waitForDeployment();
  const nft = await ethers.deployContract("DemoCollectible", [owner]);
  await nft.waitForDeployment();

  const tokenAddr = await token.getAddress(); // ethers returns EIP-55 checksummed
  const nftAddr = await nft.getAddress();
  const tokenBlock = await blockOf(token.deploymentTransaction());
  const nftBlock = await blockOf(nft.deploymentTransaction());
  console.log(`DemoToken       ${tokenAddr} @ block ${tokenBlock}`);
  console.log(`DemoCollectible ${nftAddr} @ block ${nftBlock}`);

  const repoRoot = resolve(__dirname, "..", "..");
  const dataPath = resolve(repoRoot, "packages/shared/data/chains", `${chainId}.json`);
  if (!existsSync(dataPath)) {
    console.warn(`No registry data file for chainId ${chainId} — skipping registry update.`);
    return;
  }

  const data = JSON.parse(readFileSync(dataPath, "utf8")) as { assets: AssetEntry[] };
  for (const a of data.assets) {
    if (a.type === "erc20" && a.symbol === "DEMO") {
      a.address = tokenAddr;
      a.deploymentBlock = tokenBlock;
    }
    if (a.type === "erc721" && a.symbol === "KASA") {
      a.address = nftAddr;
      a.deploymentBlock = nftBlock;
    }
  }
  writeFileSync(dataPath, JSON.stringify(data, null, 2) + "\n");
  console.log(`Updated registry: ${dataPath}`);

  execSync("pnpm --filter @kasa/shared gen:registry && pnpm --filter @kasa/shared gen:deployments", {
    cwd: repoRoot,
    stdio: "inherit",
  });
  console.log("Regenerated registry bundle + deployments.json. Run `pnpm hardhat verify` next.");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

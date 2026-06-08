import { HardhatUserConfig } from "hardhat/config";
import "@nomicfoundation/hardhat-toolbox";
import * as dotenv from "dotenv";
import { resolve } from "node:path";

// Reuse the monorepo root .env (RPC_*, deployer key, explorer API keys).
dotenv.config({ path: resolve(__dirname, "..", ".env") });

/** First entry of a comma-separated RPC fallback list, or a public default. */
function rpc(envName: string, fallback: string): string {
  const raw = process.env[envName];
  return raw ? raw.split(",")[0]!.trim() : fallback;
}

const deployerKey = process.env.DEPLOYER_PRIVATE_KEY;
const accounts = deployerKey ? [deployerKey] : [];

const config: HardhatUserConfig = {
  solidity: {
    version: "0.8.28",
    settings: { optimizer: { enabled: true, runs: 200 }, evmVersion: "cancun" },
  },
  networks: {
    hardhat: {},
    sepolia: {
      url: rpc("RPC_ETHEREUM_SEPOLIA", "https://ethereum-sepolia.publicnode.com"),
      chainId: 11155111,
      accounts,
    },
    fuji: {
      url: rpc("RPC_AVALANCHE_FUJI", "https://api.avax-test.network/ext/bc/C/rpc"),
      chainId: 43113,
      accounts,
    },
  },
  // Etherscan V2 is multichain: a single Etherscan API key verifies Sepolia AND Avalanche Fuji.
  etherscan: {
    apiKey: process.env.ETHERSCAN_API_KEY ?? "",
  },
};

export default config;

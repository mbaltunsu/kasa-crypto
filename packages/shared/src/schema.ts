import { z } from "zod";
import { getAddress } from "viem";

// Plain EIP-55 checksum — NEVER pass a chainId to getAddress (that is EIP-1191, incompatible
// with eth_utils.to_checksum_address on the Python side).
const checksummed = z
  .string()
  .regex(/^0x[0-9a-fA-F]{40}$/, "invalid EVM address")
  .transform((a) => getAddress(a));

const symbol = z
  .string()
  .min(1)
  .refine((s) => !s.toUpperCase().startsWith("0X"), "symbol must not be 0x-prefixed");

export const nativeAssetSchema = z.object({
  type: z.literal("native"),
  symbol,
  name: z.string().min(1),
  decimals: z.number().int().nonnegative(),
});

export const erc20AssetSchema = z.object({
  type: z.literal("erc20"),
  symbol,
  name: z.string().min(1),
  decimals: z.number().int().nonnegative(),
  address: checksummed,
  deploymentBlock: z.number().int().nonnegative().default(0),
});

export const erc721AssetSchema = z.object({
  type: z.literal("erc721"),
  symbol,
  name: z.string().min(1),
  decimals: z.literal(0), // an NFT has no fractional units — guards formatAmount misuse
  address: checksummed,
  deploymentBlock: z.number().int().nonnegative().default(0),
});

export const assetSchema = z.discriminatedUnion("type", [
  nativeAssetSchema,
  erc20AssetSchema,
  erc721AssetSchema,
]);

export const chainSchema = z.object({
  chainId: z.number().int().positive(),
  name: z.string().regex(/^[a-z0-9-]+$/, "slug must be kebab-case"),
  displayName: z.string().min(1),
  nativeSymbol: z.string().min(1),
  coinType: z.number().int().nonnegative(),
  rpcEnv: z.string().regex(/^[A-Z0-9_]+$/, "env var name"),
  explorerTxUrl: z.string().includes("{hash}"),
  explorerAddressUrl: z.string().includes("{address}"),
  assets: z.array(assetSchema).min(1),
});

export const manifestSchema = z.object({
  version: z.number().int(),
  updatedAt: z.string(),
  chainIds: z.array(z.number().int().positive()).min(1),
});

export const registryBundleSchema = z.object({
  version: z.number().int(),
  updatedAt: z.string(),
  chains: z.array(chainSchema).min(1),
});

// Locked deployments.json shape — strict() so gen-deployments cannot leak registry-only fields.
const deploymentContract = z
  .object({ address: z.string(), decimals: z.number().int().optional(), deploymentBlock: z.number().int() })
  .strict();
export const deploymentsSchema = z
  .object({
    version: z.number().int(),
    updatedAt: z.string(),
    networks: z.record(
      z.string(),
      z
        .object({
          name: z.string(),
          nativeSymbol: z.string(),
          rpcEnv: z.string(),
          explorerTxUrl: z.string(),
          explorerAddressUrl: z.string(),
          contracts: z.record(z.string(), deploymentContract),
        })
        .strict(),
    ),
  })
  .strict();

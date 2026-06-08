import type { z } from "zod";
import type { Address } from "viem";
import type {
  assetSchema,
  chainSchema,
  erc20AssetSchema,
  erc721AssetSchema,
  nativeAssetSchema,
} from "./schema.js";

export type Asset = z.infer<typeof assetSchema>;
export type NativeAsset = z.infer<typeof nativeAssetSchema>;
export type Erc20Asset = z.infer<typeof erc20AssetSchema>;
export type Erc721Asset = z.infer<typeof erc721AssetSchema>;
export type Chain = z.infer<typeof chainSchema>;
export type { Address };

/**
 * Branded number derived from registry data — NOT a hand-maintained literal union, so adding a
 * chain stays a data-only edit. Membership is validated at runtime by the registry.
 */
export type ChainId = number;

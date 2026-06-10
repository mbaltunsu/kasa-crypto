"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, setAccessToken } from "./client";
import type { components } from "./client";

type S = components["schemas"];

/** openapi-fetch returns { data, error }; throw the typed error so React Query surfaces it. */
async function must<T>(res: { data?: T; error?: unknown }): Promise<T> {
  if (res.error || res.data === undefined) throw res.error ?? new Error("Request failed");
  return res.data;
}

function idempotency(): { header: { "Idempotency-Key": string } } {
  return { header: { "Idempotency-Key": crypto.randomUUID() } };
}

// ── queries ────────────────────────────────────────────────────────────────
export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: async () => must(await api.GET("/api/v1/me")) });
}

export function useChains() {
  return useQuery({
    queryKey: ["chains"],
    queryFn: async () => must(await api.GET("/api/v1/chains")),
    staleTime: Infinity,
  });
}

export function useAssets(chainId?: number) {
  return useQuery({
    queryKey: ["assets", chainId ?? null],
    queryFn: async () =>
      must(await api.GET("/api/v1/assets", { params: { query: { chain_id: chainId } } })),
    staleTime: Infinity,
  });
}

/** asset_id -> AssetResponse, for resolving decimals/symbol/chain on amount-only payloads. */
export function useAssetMap() {
  const q = useAssets();
  const map = new Map((q.data ?? []).map((a) => [a.id, a] as const));
  return { map, isLoading: q.isLoading };
}

export type AssetInfo = S["AssetResponse"];

export function useBalances() {
  return useQuery({
    queryKey: ["balances"],
    queryFn: async () => must(await api.GET("/api/v1/wallet/balances")),
  });
}

export function useDepositAddresses() {
  return useQuery({
    queryKey: ["deposit-addresses"],
    queryFn: async () => must(await api.GET("/api/v1/wallet/deposit-addresses")),
    staleTime: Infinity,
  });
}

export function useTransactions(assetId?: string) {
  return useQuery({
    queryKey: ["transactions", assetId ?? null],
    queryFn: async () =>
      must(await api.GET("/api/v1/transactions", { params: { query: { asset_id: assetId } } })),
  });
}

export function useDeposits() {
  return useQuery({
    queryKey: ["deposits"],
    queryFn: async () => must(await api.GET("/api/v1/deposits", { params: { query: {} } })),
  });
}

export function useWithdrawals() {
  return useQuery({
    queryKey: ["withdrawals"],
    queryFn: async () =>
      must(await api.GET("/api/v1/withdrawals", { params: { query: {} } })),
  });
}

export function useNfts() {
  return useQuery({ queryKey: ["nfts"], queryFn: async () => must(await api.GET("/api/v1/nfts")) });
}

export function useMyNfts() {
  return useNfts();
}

export function useAdminReserves() {
  return useQuery({
    queryKey: ["admin", "reserves"],
    queryFn: async () => must(await api.GET("/api/v1/admin/reserves")),
  });
}

export function useAdminGas() {
  return useQuery({
    queryKey: ["admin", "gas"],
    queryFn: async () => must(await api.GET("/api/v1/admin/gas")),
  });
}

export function useAdminWithdrawals() {
  return useQuery({
    queryKey: ["admin", "withdrawals"],
    queryFn: async () =>
      must(await api.GET("/api/v1/admin/withdrawals", { params: { query: {} } })),
  });
}

// ── mutations ──────────────────────────────────────────────────────────────
export function useRegister() {
  return useMutation({
    mutationFn: async (body: S["RegisterRequest"]) =>
      must(await api.POST("/api/v1/auth/register", { body })),
    onSuccess: (data) => setAccessToken(data.access_token),
  });
}

export function useLogin() {
  return useMutation({
    mutationFn: async (body: S["LoginRequest"]) =>
      must(await api.POST("/api/v1/auth/login", { body })),
    onSuccess: (data) => setAccessToken(data.access_token),
  });
}

export function useFaucet() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: S["FaucetRequest"]) =>
      must(await api.POST("/api/v1/demo/faucet", { body, params: idempotency() })),
    onSuccess: () => {
      toast.success("Faucet sent — it will credit after confirmations.");
      void qc.invalidateQueries({ queryKey: ["balances"] });
      void qc.invalidateQueries({ queryKey: ["deposits"] });
    },
  });
}

export function useWithdraw() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: S["WithdrawalCreateRequest"]) =>
      must(await api.POST("/api/v1/withdrawals", { body, params: idempotency() })),
    onSuccess: () => {
      toast.success("Withdrawal submitted.");
      void qc.invalidateQueries({ queryKey: ["balances"] });
      void qc.invalidateQueries({ queryKey: ["transactions"] });
    },
  });
}

export function useTransfer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: S["TransferCreateRequest"]) =>
      must(await api.POST("/api/v1/transfers", { body, params: idempotency() })),
    onSuccess: () => {
      toast.success("Transfer sent.");
      void qc.invalidateQueries({ queryKey: ["balances"] });
      void qc.invalidateQueries({ queryKey: ["transactions"] });
    },
  });
}

export function useNftTransfer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: S["NftTransferCreateRequest"]) =>
      must(await api.POST("/api/v1/nft-transfers", { body, params: idempotency() })),
    onSuccess: () => {
      toast.success("NFT transferred.");
      void qc.invalidateQueries({ queryKey: ["nfts"] });
    },
  });
}

export function useNftWithdrawal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: S["NftWithdrawalCreateRequest"]) =>
      must(await api.POST("/api/v1/nft-withdrawals", { body, params: idempotency() })),
    onSuccess: () => {
      toast.success("NFT withdrawal submitted.");
      void qc.invalidateQueries({ queryKey: ["nfts"] });
    },
  });
}

export function useMintNft() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: S["AdminMintNftRequest"]) =>
      must(await api.POST("/api/v1/admin/mint-nft", { body })),
    onSuccess: () => {
      toast.success("NFT mint requested.");
      void qc.invalidateQueries({ queryKey: ["nfts"] });
    },
  });
}

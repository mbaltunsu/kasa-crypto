"use client";

import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import { MoneyText } from "@/components/ui/MoneyText";
import { StatusPill } from "@/components/ui/StatusPill";
import { Skeleton } from "@/components/ui/Skeleton";
import { shortChain } from "@/lib/assets";
import {
  useAdminReserves,
  useAdminWithdrawals,
  useAssetMap,
  useChains,
  useMintNft,
} from "@/api/queries";

export default function AdminPage() {
  const reserves = useAdminReserves();
  const withdrawals = useAdminWithdrawals();
  const chains = useChains().data ?? [];
  const mint = useMintNft();
  const { map: assets } = useAssetMap();
  const dec = (id: string) => assets.get(id)?.decimals ?? 18;
  const sym = (id: string) => assets.get(id)?.symbol ?? "—";

  const [email, setEmail] = useState("");
  const [chainId, setChainId] = useState<number | "">("");

  function submitMint(e: React.FormEvent) {
    e.preventDefault();
    const cid = chainId === "" ? chains[0]?.chain_id : chainId;
    if (!cid || !email) return;
    mint.mutate({ chain_id: cid, user_email: email });
  }

  return (
    <>
      <TopBar title="Admin · Reserves" />
      <main className="max-w-5xl space-y-6 p-5 sm:p-7">
        {/* Proof of reserves */}
        <Card className="overflow-hidden">
          <div className="flex items-center gap-2 border-b border-border px-5 py-4 text-sm font-semibold">
            <ShieldCheck className="h-4 w-4 text-gold" /> Proof of reserves
          </div>
          {reserves.isLoading ? (
            <div className="space-y-2 p-5">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-xs text-muted">
                <tr className="border-b border-border">
                  <th className="px-5 py-2.5 text-left font-medium">Asset</th>
                  <th className="px-5 py-2.5 text-right font-medium">Liabilities</th>
                  <th className="px-5 py-2.5 text-right font-medium">On-chain reserves</th>
                  <th className="px-5 py-2.5 text-right font-medium">Delta</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {(reserves.data?.assets ?? []).map((r) => (
                  <tr key={r.asset_id} className="hover:bg-surface2/50">
                    <td className="px-5 py-3">{sym(r.asset_id)}</td>
                    <td className="px-5 py-3 text-right">
                      <MoneyText amount={r.liabilities} decimals={dec(r.asset_id)} />
                    </td>
                    <td className="px-5 py-3 text-right">
                      <MoneyText amount={r.reserves} decimals={dec(r.asset_id)} />
                    </td>
                    <td className="px-5 py-3 text-right">
                      <MoneyText
                        amount={r.delta}
                        decimals={dec(r.asset_id)}
                        className={r.delta === "0" ? "text-pos" : "text-neg"}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        {/* Mint NFT */}
        <Card className="p-6">
          <h2 className="text-sm font-semibold">Mint a collectible to a user</h2>
          <form className="mt-4 grid gap-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end" onSubmit={submitMint}>
            <Field label="User email" htmlFor="email">
              <Input
                id="email"
                type="email"
                placeholder="user@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </Field>
            <Field label="Chain" htmlFor="chain">
              <Select
                id="chain"
                value={chainId}
                onChange={(e) => setChainId(e.target.value === "" ? "" : Number(e.target.value))}
              >
                {chains.map((c) => (
                  <option key={c.chain_id} value={c.chain_id}>
                    {shortChain(c.chain_id)}
                  </option>
                ))}
              </Select>
            </Field>
            <Button type="submit" disabled={mint.isPending}>
              {mint.isPending ? "Minting…" : "Mint"}
            </Button>
          </form>
          {mint.isSuccess ? (
            <p className="mt-3 text-xs text-pos">
              {mint.data.status === "confirmed" && mint.data.token_id && mint.data.tx_hash
                ? `Minted token #${mint.data.token_id} · tx ${mint.data.tx_hash.slice(0, 12)}…`
                : `Mint request ${mint.data.request_id ?? ""} queued`}
            </p>
          ) : null}
        </Card>

        {/* All withdrawals */}
        <Card className="overflow-hidden">
          <div className="border-b border-border px-5 py-4 text-sm font-semibold">All withdrawals</div>
          {withdrawals.isLoading ? (
            <div className="space-y-2 p-5">
              <Skeleton className="h-8 w-full" />
            </div>
          ) : (withdrawals.data?.items ?? []).length === 0 ? (
            <p className="p-8 text-center text-sm text-muted">No withdrawals.</p>
          ) : (
            <table className="w-full text-sm">
              <tbody className="divide-y divide-border">
                {(withdrawals.data?.items ?? []).map((w) => (
                  <tr key={w.id} className="hover:bg-surface2/50">
                    <td className="px-5 py-3">{sym(w.asset_id)}</td>
                    <td className="px-5 py-3 text-right">
                      <MoneyText amount={w.amount} decimals={dec(w.asset_id)} />
                    </td>
                    <td className="num px-5 py-3 font-mono text-xs text-muted">
                      {w.to_address.slice(0, 10)}…
                    </td>
                    <td className="px-5 py-3">
                      <StatusPill status={w.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </main>
    </>
  );
}

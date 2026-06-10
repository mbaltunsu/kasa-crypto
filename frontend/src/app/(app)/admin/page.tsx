"use client";

import { useEffect, useRef, useState } from "react";
import { ExternalLink, Fuel, ShieldCheck } from "lucide-react";
import { explorerTxUrl } from "@kasa/shared";
import { toast } from "sonner";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import { UserSelect } from "@/components/ui/UserSelect";
import { MoneyText } from "@/components/ui/MoneyText";
import { NetworkIcon } from "@/components/ui/NetworkIcon";
import { StatusPill } from "@/components/ui/StatusPill";
import { Skeleton } from "@/components/ui/Skeleton";
import { shortChain } from "@/lib/assets";
import {
  useAdminGas,
  useAdminReserves,
  useAdminWithdrawals,
  useAssetMap,
  useChains,
  useMintNft,
  useMintStatus,
} from "@/api/queries";
import type { GasStatus } from "@/api/enums";

const GAS_BADGE: Record<GasStatus, string> = {
  ok: "bg-pos/10 text-pos ring-pos/30",
  low: "bg-warn/10 text-warn ring-warn/30",
  critical: "bg-neg/10 text-neg ring-neg/30",
  unknown: "bg-surface2/80 text-muted ring-border/80",
};

function GasBadge({ status }: { status: GasStatus }) {
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ring-1 ${GAS_BADGE[status]}`}
    >
      {status}
    </span>
  );
}

function needsTopUp(status: GasStatus) {
  return status === "low" || status === "critical";
}

export default function AdminPage() {
  const reserves = useAdminReserves();
  const gas = useAdminGas();
  const withdrawals = useAdminWithdrawals();
  const chains = useChains().data ?? [];
  const mint = useMintNft();
  const { map: assets } = useAssetMap();
  const dec = (id: string) => assets.get(id)?.decimals ?? 18;
  const sym = (id: string) => assets.get(id)?.symbol ?? "—";

  const [email, setEmail] = useState("");
  const [chainId, setChainId] = useState<number | "">("");
  // Track the in-flight on-chain mint so we can poll its progress and build an explorer link.
  const [requestId, setRequestId] = useState<string | null>(null);
  const [mintChain, setMintChain] = useState<number | null>(null);
  const mintStatus = useMintStatus(requestId);
  const toastedRef = useRef<string | null>(null);

  useEffect(() => {
    const status = mintStatus.data?.status;
    if (!requestId || (status !== "confirmed" && status !== "failed")) return;
    const key = `${requestId}:${status}`;
    if (toastedRef.current === key) return;
    toastedRef.current = key;
    if (status === "confirmed") {
      toast.success(`NFT minted — token #${mintStatus.data?.token_id ?? ""}`);
    } else {
      toast.error("NFT mint failed.");
    }
  }, [requestId, mintStatus.data?.status, mintStatus.data?.token_id]);

  function submitMint(e: React.FormEvent) {
    e.preventDefault();
    const cid = chainId === "" ? chains[0]?.chain_id : chainId;
    if (!cid || !email) return;
    setRequestId(null);
    toastedRef.current = null;
    mint.mutate(
      { chain_id: cid, user_email: email },
      {
        onSuccess: (data) => {
          setMintChain(cid);
          setRequestId(data.request_id ?? null);
        },
      },
    );
  }

  return (
    <>
      <TopBar title="Admin · Reserves" />
      <main className="max-w-5xl animate-fade-up space-y-6 p-5 sm:p-7">
        {/* Proof of reserves */}
        <Card className="overflow-hidden">
          <div className="flex items-center gap-2.5 border-b border-border/60 px-5 py-4 text-sm font-semibold text-ink-hi">
            <span className="grid h-7 w-7 place-items-center rounded-lg bg-gold/10 ring-1 ring-gold/30">
              <ShieldCheck className="h-4 w-4 text-gold" />
            </span>
            Proof of reserves
          </div>
          {reserves.isLoading ? (
            <div className="space-y-2 p-5">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : (
            <div className="overflow-x-auto"><table className="w-full min-w-[34rem] text-sm">
              <thead className="text-[11px] uppercase tracking-wider text-muted">
                <tr className="border-b border-border/60">
                  <th className="px-5 py-2.5 text-left font-semibold">Asset</th>
                  <th className="px-5 py-2.5 text-right font-semibold">Liabilities</th>
                  <th className="px-5 py-2.5 text-right font-semibold">On-chain reserves</th>
                  <th className="px-5 py-2.5 text-right font-semibold">Delta</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {(reserves.data?.assets ?? []).map((r) => (
                  <tr key={r.asset_id} className="transition-colors hover:bg-surface2/40">
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
            </table></div>
          )}
        </Card>

        {/* Gas balances */}
        <Card className="overflow-hidden">
          <div className="flex items-center gap-2.5 border-b border-border/60 px-5 py-4 text-sm font-semibold text-ink-hi">
            <span className="grid h-7 w-7 place-items-center rounded-lg bg-aqua/10 ring-1 ring-aqua/30">
              <Fuel className="h-4 w-4 text-aqua" />
            </span>
            Gas balances
          </div>
          {gas.isLoading ? (
            <div className="space-y-2 p-5">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : (
            <>
              <div className="overflow-x-auto"><table className="w-full min-w-[34rem] text-sm">
                <thead className="text-[11px] uppercase tracking-wider text-muted">
                  <tr className="border-b border-border/60">
                    <th className="px-5 py-2.5 text-left font-semibold">Chain</th>
                    <th className="px-5 py-2.5 text-right font-semibold">Hot wallet gas</th>
                    <th className="px-5 py-2.5 text-right font-semibold">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/50">
                  {(gas.data?.chains ?? []).map((chain) => (
                    <tr key={chain.chain_id} className="transition-colors hover:bg-surface2/40">
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-2.5">
                          <NetworkIcon chainId={chain.chain_id} className="h-5 w-5" />
                          <div>
                            <div className="font-medium">{shortChain(chain.chain_id)}</div>
                            <div className="text-xs text-muted">{chain.symbol}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-3 text-right">
                        <MoneyText
                          amount={chain.balance}
                          decimals={chain.decimals}
                          symbol={chain.symbol}
                        />
                      </td>
                      <td className="px-5 py-3 text-right">
                        <GasBadge status={chain.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table></div>
              {(gas.data?.chains ?? []).some((chain) => needsTopUp(chain.status)) ? (
                <p className="border-t border-border/60 bg-warn/[0.05] px-5 py-3 text-xs font-medium text-warn">
                  Top up hot wallets marked low or critical before queued sends stall.
                </p>
              ) : null}
            </>
          )}
        </Card>

        {/* Mint NFT */}
        <Card className="p-6">
          <h2 className="text-sm font-semibold text-ink-hi">Mint a collectible to a user</h2>
          <form className="mt-4 grid gap-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end" onSubmit={submitMint}>
            <Field label="User" htmlFor="email">
              <UserSelect id="email" value={email} placeholder="Select a user…" onChange={setEmail} />
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
            <Button type="submit" disabled={mint.isPending || !email}>
              {mint.isPending ? "Minting…" : "Mint"}
            </Button>
          </form>
          {requestId ? (
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
              <span className="text-muted">Mint progress:</span>
              <StatusPill status={mintStatus.data?.status ?? "requested"} />
              {mintStatus.data?.token_id ? (
                <span className="num text-muted">token #{mintStatus.data.token_id}</span>
              ) : null}
              {mintStatus.data?.tx_hash && mintChain ? (
                <a
                  className="inline-flex items-center gap-1 text-muted underline-offset-2 hover:text-gold hover:underline"
                  href={explorerTxUrl(mintChain, mintStatus.data.tx_hash)}
                  target="_blank"
                  rel="noreferrer"
                >
                  view tx <ExternalLink className="h-3 w-3" />
                </a>
              ) : null}
            </div>
          ) : mint.isSuccess && mint.data.status === "confirmed" ? (
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
              <StatusPill status="confirmed" />
              {mint.data.token_id ? (
                <span className="num text-muted">token #{mint.data.token_id} (simulated)</span>
              ) : null}
            </div>
          ) : null}
        </Card>

        {/* All withdrawals */}
        <Card className="overflow-hidden">
          <div className="border-b border-border/60 px-5 py-4 text-sm font-semibold text-ink-hi">
            All withdrawals
          </div>
          {withdrawals.isLoading ? (
            <div className="space-y-2 p-5">
              <Skeleton className="h-8 w-full" />
            </div>
          ) : (withdrawals.data?.items ?? []).length === 0 ? (
            <p className="p-8 text-center text-sm text-muted">No withdrawals.</p>
          ) : (
            <div className="overflow-x-auto"><table className="w-full min-w-[34rem] text-sm">
              <tbody className="divide-y divide-border/50">
                {(withdrawals.data?.items ?? []).map((w) => (
                  <tr key={w.id} className="transition-colors hover:bg-surface2/40">
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
            </table></div>
          )}
        </Card>
      </main>
    </>
  );
}

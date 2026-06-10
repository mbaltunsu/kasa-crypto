"use client";

import { ExternalLink } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Card } from "@/components/ui/Card";
import { MoneyText } from "@/components/ui/MoneyText";
import { NetworkIcon } from "@/components/ui/NetworkIcon";
import { StatusPill } from "@/components/ui/StatusPill";
import { Skeleton } from "@/components/ui/Skeleton";
import { shortChain } from "@/lib/assets";
import { useAssetMap, useDeposits, useNftMints, useWithdrawals } from "@/api/queries";

export default function HistoryPage() {
  const deposits = useDeposits();
  const withdrawals = useWithdrawals();
  const mints = useNftMints();
  const { map: assets } = useAssetMap();
  const dec = (id: string) => assets.get(id)?.decimals ?? 18;
  const sym = (id: string, fallback?: string) => assets.get(id)?.symbol ?? fallback ?? "—";

  return (
    <>
      <TopBar title="History" />
      <main className="max-w-5xl animate-fade-up space-y-6 p-5 sm:p-7">
        {/* Deposits */}
        <Card className="overflow-hidden">
          <div className="border-b border-border/60 px-5 py-4 text-sm font-semibold text-ink-hi">Deposits</div>
          {deposits.isLoading ? (
            <div className="space-y-2 p-5">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : (deposits.data?.items ?? []).length === 0 ? (
            <p className="p-8 text-center text-sm text-muted">No deposits yet.</p>
          ) : (
            <div className="overflow-x-auto"><table className="w-full min-w-[34rem] text-sm">
              <thead className="text-[11px] uppercase tracking-wider text-muted">
                <tr className="border-b border-border/60">
                  <th className="px-5 py-2.5 text-left font-semibold">Asset</th>
                  <th className="px-5 py-2.5 text-right font-semibold">Amount</th>
                  <th className="px-5 py-2.5 text-left font-semibold">Status</th>
                  <th className="px-5 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {(deposits.data?.items ?? []).map((d) => (
                  <tr key={d.id} className="transition-colors hover:bg-surface2/40">
                    <td className="px-5 py-3">
                      <span className="inline-flex items-center gap-2">
                        <NetworkIcon chainId={d.chain_id} className="h-4 w-4" />
                        {d.symbol}{" "}
                        <span className="text-xs text-muted">· {shortChain(d.chain_id)}</span>
                      </span>
                    </td>
                    <td className="px-5 py-3 text-right">
                      <MoneyText amount={d.amount} decimals={dec(d.asset_id)} sign className="text-pos" />
                    </td>
                    <td className="px-5 py-3">
                      <StatusPill
                        status={d.status}
                        label={d.status === "seen" ? `pending ${d.confirmations}` : d.status}
                      />
                    </td>
                    <td className="px-5 py-3 text-right">
                      <a className="text-muted transition-colors hover:text-gold" href={d.explorer_url} target="_blank" rel="noreferrer" aria-label="Explorer">
                        <ExternalLink className="inline h-[15px] w-[15px]" />
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          )}
        </Card>

        {/* Withdrawals */}
        <Card className="overflow-hidden">
          <div className="border-b border-border/60 px-5 py-4 text-sm font-semibold text-ink-hi">Withdrawals</div>
          {withdrawals.isLoading ? (
            <div className="space-y-2 p-5">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : (withdrawals.data?.items ?? []).length === 0 ? (
            <p className="p-8 text-center text-sm text-muted">No withdrawals yet.</p>
          ) : (
            <div className="overflow-x-auto"><table className="w-full min-w-[34rem] text-sm">
              <thead className="text-[11px] uppercase tracking-wider text-muted">
                <tr className="border-b border-border/60">
                  <th className="px-5 py-2.5 text-left font-semibold">Asset</th>
                  <th className="px-5 py-2.5 text-right font-semibold">Amount</th>
                  <th className="px-5 py-2.5 text-left font-semibold">To</th>
                  <th className="px-5 py-2.5 text-left font-semibold">Status</th>
                  <th className="px-5 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {(withdrawals.data?.items ?? []).map((w) => (
                  <tr key={w.id} className="transition-colors hover:bg-surface2/40">
                    <td className="px-5 py-3">
                      <span className="inline-flex items-center gap-2">
                        <NetworkIcon chainId={w.chain_id} className="h-4 w-4" />
                        {sym(w.asset_id)}{" "}
                        <span className="text-xs text-muted">· {shortChain(w.chain_id)}</span>
                      </span>
                    </td>
                    <td className="px-5 py-3 text-right">
                      <MoneyText amount={w.amount} decimals={dec(w.asset_id)} className="text-neg" />
                    </td>
                    <td className="num px-5 py-3 font-mono text-xs text-muted">
                      {w.to_address.slice(0, 8)}…{w.to_address.slice(-4)}
                    </td>
                    <td className="px-5 py-3">
                      <StatusPill status={w.status} />
                    </td>
                    <td className="px-5 py-3 text-right">
                      {w.explorer_url ? (
                        <a className="text-muted transition-colors hover:text-gold" href={w.explorer_url} target="_blank" rel="noreferrer" aria-label="Explorer">
                          <ExternalLink className="inline h-[15px] w-[15px]" />
                        </a>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          )}
        </Card>

        {/* Collectible mints */}
        <Card className="overflow-hidden">
          <div className="border-b border-border/60 px-5 py-4 text-sm font-semibold text-ink-hi">Collectibles</div>
          {mints.isLoading ? (
            <div className="space-y-2 p-5">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : (mints.data ?? []).length === 0 ? (
            <p className="p-8 text-center text-sm text-muted">No collectible mints yet.</p>
          ) : (
            <div className="overflow-x-auto"><table className="w-full min-w-[34rem] text-sm">
              <thead className="text-[11px] uppercase tracking-wider text-muted">
                <tr className="border-b border-border/60">
                  <th className="px-5 py-2.5 text-left font-semibold">Token</th>
                  <th className="px-5 py-2.5 text-left font-semibold">Chain</th>
                  <th className="px-5 py-2.5 text-left font-semibold">Status</th>
                  <th className="px-5 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {(mints.data ?? []).map((m) => (
                  <tr key={m.id} className="transition-colors hover:bg-surface2/40">
                    <td className="px-5 py-3">
                      {m.token_id ? `Kasa Collectible #${m.token_id}` : "Kasa Collectible"}
                    </td>
                    <td className="px-5 py-3 text-xs text-muted">
                      <span className="inline-flex items-center gap-2">
                        <NetworkIcon chainId={m.chain_id} className="h-4 w-4" />
                        {shortChain(m.chain_id)}
                      </span>
                    </td>
                    <td className="px-5 py-3">
                      <StatusPill status={m.status} />
                    </td>
                    <td className="px-5 py-3 text-right">
                      {m.explorer_url ? (
                        <a className="text-muted transition-colors hover:text-gold" href={m.explorer_url} target="_blank" rel="noreferrer" aria-label="Explorer">
                          <ExternalLink className="inline h-[15px] w-[15px]" />
                        </a>
                      ) : null}
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

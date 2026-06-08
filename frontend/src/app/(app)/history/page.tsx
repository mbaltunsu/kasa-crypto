"use client";

import { ExternalLink } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Card } from "@/components/ui/Card";
import { MoneyText } from "@/components/ui/MoneyText";
import { StatusPill } from "@/components/ui/StatusPill";
import { Skeleton } from "@/components/ui/Skeleton";
import { shortChain } from "@/lib/assets";
import { useAssetMap, useDeposits, useWithdrawals } from "@/api/queries";

export default function HistoryPage() {
  const deposits = useDeposits();
  const withdrawals = useWithdrawals();
  const { map: assets } = useAssetMap();
  const dec = (id: string) => assets.get(id)?.decimals ?? 18;
  const sym = (id: string, fallback?: string) => assets.get(id)?.symbol ?? fallback ?? "—";

  return (
    <>
      <TopBar title="History" />
      <main className="max-w-5xl space-y-6 p-5 sm:p-7">
        {/* Deposits */}
        <Card className="overflow-hidden">
          <div className="border-b border-border px-5 py-4 text-sm font-semibold">Deposits</div>
          {deposits.isLoading ? (
            <div className="space-y-2 p-5">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : (deposits.data?.items ?? []).length === 0 ? (
            <p className="p-8 text-center text-sm text-muted">No deposits yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-xs text-muted">
                <tr className="border-b border-border">
                  <th className="px-5 py-2.5 text-left font-medium">Asset</th>
                  <th className="px-5 py-2.5 text-right font-medium">Amount</th>
                  <th className="px-5 py-2.5 text-left font-medium">Status</th>
                  <th className="px-5 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {(deposits.data?.items ?? []).map((d) => (
                  <tr key={d.id} className="hover:bg-surface2/50">
                    <td className="px-5 py-3">
                      {d.symbol} <span className="text-xs text-muted">· {shortChain(d.chain_id)}</span>
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
                      <a className="text-muted hover:text-gold" href={d.explorer_url} target="_blank" rel="noreferrer" aria-label="Explorer">
                        <ExternalLink className="inline h-[15px] w-[15px]" />
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        {/* Withdrawals */}
        <Card className="overflow-hidden">
          <div className="border-b border-border px-5 py-4 text-sm font-semibold">Withdrawals</div>
          {withdrawals.isLoading ? (
            <div className="space-y-2 p-5">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : (withdrawals.data?.items ?? []).length === 0 ? (
            <p className="p-8 text-center text-sm text-muted">No withdrawals yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-xs text-muted">
                <tr className="border-b border-border">
                  <th className="px-5 py-2.5 text-left font-medium">Asset</th>
                  <th className="px-5 py-2.5 text-right font-medium">Amount</th>
                  <th className="px-5 py-2.5 text-left font-medium">To</th>
                  <th className="px-5 py-2.5 text-left font-medium">Status</th>
                  <th className="px-5 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {(withdrawals.data?.items ?? []).map((w) => (
                  <tr key={w.id} className="hover:bg-surface2/50">
                    <td className="px-5 py-3">
                      {sym(w.asset_id)} <span className="text-xs text-muted">· {shortChain(w.chain_id)}</span>
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
                        <a className="text-muted hover:text-gold" href={w.explorer_url} target="_blank" rel="noreferrer" aria-label="Explorer">
                          <ExternalLink className="inline h-[15px] w-[15px]" />
                        </a>
                      ) : null}
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

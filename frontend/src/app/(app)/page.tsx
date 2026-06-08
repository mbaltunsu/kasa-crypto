"use client";

import Link from "next/link";
import { ArrowDownToLine, ArrowRightLeft, ArrowUpFromLine, Inbox } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { MoneyText } from "@/components/ui/MoneyText";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/cn";
import { shortChain } from "@/lib/assets";
import { useAssetMap, useBalances, useTransactions } from "@/api/queries";

const CHIP: Record<string, string> = {
  ETH: "bg-[#627EEA]/15 text-[#8AA0F2]",
  AVAX: "bg-[#E84142]/15 text-[#F87171]",
  DEMO: "bg-tech/15 text-tech",
};

const KIND_TONE: Record<string, string> = {
  deposit: "text-pos",
  transfer_in: "text-pos",
  withdrawal: "text-neg",
  transfer_out: "text-neg",
  fee: "text-muted",
  reversal: "text-gold",
  adjustment: "text-muted",
};

export default function DashboardPage() {
  const balances = useBalances();
  const txns = useTransactions();
  const { map: assets } = useAssetMap();
  const decimalsOf = (assetId: string) => assets.get(assetId)?.decimals ?? 18;

  return (
    <>
      <TopBar title="Dashboard" />
      <main className="max-w-6xl space-y-6 p-5 sm:p-7">
        <div className="flex flex-wrap gap-2.5">
          <Link href="/deposit">
            <Button>
              <ArrowDownToLine className="h-4 w-4" /> Deposit
            </Button>
          </Link>
          <Link href="/withdraw">
            <Button variant="secondary">
              <ArrowUpFromLine className="h-4 w-4" /> Withdraw
            </Button>
          </Link>
          <Link href="/transfer">
            <Button variant="secondary">
              <ArrowRightLeft className="h-4 w-4" /> Transfer
            </Button>
          </Link>
        </div>

        {/* Balances */}
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Balances</h2>
          {balances.isLoading ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {[0, 1, 2].map((i) => (
                <Card key={i} className="space-y-3 p-5">
                  <Skeleton className="h-9 w-9 rounded-full" />
                  <Skeleton className="h-7 w-32" />
                  <Skeleton className="h-3 w-20" />
                </Card>
              ))}
            </div>
          ) : (balances.data ?? []).length === 0 ? (
            <Card className="flex flex-col items-center gap-3 p-10 text-center">
              <Inbox className="h-8 w-8 text-muted" />
              <p className="text-sm text-muted">No balances yet.</p>
              <Link href="/deposit">
                <Button>Make your first deposit</Button>
              </Link>
            </Card>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {(balances.data ?? []).map((b) => (
                <Card
                  key={b.asset_id}
                  className="p-5 transition hover:ring-1 hover:ring-gold/30"
                >
                  <div className="flex items-center gap-3">
                    <span
                      className={cn(
                        "grid h-9 w-9 place-items-center rounded-full text-[10px] font-bold",
                        CHIP[b.symbol] ?? "bg-surface2 text-muted",
                      )}
                    >
                      {b.symbol}
                    </span>
                    <div>
                      <div className="font-semibold leading-tight">{b.symbol}</div>
                      <div className="text-[11px] text-muted">{shortChain(b.chain_id)}</div>
                    </div>
                  </div>
                  <MoneyText
                    amount={b.available}
                    decimals={decimalsOf(b.asset_id)}
                    className="mt-4 block text-2xl font-semibold"
                  />
                  {b.pending !== "0" ? (
                    <div className="num mt-2 flex items-center gap-1.5 text-xs text-gold">
                      <span className="h-1.5 w-1.5 rounded-full bg-gold" />
                      <MoneyText amount={b.pending} decimals={decimalsOf(b.asset_id)} /> pending
                    </div>
                  ) : (
                    <div className="num mt-2 text-xs text-muted">no pending</div>
                  )}
                </Card>
              ))}
            </div>
          )}
        </section>

        {/* Recent activity */}
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <h2 className="text-sm font-semibold">Recent activity</h2>
            <Link href="/history" className="text-xs text-muted hover:text-ink">
              Full history →
            </Link>
          </div>
          {txns.isLoading ? (
            <div className="space-y-2 p-5">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-8 w-full" />
              ))}
            </div>
          ) : (txns.data?.items ?? []).length === 0 ? (
            <p className="p-8 text-center text-sm text-muted">No activity yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-xs text-muted">
                <tr className="border-b border-border">
                  <th className="px-5 py-2.5 text-left font-medium">Type</th>
                  <th className="px-5 py-2.5 text-left font-medium">Asset</th>
                  <th className="px-5 py-2.5 text-right font-medium">Amount</th>
                  <th className="px-5 py-2.5 text-right font-medium">Ref</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {(txns.data?.items ?? []).slice(0, 8).map((t) => {
                  const negative = t.amount.startsWith("-");
                  return (
                    <tr key={t.id} className="hover:bg-surface2/50">
                      <td className="px-5 py-3">
                        <span className={cn("capitalize", KIND_TONE[t.type] ?? "text-ink")}>
                          {t.type.replace("_", " ")}
                        </span>
                      </td>
                      <td className="px-5 py-3">{t.symbol}</td>
                      <td className="px-5 py-3 text-right">
                        <MoneyText
                          amount={t.amount}
                          decimals={decimalsOf(t.asset_id)}
                          sign
                          className={negative ? "text-neg" : "text-pos"}
                        />
                      </td>
                      <td className="num px-5 py-3 text-right text-xs text-muted">{t.ref}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </Card>
      </main>
    </>
  );
}

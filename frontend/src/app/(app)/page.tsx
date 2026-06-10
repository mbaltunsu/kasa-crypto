"use client";

import Link from "next/link";
import { ArrowDownToLine, ArrowRightLeft, ArrowUpFromLine, Inbox } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { MoneyText } from "@/components/ui/MoneyText";
import { AssetIcon, NetworkIcon } from "@/components/ui/NetworkIcon";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/cn";
import { shortChain } from "@/lib/assets";
import { useAssetMap, useBalances, useTransactions } from "@/api/queries";

const KIND_TONE: Record<string, string> = {
  deposit: "text-pos",
  transfer_in: "text-pos",
  withdrawal: "text-neg",
  transfer_out: "text-neg",
  fee: "text-muted",
  reversal: "text-warn",
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
      <main className="relative max-w-6xl animate-fade-up space-y-7 p-5 sm:p-7">
        {/* Faint warm wash behind the balances — a hint of brand, not an aura. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-80 bg-gradient-hero"
        />

        <div className="relative flex flex-wrap gap-2.5">
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
        <section className="relative">
          <h2 className="mb-3 text-xs font-bold uppercase tracking-[0.14em] text-muted">
            Balances
          </h2>
          {balances.isLoading ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {[0, 1, 2].map((i) => (
                <Card key={i} className="space-y-3 p-5">
                  <Skeleton className="h-10 w-10 rounded-full" />
                  <Skeleton className="h-8 w-36" />
                  <Skeleton className="h-3 w-20" />
                </Card>
              ))}
            </div>
          ) : (balances.data ?? []).length === 0 ? (
            <Card className="flex flex-col items-center gap-4 p-12 text-center">
              <span className="grid h-12 w-12 place-items-center rounded-2xl bg-gold/10 ring-1 ring-gold/30">
                <Inbox className="h-6 w-6 text-gold" />
              </span>
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
                  className="group relative overflow-hidden p-5 transition-all duration-200 hover:-translate-y-0.5 hover:border-border hover:shadow-pop"
                >
                  {/* Network watermark — oversized chain mark fading out of the corner. */}
                  <div
                    aria-hidden
                    className="pointer-events-none absolute -bottom-7 -right-5 h-28 w-28 opacity-[0.05] transition-opacity duration-200 group-hover:opacity-[0.09]"
                  >
                    <NetworkIcon chainId={b.chain_id} className="h-full w-full" />
                  </div>
                  <div className="flex items-center gap-3">
                    <AssetIcon symbol={b.symbol} chainId={b.chain_id} className="h-10 w-10" />
                    <div>
                      <div className="font-semibold leading-tight text-ink-hi">{b.symbol}</div>
                      <div className="text-[11px] text-muted">{shortChain(b.chain_id)}</div>
                    </div>
                  </div>
                  <MoneyText
                    amount={b.available}
                    decimals={decimalsOf(b.asset_id)}
                    className="mt-4 block text-3xl font-semibold tracking-tight text-ink-hi"
                  />
                  {b.pending !== "0" ? (
                    <div className="num mt-2.5 flex items-center gap-1.5 text-xs font-medium text-warn">
                      <span className="h-1.5 w-1.5 rounded-full bg-warn" />
                      <MoneyText amount={b.pending} decimals={decimalsOf(b.asset_id)} /> pending
                    </div>
                  ) : (
                    <div className="num mt-2.5 text-xs text-muted/70">no pending</div>
                  )}
                </Card>
              ))}
            </div>
          )}
        </section>

        {/* Recent activity */}
        <Card className="relative overflow-hidden">
          <div className="flex items-center justify-between border-b border-border/60 px-5 py-4">
            <h2 className="text-sm font-semibold text-ink-hi">Recent activity</h2>
            <Link
              href="/history"
              className="text-xs font-medium text-gold transition-colors hover:text-gold-hi"
            >
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
            <div className="overflow-x-auto"><table className="w-full min-w-[34rem] text-sm">
              <thead className="text-[11px] uppercase tracking-wider text-muted">
                <tr className="border-b border-border/60">
                  <th className="px-5 py-2.5 text-left font-semibold">Type</th>
                  <th className="px-5 py-2.5 text-left font-semibold">Asset</th>
                  <th className="px-5 py-2.5 text-right font-semibold">Amount</th>
                  <th className="px-5 py-2.5 text-right font-semibold">Ref</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {(txns.data?.items ?? []).slice(0, 8).map((t) => {
                  const negative = t.amount.startsWith("-");
                  return (
                    <tr key={t.id} className="transition-colors hover:bg-surface2/40">
                      <td className="px-5 py-3">
                        <span
                          className={cn("font-medium capitalize", KIND_TONE[t.type] ?? "text-ink")}
                        >
                          {t.type.replace("_", " ")}
                        </span>
                      </td>
                      <td className="px-5 py-3 font-medium text-ink">{t.symbol}</td>
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
            </table></div>
          )}
        </Card>
      </main>
    </>
  );
}

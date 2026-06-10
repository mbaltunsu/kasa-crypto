"use client";

import { useState } from "react";
import { Check, Copy, Droplets, ExternalLink, Wallet } from "lucide-react";
import { explorerTxUrl, parseAmount } from "@kasa/shared";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Field";
import { NetworkIcon } from "@/components/ui/NetworkIcon";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/ui/Skeleton";
import { amountCapError, maxAmountLabel, shortChain } from "@/lib/assets";
import { useAssets, useDepositAddresses, useFaucet } from "@/api/queries";

function CopyAddress({ address }: { address: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard.writeText(address);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className="flex items-center gap-2 rounded-lg p-1.5 text-muted transition-colors hover:bg-gold/10 hover:text-gold"
      aria-label="Copy address"
    >
      {copied ? <Check className="h-4 w-4 text-pos" /> : <Copy className="h-4 w-4" />}
    </button>
  );
}

export default function DepositPage() {
  const addrs = useDepositAddresses();
  const assetsQ = useAssets();
  const faucet = useFaucet();
  const assets = assetsQ.data ?? [];
  const [assetId, setAssetId] = useState("");
  const [amount, setAmount] = useState("1");
  const [err, setErr] = useState<string | null>(null);
  const selected = assets.find((a) => a.id === assetId) ?? assets[0];

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (!selected) return;
    let base: bigint;
    try {
      base = parseAmount(selected, amount);
    } catch {
      setErr("Invalid amount.");
      return;
    }
    if (base <= 0n) return setErr("Amount must be positive.");
    const capErr = amountCapError(selected, base);
    if (capErr) return setErr(capErr);
    faucet.mutate({ asset_id: selected.id, amount: base.toString() });
  }

  return (
    <>
      <TopBar title="Deposit" />
      <main className="max-w-3xl animate-fade-up space-y-6 p-5 sm:p-7">
        <Card className="p-6">
          <div className="flex items-center gap-2.5">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-gold/10 ring-1 ring-gold/30">
              <Wallet className="h-4 w-4 text-gold" aria-hidden />
            </span>
            <h2 className="text-sm font-semibold text-ink-hi">Your deposit addresses</h2>
          </div>
          <p className="mt-2 text-xs text-muted">
            One EVM address, reused across chains. Send testnet funds here, or use the faucet below.
          </p>
          <div className="mt-4 space-y-2">
            {addrs.isLoading ? (
              <Skeleton className="h-12 w-full" />
            ) : (
              (addrs.data ?? []).map((a) => (
                <div
                  key={a.chain_id}
                  className="flex items-center gap-3 rounded-xl border border-border/70 bg-bg/50 px-4 py-3 transition-colors hover:border-border"
                >
                  <span className="flex w-24 shrink-0 items-center gap-2 text-xs font-semibold text-muted">
                    <NetworkIcon chainId={a.chain_id} className="h-4 w-4" />
                    {shortChain(a.chain_id)}
                  </span>
                  <span className="num truncate font-mono text-xs text-ink">{a.address}</span>
                  <span className="ml-auto">
                    <CopyAddress address={a.address} />
                  </span>
                </div>
              ))
            )}
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center gap-2.5">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-aqua/10 ring-1 ring-aqua/30">
              <Droplets className="h-4 w-4 text-aqua" aria-hidden />
            </span>
            <h2 className="text-sm font-semibold text-ink-hi">Simulate a deposit (faucet)</h2>
          </div>
          <p className="mt-2 text-xs text-muted">
            Sends a real testnet transaction from a pre-funded key to your address — no funds needed.
          </p>
          <form className="mt-4 space-y-2.5" onSubmit={submit}>
            {/* Grid holds label+control only, so Asset / Amount / Send align on a single row;
                the amount hint/error renders full-width below (keeping the controls aligned). */}
            <div className="grid gap-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
              <Field label="Asset" htmlFor="asset">
                <Select
                  id="asset"
                  value={selected?.id ?? ""}
                  onChange={(e) => {
                    setAssetId(e.target.value);
                    setErr(null);
                  }}
                >
                  {assets.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.symbol} · {shortChain(a.chain_id)}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Amount" htmlFor="amount">
                <Input
                  id="amount"
                  inputMode="decimal"
                  value={amount}
                  onChange={(e) => {
                    setAmount(e.target.value);
                    setErr(null);
                  }}
                />
              </Field>
              <Button type="submit" disabled={faucet.isPending || !selected}>
                {faucet.isPending ? "Sending…" : "Send"}
              </Button>
            </div>
            {err ? (
              <p role="alert" className="text-xs text-neg">
                {err}
              </p>
            ) : selected && maxAmountLabel(selected) ? (
              <p className="num text-xs text-muted/70">max {maxAmountLabel(selected)}</p>
            ) : null}
          </form>
          {faucet.isSuccess ? (
            <p className="mt-3 flex items-center gap-1.5 text-xs text-pos">
              <span>Sent · status {faucet.data.status}</span>
              {selected ? (
                <a
                  className="inline-flex items-center gap-1 underline-offset-2 hover:text-gold hover:underline"
                  href={explorerTxUrl(selected.chain_id, faucet.data.tx_hash)}
                  target="_blank"
                  rel="noreferrer"
                >
                  view tx <ExternalLink className="h-3 w-3" />
                </a>
              ) : null}
            </p>
          ) : faucet.isError ? (
            <p className="mt-3 text-xs text-neg">Faucet request failed.</p>
          ) : null}
        </Card>
      </main>
    </>
  );
}

"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { parseAmount } from "@kasa/shared";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/ui/Skeleton";
import { shortChain } from "@/lib/assets";
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
      className="flex items-center gap-2 text-muted hover:text-gold"
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
  const selected = assets.find((a) => a.id === assetId) ?? assets[0];

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!selected) return;
    let base: string;
    try {
      base = parseAmount(selected, amount).toString();
    } catch {
      return;
    }
    faucet.mutate({ asset_id: selected.id, amount: base });
  }

  return (
    <>
      <TopBar title="Deposit" />
      <main className="max-w-3xl space-y-6 p-5 sm:p-7">
        <Card className="p-6">
          <h2 className="text-sm font-semibold">Your deposit addresses</h2>
          <p className="mt-1 text-xs text-muted">
            One EVM address, reused across chains. Send testnet funds here, or use the faucet below.
          </p>
          <div className="mt-4 space-y-2">
            {addrs.isLoading ? (
              <Skeleton className="h-12 w-full" />
            ) : (
              (addrs.data ?? []).map((a) => (
                <div
                  key={a.chain_id}
                  className="flex items-center gap-3 rounded-lg border border-border bg-surface2 px-4 py-3"
                >
                  <span className="w-20 shrink-0 text-xs text-muted">{shortChain(a.chain_id)}</span>
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
          <h2 className="text-sm font-semibold">Simulate a deposit (faucet)</h2>
          <p className="mt-1 text-xs text-muted">
            Sends a real testnet transaction from a pre-funded key to your address — no funds needed.
          </p>
          <form className="mt-4 grid gap-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end" onSubmit={submit}>
            <Field label="Asset" htmlFor="asset">
              <Select id="asset" value={selected?.id ?? ""} onChange={(e) => setAssetId(e.target.value)}>
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
                onChange={(e) => setAmount(e.target.value)}
              />
            </Field>
            <Button type="submit" disabled={faucet.isPending || !selected}>
              {faucet.isPending ? "Sending…" : "Send"}
            </Button>
          </form>
          {faucet.isSuccess ? (
            <p className="mt-3 text-xs text-pos">
              Sent · status {faucet.data.status} · tx {faucet.data.tx_hash.slice(0, 12)}…
            </p>
          ) : faucet.isError ? (
            <p className="mt-3 text-xs text-neg">Faucet request failed.</p>
          ) : null}
        </Card>
      </main>
    </>
  );
}

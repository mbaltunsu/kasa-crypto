"use client";

import { useState } from "react";
import { formatAmount, parseAmount } from "@kasa/shared";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import { shortChain } from "@/lib/assets";
import { useAssets, useBalances, useTransfer } from "@/api/queries";

export default function TransferPage() {
  const assets = useAssets().data ?? [];
  const balances = useBalances().data ?? [];
  const transfer = useTransfer();
  const [assetId, setAssetId] = useState("");
  const [toEmail, setToEmail] = useState("");
  const [amount, setAmount] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const selected = assets.find((a) => a.id === assetId) ?? assets[0];
  const available = balances.find((b) => b.asset_id === selected?.id)?.available ?? "0";

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
    if (base > BigInt(available)) return setErr("Amount exceeds available balance.");
    transfer.mutate({ asset_id: selected.id, to_email: toEmail, amount: base.toString() });
  }

  return (
    <>
      <TopBar title="Transfer" />
      <main className="max-w-lg space-y-6 p-5 sm:p-7">
        <Card className="p-6">
          <p className="mb-4 text-xs text-muted">
            Instant internal transfer to another Kasa user by email — off-chain, no gas.
          </p>
          <form className="space-y-4" onSubmit={submit}>
            <Field label="Asset" htmlFor="asset">
              <Select id="asset" value={selected?.id ?? ""} onChange={(e) => setAssetId(e.target.value)}>
                {assets.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.symbol} · {shortChain(a.chain_id)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Recipient email" htmlFor="to">
              <Input
                id="to"
                type="email"
                placeholder="friend@example.com"
                value={toEmail}
                onChange={(e) => setToEmail(e.target.value)}
              />
            </Field>
            <Field
              label="Amount"
              htmlFor="amount"
              hint={
                selected ? (
                  <span className="num">
                    available {formatAmount(selected, available)} {selected.symbol}
                  </span>
                ) : undefined
              }
              error={err ?? undefined}
            >
              <Input
                id="amount"
                inputMode="decimal"
                placeholder="0.0"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </Field>
            <Button type="submit" className="w-full" disabled={transfer.isPending || !selected}>
              {transfer.isPending ? "Sending…" : "Send transfer"}
            </Button>
          </form>
          {transfer.isSuccess ? <p className="mt-3 text-xs text-pos">Transfer complete.</p> : null}
        </Card>
      </main>
    </>
  );
}

"use client";

import { useState } from "react";
import { formatAmount, parseAmount } from "@kasa/shared";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import { UserSelect } from "@/components/ui/UserSelect";
import { amountCapError, maxAmountLabel, shortChain } from "@/lib/assets";
import { useAssets, useBalances, useMe, useTransfer } from "@/api/queries";

export default function TransferPage() {
  const assets = useAssets().data ?? [];
  const balances = useBalances().data ?? [];
  const me = useMe();
  const transfer = useTransfer();
  const [assetId, setAssetId] = useState("");
  const [toEmail, setToEmail] = useState("");
  const [amount, setAmount] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const selected = assets.find((a) => a.id === assetId) ?? assets[0];
  const availOf = (id: string) => balances.find((b) => b.asset_id === id)?.available ?? "0";
  const available = availOf(selected?.id ?? "");

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
    const capErr = amountCapError(selected, base);
    if (capErr) return setErr(capErr);
    transfer.mutate({ asset_id: selected.id, to_email: toEmail, amount: base.toString() });
  }

  return (
    <>
      <TopBar title="Transfer" />
      <main className="max-w-lg animate-fade-up space-y-6 p-5 sm:p-7">
        <Card className="p-6">
          <p className="mb-4 text-xs text-muted">
            Instant internal transfer to another Kasa user by email — off-chain, no gas.
          </p>
          <form className="space-y-4" onSubmit={submit}>
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
                    {a.symbol} · {shortChain(a.chain_id)} — {formatAmount(a, availOf(a.id))} avail
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Recipient" htmlFor="to">
              <UserSelect
                id="to"
                value={toEmail}
                excludeEmail={me.data?.email}
                placeholder="Select a recipient…"
                onChange={(email) => {
                  setToEmail(email);
                  setErr(null);
                }}
              />
            </Field>
            <Field
              label="Amount"
              htmlFor="amount"
              hint={
                selected ? (
                  <span className="num">
                    available {formatAmount(selected, available)} {selected.symbol}
                    {maxAmountLabel(selected) ? ` · max ${maxAmountLabel(selected)}` : ""}
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
                onChange={(e) => {
                  setAmount(e.target.value);
                  setErr(null);
                }}
              />
            </Field>
            <Button type="submit" className="w-full" disabled={transfer.isPending || !selected}>
              {transfer.isPending ? "Sending…" : "Send transfer"}
            </Button>
          </form>
          {transfer.isSuccess ? (
            <p className="mt-3 text-xs font-medium text-pos">Transfer complete.</p>
          ) : null}
        </Card>
      </main>
    </>
  );
}

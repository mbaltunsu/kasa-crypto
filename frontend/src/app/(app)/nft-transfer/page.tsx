"use client";

import { useEffect, useMemo, useState } from "react";
import { Images, Inbox } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Field";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/cn";
import { shortChain } from "@/lib/assets";
import { useMyNfts, useNftTransfer } from "@/api/queries";

export default function NftTransferPage() {
  const nfts = useMyNfts();
  const transfer = useNftTransfer();
  const [selectedId, setSelectedId] = useState("");
  const [toEmail, setToEmail] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const owned = useMemo(() => nfts.data ?? [], [nfts.data]);
  const selected = owned.find((n) => n.id === selectedId) ?? owned[0];

  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("nft_id");
    if (requested) setSelectedId(requested);
  }, []);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (!selected) {
      setErr("Select a collectible.");
      return;
    }
    transfer.mutate({ nft_id: selected.id, to_email: toEmail });
  }

  return (
    <>
      <TopBar title="NFT Transfer" />
      <main className="max-w-4xl space-y-6 p-5 sm:p-7">
        <Card className="p-6">
          <p className="mb-4 text-xs text-muted">
            Instant internal collectible transfer to another Kasa user by email — off-chain, no gas.
          </p>
          <form className="space-y-5" onSubmit={submit}>
            <Field label="Collectible" htmlFor="nft" error={err ?? undefined}>
              {nfts.isLoading ? (
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {[0, 1, 2].map((i) => (
                    <Skeleton key={i} className="h-52 w-full rounded-2xl" />
                  ))}
                </div>
              ) : nfts.isError ? (
                <div className="flex flex-col items-center gap-3 rounded-2xl border border-border bg-surface2 p-10 text-center">
                  <Images className="h-8 w-8 text-muted" />
                  <p className="text-sm text-muted">Could not load collectibles.</p>
                </div>
              ) : owned.length === 0 ? (
                <div className="flex flex-col items-center gap-3 rounded-2xl border border-border bg-surface2 p-10 text-center">
                  <Inbox className="h-8 w-8 text-muted" />
                  <p className="text-sm text-muted">No collectibles available to send.</p>
                </div>
              ) : (
                <div id="nft" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {owned.map((n) => {
                    const active = selected?.id === n.id;
                    return (
                      <button
                        key={n.id}
                        type="button"
                        onClick={() => setSelectedId(n.id)}
                        className={cn(
                          "overflow-hidden rounded-2xl border border-border bg-surface text-left transition",
                          "hover:ring-1 hover:ring-gold/30",
                          active && "border-gold/50 ring-1 ring-gold/40",
                        )}
                      >
                        <img
                          src={n.image}
                          alt={`Kasa Collectible #${n.token_id}`}
                          className="h-32 w-full bg-surface2 object-cover"
                        />
                        <span className="block space-y-1 p-4">
                          <span className="block text-sm font-semibold">
                            Kasa Collectible #{n.token_id}
                          </span>
                          <span className="block text-[11px] text-muted">{shortChain(n.chain_id)}</span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
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
            <Button type="submit" className="w-full" disabled={transfer.isPending || !selected}>
              {transfer.isPending ? "Sending..." : "Send collectible"}
            </Button>
          </form>
          {transfer.isSuccess ? <p className="mt-3 text-xs text-pos">Collectible sent.</p> : null}
        </Card>
      </main>
    </>
  );
}

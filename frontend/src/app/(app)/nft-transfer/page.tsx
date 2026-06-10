"use client";

import { useEffect, useMemo, useState } from "react";
import { Images, Inbox } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field } from "@/components/ui/Field";
import { NetworkIcon } from "@/components/ui/NetworkIcon";
import { Skeleton } from "@/components/ui/Skeleton";
import { UserSelect } from "@/components/ui/UserSelect";
import { cn } from "@/lib/cn";
import { shortChain } from "@/lib/assets";
import { useMe, useMyNfts, useNftTransfer } from "@/api/queries";

export default function NftTransferPage() {
  const nfts = useMyNfts();
  const me = useMe();
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
      <main className="max-w-4xl animate-fade-up space-y-6 p-5 sm:p-7">
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
                <div className="flex flex-col items-center gap-4 rounded-2xl border border-border/70 bg-bg/50 p-10 text-center">
                  <span className="grid h-12 w-12 place-items-center rounded-2xl bg-neg/10 ring-1 ring-neg/30">
                    <Images className="h-6 w-6 text-neg" />
                  </span>
                  <p className="text-sm text-muted">Could not load collectibles.</p>
                </div>
              ) : owned.length === 0 ? (
                <div className="flex flex-col items-center gap-4 rounded-2xl border border-border/70 bg-bg/50 p-10 text-center">
                  <span className="grid h-12 w-12 place-items-center rounded-2xl bg-tech/10 ring-1 ring-tech/30">
                    <Inbox className="h-6 w-6 text-tech" />
                  </span>
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
                          "group overflow-hidden rounded-2xl border bg-surface text-left shadow-card",
                          "transition-all duration-200 hover:-translate-y-0.5 hover:shadow-pop",
                          active
                            ? "border-gold/50 ring-1 ring-gold/30"
                            : "border-border/60 hover:border-border",
                        )}
                      >
                        <span className="relative block overflow-hidden">
                          <img
                            src={n.image}
                            alt={`Kasa Collectible #${n.token_id}`}
                            className="h-32 w-full bg-surface2 object-cover transition-transform duration-300 group-hover:scale-[1.02]"
                          />
                          <span
                            aria-hidden
                            className="pointer-events-none absolute inset-0 bg-gradient-to-t from-surface via-transparent to-transparent"
                          />
                        </span>
                        <span className="block space-y-1 p-4">
                          <span
                            className={cn(
                              "block text-sm font-semibold",
                              active ? "text-gold" : "text-ink-hi",
                            )}
                          >
                            Kasa Collectible #{n.token_id}
                          </span>
                          <span className="flex items-center gap-1.5 text-[11px] text-muted">
                            <NetworkIcon chainId={n.chain_id} className="h-3.5 w-3.5" />
                            {shortChain(n.chain_id)}
                          </span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
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
            <Button type="submit" className="w-full" disabled={transfer.isPending || !selected}>
              {transfer.isPending ? "Sending..." : "Send collectible"}
            </Button>
          </form>
          {transfer.isSuccess ? (
            <p className="mt-3 text-xs font-medium text-pos">Collectible sent.</p>
          ) : null}
        </Card>
      </main>
    </>
  );
}

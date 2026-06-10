"use client";

import Link from "next/link";
import { useState } from "react";
import { ExternalLink, Images } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Field";
import { NetworkIcon } from "@/components/ui/NetworkIcon";
import { Skeleton } from "@/components/ui/Skeleton";
import { shortChain } from "@/lib/assets";
import { useNftWithdrawal, useNfts } from "@/api/queries";
import type { components } from "@/api/client";

type Nft = components["schemas"]["NftResponse"];

function NftCard({ nft }: { nft: Nft }) {
  const withdrawal = useNftWithdrawal();
  const [toAddress, setToAddress] = useState("");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    withdrawal.mutate({ nft_id: nft.id, to_address: toAddress });
  }

  return (
    <Card className="group overflow-hidden transition-all duration-200 hover:-translate-y-0.5 hover:border-border hover:shadow-pop">
      <div className="relative overflow-hidden">
        <img
          src={nft.image}
          alt={`Kasa Collectible #${nft.token_id}`}
          className="h-32 w-full bg-surface2 object-cover transition-transform duration-300 group-hover:scale-[1.02]"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-gradient-to-t from-surface via-transparent to-transparent"
        />
      </div>
      <div className="space-y-3 p-4">
        <div className="text-sm font-semibold text-ink-hi">Kasa Collectible #{nft.token_id}</div>
        <div className="flex items-center gap-1.5 text-[11px] text-muted">
          <NetworkIcon chainId={nft.chain_id} className="h-3.5 w-3.5" />
          {shortChain(nft.chain_id)}
        </div>
        <div className="flex items-center justify-between gap-3">
          <a
            href={nft.explorer_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-xs text-muted transition-colors hover:text-gold"
          >
            Explorer <ExternalLink className="h-3 w-3" />
          </a>
          <Link href={`/nft-transfer?nft_id=${encodeURIComponent(nft.id)}`}>
            <Button variant="secondary" className="px-3 py-1.5 text-xs">
              Send
            </Button>
          </Link>
        </div>
        <form className="space-y-2 border-t border-border/60 pt-3" onSubmit={submit}>
          <Input
            aria-label="Withdrawal address"
            placeholder="0x external address"
            value={toAddress}
            onChange={(e) => setToAddress(e.target.value)}
            className="py-2 text-xs"
          />
          <Button
            type="submit"
            variant="secondary"
            className="w-full px-3 py-2 text-xs"
            disabled={withdrawal.isPending || toAddress.length === 0}
          >
            {withdrawal.isPending ? "Withdrawing..." : "Withdraw"}
          </Button>
          {withdrawal.isSuccess ? (
            <p className="text-xs font-medium text-pos">Withdrawal requested.</p>
          ) : null}
        </form>
      </div>
    </Card>
  );
}

export default function NftsPage() {
  const nfts = useNfts();

  return (
    <>
      <TopBar title="Collectibles" />
      <main className="max-w-5xl animate-fade-up space-y-6 p-5 sm:p-7">
        {nfts.isLoading ? (
          <div className="grid gap-4 sm:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-40 w-full rounded-2xl" />
            ))}
          </div>
        ) : (nfts.data ?? []).length === 0 ? (
          <Card className="flex flex-col items-center gap-4 p-12 text-center">
            <span className="grid h-12 w-12 place-items-center rounded-2xl bg-tech/10 ring-1 ring-tech/30">
              <Images className="h-6 w-6 text-tech" />
            </span>
            <p className="text-sm text-muted">No collectibles yet. An admin can mint one to you.</p>
          </Card>
        ) : (
          <div className="grid gap-4 sm:grid-cols-3">
            {(nfts.data ?? []).map((n) => (
              <NftCard key={`${n.contract}-${n.token_id}`} nft={n} />
            ))}
          </div>
        )}
      </main>
    </>
  );
}

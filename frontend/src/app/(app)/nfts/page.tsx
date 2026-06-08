"use client";

import { ExternalLink, Images } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { shortChain } from "@/lib/assets";
import { useNfts } from "@/api/queries";

export default function NftsPage() {
  const nfts = useNfts();

  return (
    <>
      <TopBar title="Collectibles" />
      <main className="max-w-5xl space-y-6 p-5 sm:p-7">
        {nfts.isLoading ? (
          <div className="grid gap-4 sm:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-40 w-full rounded-2xl" />
            ))}
          </div>
        ) : (nfts.data ?? []).length === 0 ? (
          <Card className="flex flex-col items-center gap-3 p-12 text-center">
            <Images className="h-8 w-8 text-muted" />
            <p className="text-sm text-muted">No collectibles yet. An admin can mint one to you.</p>
          </Card>
        ) : (
          <div className="grid gap-4 sm:grid-cols-3">
            {(nfts.data ?? []).map((n) => (
              <Card key={`${n.contract}-${n.token_id}`} className="overflow-hidden">
                <div className="grid h-32 place-items-center bg-gradient-to-br from-tech/20 to-surface">
                  <Images className="h-10 w-10 text-tech" />
                </div>
                <div className="space-y-1 p-4">
                  <div className="text-sm font-semibold">Kasa Collectible #{n.token_id}</div>
                  <div className="text-[11px] text-muted">{shortChain(n.chain_id)}</div>
                  <a
                    href={n.explorer_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-muted hover:text-gold"
                  >
                    View on explorer <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              </Card>
            ))}
          </div>
        )}
      </main>
    </>
  );
}

"use client";

import { MobileNav } from "@/components/layout/MobileNav";
import { NetworkIcon } from "@/components/ui/NetworkIcon";

const CHAINS = [
  { id: 11155111, label: "Sepolia" },
  { id: 43113, label: "Fuji" },
];

export function TopBar({ title }: { title: string }) {
  return (
    <header className="sticky top-0 z-10 flex h-16 items-center gap-3 border-b border-border/60 bg-bg/70 px-5 backdrop-blur-xl sm:px-7">
      <MobileNav />
      <h1 className="truncate text-lg font-semibold tracking-tight text-ink-hi">{title}</h1>
      <div className="ml-auto flex items-center gap-2.5">
        {/* Display-only: both testnets are always watched; there's no single "active" chain to pick. */}
        <div
          className="hidden items-center gap-1 rounded-xl bg-surface/70 p-1 text-xs ring-1 ring-border/70 sm:flex"
          title="Both testnets are always watched — display only"
          aria-label="Supported networks (read-only)"
        >
          {CHAINS.map((c) => (
            <span
              key={c.id}
              className="flex cursor-default items-center gap-1.5 rounded-lg px-2.5 py-1 font-medium text-muted"
            >
              <NetworkIcon chainId={c.id} className="h-3.5 w-3.5" />
              {c.label}
            </span>
          ))}
        </div>
        <span className="flex items-center gap-2 rounded-xl bg-surface/70 px-2.5 py-1.5 text-xs font-medium text-pos/90 ring-1 ring-border/70">
          <span className="h-1.5 w-1.5 rounded-full bg-pos" aria-hidden />
          watcher live
        </span>
      </div>
    </header>
  );
}

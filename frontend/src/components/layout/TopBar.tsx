"use client";

import { useState } from "react";
import { cn } from "@/lib/cn";

const CHAINS = [
  { id: 11155111, label: "Sepolia", dot: "bg-tech" },
  { id: 43113, label: "Fuji", dot: "bg-neg" },
];

export function TopBar({ title }: { title: string }) {
  const [active, setActive] = useState(CHAINS[0]!.id);

  return (
    <header className="sticky top-0 z-10 flex h-16 items-center gap-3 border-b border-border bg-bg/80 px-5 backdrop-blur sm:px-7">
      <h1 className="text-lg font-semibold text-ink-hi">{title}</h1>
      <div className="ml-auto flex items-center gap-2.5">
        <div className="flex items-center gap-1 rounded-lg bg-surface p-1 text-xs ring-1 ring-border">
          {CHAINS.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => setActive(c.id)}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-2.5 py-1 transition-colors",
                active === c.id ? "bg-surface2 font-medium text-ink" : "text-muted hover:text-ink",
              )}
            >
              <span className={cn("h-1.5 w-1.5 rounded-full", c.dot)} />
              {c.label}
            </button>
          ))}
        </div>
        <span className="flex items-center gap-1.5 rounded-lg bg-surface px-2.5 py-1.5 text-xs text-muted ring-1 ring-border">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-pos" />
          watcher live
        </span>
      </div>
    </header>
  );
}

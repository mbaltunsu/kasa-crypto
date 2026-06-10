"use client";

import { useId } from "react";
import { cn } from "@/lib/cn";

/** The Kasa mark: a geometric K carved into a mint squircle, with a signal dot at the
 * mouth of the K — value flowing into the vault. Gradient id is namespaced via useId so
 * multiple instances (sidebar + drawer + login) can coexist on one page. */
export function KasaLogo({ className }: { className?: string }) {
  const id = useId();
  const gradient = `kasa-mark-${id}`;
  return (
    <svg viewBox="0 0 48 48" role="img" aria-label="Kasa" className={cn("shrink-0", className)}>
      <defs>
        <linearGradient id={gradient} x1="6" y1="4" x2="44" y2="46" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#3BCD9F" />
          <stop offset="1" stopColor="#178F6B" />
        </linearGradient>
      </defs>
      <rect width="48" height="48" rx="13.5" fill={`url(#${gradient})`} />
      <path
        d="M16 13.5v21"
        stroke="#0B0E13"
        strokeWidth="5"
        strokeLinecap="round"
        fill="none"
      />
      <path
        d="M32.5 13.5 23 24l9.5 10.5"
        stroke="#0B0E13"
        strokeWidth="5"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      <circle cx="35.5" cy="24" r="2.6" fill="#0B0E13" />
    </svg>
  );
}

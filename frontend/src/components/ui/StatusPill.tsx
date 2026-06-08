import { Loader2 } from "lucide-react";
import { cn } from "@/lib/cn";

type Tone = "pos" | "neg" | "gold" | "muted";

// Maps every backend status (DepositStatus | WithdrawalStatus | TransferStatus) to a tone.
// When the generated enum unions land (schema.gen.ts), this stays the single status→tone map.
const TONE: Record<string, Tone> = {
  // terminal-good
  credited: "pos",
  confirmed: "pos",
  // terminal-bad
  failed: "neg",
  rejected: "neg",
  orphaned: "neg",
  // in-flight
  seen: "gold",
  pending: "gold",
  requested: "gold",
  approved: "gold",
  signing: "gold",
  broadcast: "gold",
  submitted: "gold",
};

const IN_FLIGHT = new Set([
  "seen",
  "pending",
  "requested",
  "approved",
  "signing",
  "broadcast",
  "submitted",
]);

const CLASSES: Record<Tone, string> = {
  pos: "bg-pos/10 text-pos ring-pos/30",
  neg: "bg-neg/10 text-neg ring-neg/30",
  gold: "bg-gold/10 text-gold ring-gold/30",
  muted: "bg-surface2 text-muted ring-border",
};

// Literal classes so Tailwind's JIT keeps them (no string interpolation).
const DOT: Record<Tone, string> = {
  pos: "bg-pos",
  neg: "bg-neg",
  gold: "bg-gold",
  muted: "bg-muted",
};

export function StatusPill({ status, label }: { status: string; label?: string }) {
  const tone = TONE[status] ?? "muted";
  const inFlight = IN_FLIGHT.has(status);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-xs ring-1",
        CLASSES[tone],
      )}
    >
      {inFlight ? (
        <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
      ) : (
        <span className={cn("h-1.5 w-1.5 rounded-full", DOT[tone])} aria-hidden />
      )}
      {label ?? status}
    </span>
  );
}

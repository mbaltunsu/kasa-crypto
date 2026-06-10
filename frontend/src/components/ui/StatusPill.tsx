import { Loader2 } from "lucide-react";
import { cn } from "@/lib/cn";

type Tone = "pos" | "neg" | "warn" | "muted";

// Maps every backend status (DepositStatus | WithdrawalStatus | TransferStatus) to a tone.
// In-flight states are amber (`warn`) so they never read as the mint brand/success color.
const TONE: Record<string, Tone> = {
  // terminal-good
  credited: "pos",
  confirmed: "pos",
  // terminal-bad
  failed: "neg",
  rejected: "neg",
  orphaned: "neg",
  // in-flight
  seen: "warn",
  pending: "warn",
  requested: "warn",
  approved: "warn",
  signing: "warn",
  broadcast: "warn",
  submitted: "warn",
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
  warn: "bg-warn/10 text-warn ring-warn/30",
  muted: "bg-surface2/80 text-muted ring-border/80",
};

// Literal classes so Tailwind's JIT keeps them (no string interpolation).
// Status dots are flat solid color — the tinted pill + label carry the meaning.
const DOT: Record<Tone, string> = {
  pos: "bg-pos",
  neg: "bg-neg",
  warn: "bg-warn",
  muted: "bg-muted",
};

export function StatusPill({ status, label }: { status: string; label?: string }) {
  const tone = TONE[status] ?? "muted";
  const inFlight = IN_FLIGHT.has(status);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1",
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

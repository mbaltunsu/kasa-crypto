import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

/** Soft surface: flat panel + gentle hairline border + neutral elevation. All depth
 * comes from the shared `shadow-card` / `shadow-pop` scale, never ad-hoc shadows. */
export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-2xl border border-border/60 bg-surface shadow-card", className)}
      {...props}
    />
  );
}

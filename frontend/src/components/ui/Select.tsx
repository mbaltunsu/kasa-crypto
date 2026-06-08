import type { SelectHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "w-full appearance-none rounded-lg border border-border bg-surface2 px-3 py-2.5 text-sm text-ink",
        className,
      )}
      {...props}
    />
  );
}

import type { InputHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

export function Field({
  label,
  htmlFor,
  hint,
  error,
  children,
}: {
  label: string;
  htmlFor: string;
  hint?: ReactNode;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label
        htmlFor={htmlFor}
        className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-muted"
      >
        {label}
      </label>
      {children}
      {error ? (
        <p role="alert" className="text-xs font-medium text-neg">
          {error}
        </p>
      ) : hint ? (
        <p className="text-xs text-muted/70">{hint}</p>
      ) : null}
    </div>
  );
}

/** Inputs sit *into* the card (darker than the surface) so forms read as carved-in wells. */
export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "w-full rounded-xl border border-border/80 bg-bg/60 px-3.5 py-2.5 text-sm text-ink",
        "placeholder:text-muted/50 transition-colors duration-200 hover:border-border focus:border-gold/50",
        className,
      )}
      {...props}
    />
  );
}

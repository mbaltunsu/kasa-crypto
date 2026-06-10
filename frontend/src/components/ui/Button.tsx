import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-gradient-gold text-bg font-semibold shadow-glow-gold-sm hover:brightness-105",
  secondary:
    "bg-surface2/70 text-ink ring-1 ring-border/70 hover:bg-surface2 hover:text-ink-hi hover:ring-border",
  ghost: "text-muted hover:bg-surface2/60 hover:text-ink",
  danger: "bg-neg/10 text-neg ring-1 ring-neg/30 hover:bg-neg/15 hover:ring-neg/50",
};

export function Button({
  variant = "primary",
  className,
  type = "button",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type={type}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm",
        "transition-all duration-200 active:scale-[0.97]",
        "disabled:pointer-events-none disabled:opacity-50",
        VARIANTS[variant],
        className,
      )}
      {...props}
    />
  );
}

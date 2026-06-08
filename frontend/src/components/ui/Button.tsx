import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-gold text-bg font-semibold hover:brightness-110",
  secondary: "bg-surface2 text-ink ring-1 ring-border hover:bg-border/40",
  ghost: "text-muted hover:text-ink hover:bg-surface",
  danger: "bg-neg/10 text-neg ring-1 ring-neg/30 hover:bg-neg/20",
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
        "inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm transition",
        "disabled:pointer-events-none disabled:opacity-50",
        VARIANTS[variant],
        className,
      )}
      {...props}
    />
  );
}

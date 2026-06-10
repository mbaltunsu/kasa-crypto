import type { Config } from "tailwindcss";

// "Signal" tokens (v5) — see docs/design_system.md (the committed source of truth).
// Token NAMES are stable across redesigns (bg/surface/ink/gold/…); only values change.
// `gold` is the historical name of the brand-accent slot — it now resolves to Signal mint.
export default {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0B0E13",
        surface: "#11151D",
        surface2: "#181E29",
        border: "#222B39",
        ink: "#DFE6F0",
        "ink-hi": "#F6F9FD",
        muted: "#8C97AB",
        // Brand accent (slot name "gold" kept for class stability) — calm signal mint,
        // deliberately dimmed (~20%) so large CTAs don't fatigue eyes on the dark canvas.
        gold: "#2BC495",
        "gold-hi": "#57D9AF",
        "gold-deep": "#178F6B",
        pos: "#2BC495",
        neg: "#FF5C7A",
        warn: "#F5B544",
        tech: "#8B9DFF",
        aqua: "#5CC8FF",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      fontSize: {
        // Expressive hero sizes (login brand, dashboard balances).
        display: [
          "clamp(2.25rem, 1.4rem + 2.6vw, 3.25rem)",
          { lineHeight: "1.08", letterSpacing: "-0.03em", fontWeight: "700" },
        ],
        "display-sm": [
          "clamp(1.625rem, 1.25rem + 1.2vw, 2.125rem)",
          { lineHeight: "1.15", letterSpacing: "-0.02em", fontWeight: "600" },
        ],
      },
      backgroundImage: {
        // Primary CTA ramp — barely-shifted calm mint, reads as a rich solid.
        "gradient-gold": "linear-gradient(170deg, #35CD9E 0%, #1FA87C 100%)",
        // Hairline top sheen for raised surfaces (kept extremely subtle).
        "gradient-sheen":
          "linear-gradient(180deg, rgb(255 255 255 / 0.03) 0%, rgb(255 255 255 / 0) 32%)",
        // Faint brand wash behind hero sections — a hint, not an aura.
        "gradient-hero":
          "radial-gradient(720px 300px at 50% -8%, rgb(43 196 149 / 0.05), transparent 65%)",
      },
      boxShadow: {
        // Neutral elevation scale — engineered depth, no colored halos.
        card: "0 1px 0 0 rgb(255 255 255 / 0.03) inset, 0 8px 24px -12px rgb(0 0 0 / 0.55)",
        pop: "0 1px 0 0 rgb(255 255 255 / 0.04) inset, 0 16px 40px -16px rgb(0 0 0 / 0.7)",
        // Legacy glow slots kept for class stability — resolve to quiet neutrals.
        "glow-gold": "0 6px 20px -8px rgb(0 0 0 / 0.6)",
        "glow-gold-sm": "0 4px 14px -8px rgb(0 0 0 / 0.55)",
        "glow-pos": "none",
        "glow-neg": "none",
      },
      keyframes: {
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        shimmer: "shimmer 2.2s infinite",
        "fade-up": "fade-up 0.45s cubic-bezier(0.16, 1, 0.3, 1) both",
      },
    },
  },
  plugins: [],
} satisfies Config;

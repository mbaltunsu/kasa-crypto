import type { Config } from "tailwindcss";

// Exchange Dark v2 tokens — see docs/design_system.md (the committed source of truth).
export default {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0F172A",
        surface: "#1B2336",
        surface2: "#232B3F",
        border: "#2D3A50",
        ink: "#DCE3EC",
        "ink-hi": "#F1F5F9",
        muted: "#94A3B8",
        gold: "#F59E0B",
        pos: "#34D399",
        neg: "#F87171",
        tech: "#A78BFA",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;

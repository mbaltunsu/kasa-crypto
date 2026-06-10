import { Sora, Spline_Sans_Mono } from "next/font/google";

// "Signal" type system: Sora (geometric grotesque — display + UI) paired with
// Spline Sans Mono (data: balances, addresses, hashes). The CSS variable names
// are kept stable (--font-inter/--font-mono) because tailwind.config maps them.
export const sans = Sora({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const mono = Spline_Sans_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

import type { Metadata } from "next";
import type { ReactNode } from "react";
import { inter, jetbrainsMono } from "@/lib/fonts";
import { Providers } from "@/app/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "Kasa — Wallet",
  description: "Custodial multi-chain exchange wallet",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`dark ${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="bg-bg font-sans text-ink antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

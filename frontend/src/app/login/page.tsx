"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ScanLine, ShieldCheck, Sparkles, Waypoints } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Field";
import { KasaLogo } from "@/components/ui/KasaLogo";
import { NetworkIcon } from "@/components/ui/NetworkIcon";
import { useLogin, useRegister } from "@/api/queries";

type Mode = "login" | "register";

// The demo roster the backend seeds at startup (SEED_DEMO_USER). All share DEMO_PASSWORD; the
// first account is the admin. The buttons below let people switch accounts in one click.
const DEMO_PASSWORD = "kasademo123";
const DEMO_ACCOUNTS = [
  { label: "Demo · admin", email: "demo@kasa.app" },
  { label: "Alice", email: "alice@kasa.app" },
  { label: "Bob", email: "bob@kasa.app" },
];

const FEATURES = [
  { icon: ShieldCheck, text: "Custodial HD vault — double-entry ledger behind every balance" },
  { icon: ScanLine, text: "Live chain watcher — deposits credit as confirmations land" },
  { icon: Waypoints, text: "Reorg-safe indexing across Sepolia and Fuji" },
];

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState(DEMO_ACCOUNTS[0]!.email);
  const [password, setPassword] = useState(DEMO_PASSWORD);

  const login = useLogin();
  const register = useRegister();
  const active = mode === "login" ? login : register;

  function switchMode(next: Mode) {
    setMode(next);
    // Keep the demo creds prefilled for sign-in; clear them when creating a fresh account.
    setEmail(next === "login" ? DEMO_ACCOUNTS[0]!.email : "");
    setPassword(next === "login" ? DEMO_PASSWORD : "");
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    active.mutate({ email, password }, { onSuccess: () => router.replace("/") });
  }

  function quickLogin(account: { email: string }) {
    setEmail(account.email);
    setPassword(DEMO_PASSWORD);
    login.mutate(
      { email: account.email, password: DEMO_PASSWORD },
      { onSuccess: () => router.replace("/") },
    );
  }

  return (
    <div className="relative grid min-h-dvh place-items-center overflow-hidden p-6">
      {/* Faint mint signal wash at the top of the canvas. */}
      <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-72 bg-gradient-hero" />

      <div className="grid w-full max-w-4xl animate-fade-up items-center gap-10 lg:grid-cols-[1.1fr_1fr] lg:gap-14">
        {/* Brand panel */}
        <div className="flex flex-col items-center text-center lg:items-start lg:text-left">
          <div className="flex items-center gap-3.5">
            <KasaLogo className="h-12 w-12 shadow-card" />
            <span className="text-display text-gradient-gold">Kasa</span>
          </div>
          <p className="mt-4 max-w-sm text-balance text-lg font-medium leading-snug text-ink-hi">
            A custodial multi-chain vault, built on real testnet rails.
          </p>

          <ul className="mt-7 hidden space-y-3 lg:block">
            {FEATURES.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-start gap-2.5 text-sm text-muted">
                <Icon className="mt-0.5 h-4 w-4 shrink-0 text-gold" aria-hidden />
                {text}
              </li>
            ))}
          </ul>

          <div className="mt-7 hidden items-center gap-2 lg:flex">
            {[11155111, 43113].map((id) => (
              <span
                key={id}
                className="flex items-center gap-2 rounded-full bg-surface/80 py-1.5 pl-2 pr-3 text-xs font-medium text-muted ring-1 ring-border/70"
              >
                <NetworkIcon chainId={id} className="h-4 w-4" />
                {id === 11155111 ? "Ethereum Sepolia" : "Avalanche Fuji"}
              </span>
            ))}
          </div>
        </div>

        {/* Auth card */}
        <div className="w-full">
          <Card className="p-7 shadow-pop">
            <div className="mb-5 flex rounded-xl bg-bg/60 p-1 text-sm ring-1 ring-border/80">
              {(["login", "register"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => switchMode(m)}
                  className={
                    "flex-1 rounded-lg px-3 py-1.5 transition-all duration-200 " +
                    (mode === m
                      ? "bg-surface2 font-semibold text-ink-hi shadow-card"
                      : "text-muted hover:text-ink")
                  }
                >
                  {m === "login" ? "Sign in" : "Create account"}
                </button>
              ))}
            </div>

            {mode === "login" && (
              <div className="mb-4 space-y-2">
                <p className="flex items-center justify-center gap-1.5 rounded-lg bg-gold/[0.08] px-3 py-2 text-center text-xs font-medium text-gold ring-1 ring-gold/25">
                  <Sparkles className="h-3.5 w-3.5" aria-hidden />
                  Demo — tap an account to sign in instantly
                </p>
                <div className="grid grid-cols-3 gap-2">
                  {DEMO_ACCOUNTS.map((a) => (
                    <button
                      key={a.email}
                      type="button"
                      onClick={() => quickLogin(a)}
                      disabled={login.isPending}
                      className="rounded-lg border border-border/70 bg-surface2/60 px-2 py-2 text-xs font-medium text-muted transition-all duration-200 hover:border-gold/40 hover:bg-surface2 hover:text-ink-hi active:scale-[0.97] disabled:opacity-60"
                    >
                      {a.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <form className="space-y-4" onSubmit={submit}>
              <Field label="Email" htmlFor="email">
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </Field>
              <Field
                label="Password"
                htmlFor="password"
                error={active.isError ? "Authentication failed. Check your credentials." : undefined}
              >
                <Input
                  id="password"
                  type="password"
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  required
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </Field>
              <Button type="submit" className="w-full py-3 text-[15px]" disabled={active.isPending}>
                {active.isPending ? "…" : mode === "login" ? "Sign in" : "Create account"}
              </Button>
            </form>
          </Card>

          <p className="mt-5 text-center text-[11px] text-muted/70">
            Testnet demo · custodial wallet · no real funds
          </p>
        </div>
      </div>
    </div>
  );
}

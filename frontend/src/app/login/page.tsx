"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Gem } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Field";
import { useLogin, useRegister } from "@/api/queries";

type Mode = "login" | "register";

// Demo login, prefilled for one-click access. Matches the backend DEMO_EMAIL / DEMO_PASSWORD
// defaults that SEED_DEMO_USER seeds at startup.
const DEMO_EMAIL = "demo@kasa.app";
const DEMO_PASSWORD = "kasademo123";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState(DEMO_EMAIL);
  const [password, setPassword] = useState(DEMO_PASSWORD);

  const login = useLogin();
  const register = useRegister();
  const active = mode === "login" ? login : register;

  function switchMode(next: Mode) {
    setMode(next);
    // Keep the demo creds prefilled for sign-in; clear them when creating a fresh account.
    setEmail(next === "login" ? DEMO_EMAIL : "");
    setPassword(next === "login" ? DEMO_PASSWORD : "");
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    active.mutate({ email, password }, { onSuccess: () => router.replace("/") });
  }

  return (
    <div className="grid min-h-dvh place-items-center p-6">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2.5">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-gold/15 ring-1 ring-gold/40">
            <Gem className="h-5 w-5 text-gold" />
          </span>
          <span className="text-2xl font-bold tracking-tight text-ink-hi">Kasa</span>
        </div>

        <Card className="p-7">
          <div className="mb-5 flex rounded-lg bg-surface2 p-1 text-sm ring-1 ring-border">
            {(["login", "register"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => switchMode(m)}
                className={
                  "flex-1 rounded-md px-3 py-1.5 transition-colors " +
                  (mode === m ? "bg-surface font-medium text-ink" : "text-muted hover:text-ink")
                }
              >
                {m === "login" ? "Sign in" : "Create account"}
              </button>
            ))}
          </div>

          {mode === "login" && (
            <p className="mb-4 rounded-md bg-gold/10 px-3 py-2 text-center text-xs text-gold ring-1 ring-gold/25">
              ✨ Demo login prefilled — just press <span className="font-semibold">Sign in</span>
            </p>
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
            <Button type="submit" className="w-full" disabled={active.isPending}>
              {active.isPending ? "…" : mode === "login" ? "Sign in" : "Create account"}
            </Button>
          </form>
        </Card>

        <p className="mt-4 text-center text-[11px] text-muted/70">
          Testnet demo · custodial wallet · no real funds
        </p>
      </div>
    </div>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ArrowDownToLine,
  ArrowRightLeft,
  ArrowUpFromLine,
  Gem,
  History,
  Images,
  LayoutDashboard,
  LogOut,
  ShieldCheck,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

const PRIMARY: NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/deposit", label: "Deposit", icon: ArrowDownToLine },
  { href: "/withdraw", label: "Withdraw", icon: ArrowUpFromLine },
  { href: "/transfer", label: "Transfer", icon: ArrowRightLeft },
  { href: "/history", label: "History", icon: History },
  { href: "/nfts", label: "Collectibles", icon: Images },
];

export function Sidebar() {
  const pathname = usePathname();
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-border bg-[#111827]/60 md:flex">
      <div className="flex h-16 items-center gap-2.5 border-b border-border px-5">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-gold/15 ring-1 ring-gold/40">
          <Gem className="h-4 w-4 text-gold" />
        </span>
        <span className="text-[17px] font-bold tracking-tight text-ink-hi">Kasa</span>
        <span className="ml-auto rounded border border-border px-1.5 py-0.5 text-[10px] font-semibold text-muted">
          TESTNET
        </span>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4 text-sm">
        {PRIMARY.map(({ href, label, icon: Icon }) => {
          const active = isActive(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 transition-colors",
                active
                  ? "bg-gold/10 font-medium text-ink ring-1 ring-gold/30"
                  : "text-muted hover:bg-surface hover:text-ink",
              )}
            >
              <Icon className={cn("h-[18px] w-[18px]", active && "text-gold")} />
              {label}
            </Link>
          );
        })}
        <div className="mt-3 border-t border-border pt-3">
          <Link
            href="/admin"
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2 transition-colors",
              isActive("/admin")
                ? "bg-gold/10 font-medium text-ink ring-1 ring-gold/30"
                : "text-muted hover:bg-surface hover:text-ink",
            )}
          >
            <ShieldCheck className="h-[18px] w-[18px]" />
            Admin · Reserves
          </Link>
        </div>
      </nav>

      <div className="border-t border-border p-3">
        <div className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-surface">
          <span className="grid h-8 w-8 place-items-center rounded-full bg-tech/20 text-xs font-semibold text-tech">
            BA
          </span>
          <div className="min-w-0">
            <div className="truncate text-xs font-medium">bengican@gmail.com</div>
            <div className="text-[11px] text-muted">user</div>
          </div>
          <button type="button" aria-label="Sign out" className="ml-auto text-muted hover:text-ink">
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}

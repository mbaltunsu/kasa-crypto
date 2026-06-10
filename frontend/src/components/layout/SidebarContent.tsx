"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  ArrowDownToLine,
  ArrowRightLeft,
  ArrowUpFromLine,
  History,
  Images,
  LayoutDashboard,
  LogOut,
  ShieldCheck,
} from "lucide-react";
import { KasaLogo } from "@/components/ui/KasaLogo";
import type { LucideIcon } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/cn";
import { setAccessToken } from "@/api/client";
import { useMe } from "@/api/queries";

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
  { href: "/nft-transfer", label: "NFT Transfer", icon: ArrowRightLeft },
];

function NavLink({
  item,
  active,
  onNavigate,
}: {
  item: NavItem;
  active: boolean;
  onNavigate?: () => void;
}) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      className={cn(
        "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 transition-colors duration-200",
        active
          ? "bg-surface2/70 font-semibold text-ink-hi"
          : "text-muted hover:bg-surface/80 hover:text-ink",
      )}
    >
      {active ? (
        <span
          className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-full bg-gold"
          aria-hidden
        />
      ) : null}
      <Icon
        className={cn(
          "h-[18px] w-[18px] transition-colors",
          active ? "text-gold" : "text-muted/80 group-hover:text-ink",
        )}
      />
      {item.label}
    </Link>
  );
}

/** The shared shell body (brand, nav, account footer). Rendered inside the desktop `<aside>` and
 * the mobile drawer; `onNavigate` lets the drawer close itself when a link is tapped. */
export function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const me = useMe();
  const email = me.data?.email ?? "—";
  const role = me.data?.role ?? "";
  const initials = email.includes("@") ? email.slice(0, 2).toUpperCase() : "··";
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  const signOut = () => {
    setAccessToken(null);
    queryClient.clear();
    onNavigate?.();
    router.replace("/login");
  };

  return (
    <>
      <div className="flex h-16 items-center gap-2.5 border-b border-border/60 px-5">
        <KasaLogo className="h-9 w-9" />
        <span className="text-lg font-extrabold tracking-tight text-ink-hi">Kasa</span>
        <span className="ml-auto rounded-md bg-gold/10 px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-gold ring-1 ring-gold/30">
          TESTNET
        </span>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4 text-sm">
        <p className="px-3 pb-2 pt-1 text-[10px] font-bold uppercase tracking-[0.18em] text-muted/60">
          Wallet
        </p>
        {PRIMARY.map((item) => (
          <NavLink
            key={item.href}
            item={item}
            active={isActive(item.href)}
            onNavigate={onNavigate}
          />
        ))}
        {role === "admin" ? (
          <div className="mt-3 border-t border-border/60 pt-3">
            <p className="px-3 pb-2 text-[10px] font-bold uppercase tracking-[0.18em] text-muted/60">
              Admin
            </p>
            <NavLink
              item={{ href: "/admin", label: "Admin · Reserves", icon: ShieldCheck }}
              active={isActive("/admin")}
              onNavigate={onNavigate}
            />
          </div>
        ) : null}
      </nav>

      <div className="border-t border-border/60 p-3">
        <div className="flex items-center gap-3 rounded-xl px-2 py-2 transition-colors hover:bg-surface/80">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-tech/15 text-xs font-bold text-tech ring-1 ring-tech/25">
            {initials}
          </span>
          <div className="min-w-0">
            <div className="truncate text-xs font-semibold text-ink">{email}</div>
            <div className="text-[11px] capitalize text-muted">{role}</div>
          </div>
          <button
            type="button"
            onClick={signOut}
            aria-label="Sign out"
            title="Sign out"
            className="ml-auto rounded-lg p-1.5 text-muted transition-colors hover:bg-surface2 hover:text-neg"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </>
  );
}

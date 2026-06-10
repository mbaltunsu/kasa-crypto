import { cn } from "@/lib/cn";

// Network logos live in /public/networks (sourced from frontend/assets).
// Testnets map to their parent network's mark: Sepolia → Ethereum, Fuji → Avalanche.
const NETWORK_LOGO: Record<number, { src: string; alt: string }> = {
  1: { src: "/networks/ethereum.svg", alt: "Ethereum" },
  11155111: { src: "/networks/ethereum.svg", alt: "Ethereum" },
  43114: { src: "/networks/avalanche.svg", alt: "Avalanche" },
  43113: { src: "/networks/avalanche.svg", alt: "Avalanche" },
};

/** A network (chain) logo. Falls back to a neutral dot for chains without a mark
 * (e.g. the local Hardhat node). */
export function NetworkIcon({ chainId, className }: { chainId: number; className?: string }) {
  const logo = NETWORK_LOGO[chainId];
  if (!logo) {
    return (
      <span
        aria-hidden
        className={cn("inline-block shrink-0 rounded-full bg-muted/40", className)}
      />
    );
  }
  return (
    <img
      src={logo.src}
      alt={logo.alt}
      className={cn("inline-block shrink-0 object-contain", className)}
    />
  );
}

// Native coins whose network mark IS the asset mark.
const NATIVE_SYMBOL_LOGO: Record<string, { src: string; alt: string }> = {
  ETH: { src: "/networks/ethereum.svg", alt: "Ethereum" },
  AVAX: { src: "/networks/avalanche.svg", alt: "Avalanche" },
};

const TOKEN_CHIP: Record<string, string> = {
  DEMO: "bg-tech/15 text-tech ring-tech/30",
  KASA: "bg-gold/10 text-gold ring-gold/30",
};

/** An asset mark: real network logo for native coins (ETH/AVAX), a lettered chip for
 * tokens — each with a small chain badge so the network is always visible. */
export function AssetIcon({
  symbol,
  chainId,
  className,
}: {
  symbol: string;
  chainId: number;
  className?: string;
}) {
  const native = NATIVE_SYMBOL_LOGO[symbol];
  const showBadge = NETWORK_LOGO[chainId] !== undefined;
  return (
    <span className={cn("relative inline-grid shrink-0 place-items-center", className)}>
      {native ? (
        <span className="grid h-full w-full place-items-center rounded-full bg-surface2 ring-1 ring-border">
          <img src={native.src} alt={native.alt} className="h-[62%] w-[62%] object-contain" />
        </span>
      ) : (
        <span
          className={cn(
            "grid h-full w-full place-items-center rounded-full text-[10px] font-bold ring-1",
            TOKEN_CHIP[symbol] ?? "bg-surface2 text-muted ring-border",
          )}
        >
          {symbol.slice(0, 4)}
        </span>
      )}
      {!native && showBadge ? (
        <span className="absolute -bottom-0.5 -right-0.5 grid h-[42%] w-[42%] place-items-center rounded-full bg-bg ring-1 ring-border">
          <NetworkIcon chainId={chainId} className="h-[68%] w-[68%]" />
        </span>
      ) : null}
    </span>
  );
}

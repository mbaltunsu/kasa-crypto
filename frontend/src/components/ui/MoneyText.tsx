import { formatAmount } from "@kasa/shared";
import { cn } from "@/lib/cn";

/**
 * Renders an integer base-unit amount as a human decimal using the shared formatter.
 * Always mono + tabular so columns align. `sign` prefixes a "+" for positive values.
 */
export function MoneyText({
  amount,
  decimals,
  symbol,
  sign = false,
  className,
}: {
  amount: string | bigint;
  decimals: number;
  symbol?: string;
  sign?: boolean;
  className?: string;
}) {
  const formatted = formatAmount({ decimals }, amount);
  const isNeg = formatted.startsWith("-");
  const display = sign && !isNeg && formatted !== "0" ? `+${formatted}` : formatted;
  return (
    <span className={cn("num font-mono", className)}>
      {display}
      {symbol ? <span className="ml-1 text-muted">{symbol}</span> : null}
    </span>
  );
}

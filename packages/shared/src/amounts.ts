// Integer base-unit amount math. String on the wire, bigint in code, NEVER a float —
// 2^256 overflows 2^53, so any path through Number() corrupts balances. Mirrored exactly by
// the Python kasa_shared.amounts; both are pinned by packages/shared/fixtures/amounts.json.

/** Branded base-unit integer string (e.g. "1000000000000000000"). */
export type BaseUnitString = string & { readonly __brand: "BaseUnitString" };

const INT_RE = /^-?(0|[1-9]\d*)$/; // optional sign, no leading zeros, no decimals
const HUMAN_RE = /^-?\d*(\.\d*)?$/; // decimal human input (rejects exponents, letters, double dots)

/** Parse a wire base-unit string to bigint; throws on a malformed integer. */
export function parseBaseUnit(s: string): bigint {
  if (!INT_RE.test(s)) throw new RangeError(`invalid base-unit integer: ${JSON.stringify(s)}`);
  return BigInt(s);
}

/** Human decimal string -> base-unit bigint, using the asset's decimals. Pure string math. */
export function parseAmount(asset: { decimals: number; symbol: string }, human: string): bigint {
  const d = asset.decimals;
  const s = human.trim();
  if (s === "" || s === "-" || s === "." || s === "-." || !HUMAN_RE.test(s)) {
    throw new RangeError(`invalid amount for ${asset.symbol}: ${JSON.stringify(human)}`);
  }
  const neg = s.startsWith("-");
  const body = neg ? s.slice(1) : s;
  const dot = body.indexOf(".");
  const whole = dot === -1 ? body : body.slice(0, dot);
  const frac = dot === -1 ? "" : body.slice(dot + 1);
  if (frac.length > d) {
    throw new RangeError(`too many decimals for ${asset.symbol} (max ${d}): ${human}`);
  }
  const v = BigInt((whole || "0") + frac.padEnd(d, "0"));
  return neg ? -v : v;
}

/** Base-unit bigint|string -> human decimal string (trailing zeros + bare dot trimmed, sign kept). */
export function formatAmount(asset: { decimals: number }, baseUnits: bigint | string): string {
  const d = asset.decimals;
  let v = typeof baseUnits === "bigint" ? baseUnits : parseBaseUnit(baseUnits);
  const neg = v < 0n;
  if (neg) v = -v;
  const digits = v.toString().padStart(d + 1, "0");
  const whole = digits.slice(0, digits.length - d);
  const frac = (d > 0 ? digits.slice(digits.length - d) : "").replace(/0+$/, "");
  const out = frac ? `${whole}.${frac}` : whole;
  return neg && out !== "0" ? `-${out}` : out;
}

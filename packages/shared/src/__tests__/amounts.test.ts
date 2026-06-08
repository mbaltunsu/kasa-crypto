import { describe, expect, it } from "vitest";
import fixtures from "../../fixtures/amounts.json";
import { formatAmount, parseAmount, parseBaseUnit } from "../amounts.js";

describe("amount golden vectors (shared with Python)", () => {
  for (const v of fixtures.parse) {
    it(`parse d${v.decimals} "${v.human}" -> ${v.base}`, () => {
      expect(parseAmount({ decimals: v.decimals, symbol: "X" }, v.human).toString()).toBe(v.base);
    });
  }

  for (const v of fixtures.parseErrors) {
    it(`parse d${v.decimals} "${v.human}" throws`, () => {
      expect(() => parseAmount({ decimals: v.decimals, symbol: "X" }, v.human)).toThrow();
    });
  }

  for (const v of fixtures.format) {
    it(`format d${v.decimals} ${v.base} -> "${v.human}"`, () => {
      expect(formatAmount({ decimals: v.decimals }, v.base)).toBe(v.human);
    });
  }

  it("rejects malformed base-unit strings", () => {
    expect(() => parseBaseUnit("01")).toThrow();
    expect(() => parseBaseUnit("1.0")).toThrow();
    expect(() => parseBaseUnit("0x1")).toThrow();
    expect(parseBaseUnit("-5")).toBe(-5n);
  });
});

import { describe, expect, it } from "vitest";
import { isAddress, isAddressEqual, toChecksum, toLookupKey } from "../address.js";

// Canonical EIP-55 vector (from the spec).
const LOWER = "0x5aaeb6053f3e94c9b9a09f33669435e7ef1beaed";
const CHECKSUM = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed";

describe("address", () => {
  it("produces plain EIP-55 checksums", () => {
    expect(toChecksum(LOWER)).toBe(CHECKSUM);
    expect(toChecksum(CHECKSUM.toUpperCase().replace("0X", "0x"))).toBe(CHECKSUM);
  });

  it("lookup key is always lowercase", () => {
    expect(toLookupKey(CHECKSUM)).toBe(LOWER);
  });

  it("compares case-insensitively and rejects malformed input", () => {
    expect(isAddressEqual(LOWER, CHECKSUM)).toBe(true);
    expect(isAddressEqual(LOWER, "0xdead")).toBe(false);
    expect(isAddress(CHECKSUM)).toBe(true);
    expect(isAddress("nope")).toBe(false);
  });
});

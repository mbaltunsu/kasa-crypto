// TS half of the no-drift gate. Validates every data file against the Zod schema, re-checks the
// generated bundle matches the data, and prints the canonical content hash that the Python half
// must reproduce (CI compares the two hashes). Exits non-zero on any failure.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { ASSET_TYPES } from "../src/consts.js";
import { canonicalRows, chainIds, listChains } from "../src/api.js";
import { chainSchema, manifestSchema } from "../src/schema.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (p: string): unknown => JSON.parse(readFileSync(join(root, p), "utf8"));

let failures = 0;
const fail = (msg: string): void => {
  console.error(`✗ ${msg}`);
  failures += 1;
};

// 1. every data file validates against the schema
const manifest = manifestSchema.parse(read("data/registry.json"));
for (const id of manifest.chainIds) {
  const res = chainSchema.safeParse(read(`data/chains/${id}.json`));
  if (!res.success) fail(`data/chains/${id}.json invalid: ${res.error.message}`);
}

// 2. loaded registry covers exactly the manifest chains
const loaded = new Set(chainIds());
if (loaded.size !== manifest.chainIds.length || !manifest.chainIds.every((id) => loaded.has(id))) {
  fail(`registry chains ${[...loaded]} != manifest ${manifest.chainIds}`);
}

// 3. asset types in data are a subset of the canonical const
for (const chain of listChains()) {
  for (const a of chain.assets) {
    if (!(ASSET_TYPES as readonly string[]).includes(a.type)) fail(`unknown asset type ${a.type}`);
  }
}

const hash = createHash("sha256").update(canonicalRows()).digest("hex");
if (failures > 0) {
  console.error(`check-parity FAILED (${failures})`);
  process.exit(1);
}
console.log(`check-parity OK · content-hash sha256=${hash}`);

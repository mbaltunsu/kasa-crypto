// Emit the cross-language JSON Schema from the Zod chain schema. This is the contract the Python
// Pydantic models validate against too. Committed; CI fails if it drifts from the Zod source.
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { zodToJsonSchema } from "zod-to-json-schema";
import { chainSchema } from "../src/schema.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const schema = zodToJsonSchema(chainSchema, { name: "Chain", target: "jsonSchema2020-12" });

mkdirSync(join(root, "schema"), { recursive: true });
writeFileSync(join(root, "schema/registry.schema.json"), JSON.stringify(schema, null, 2) + "\n");
console.log("registry.schema.json written");

import { readFileSync, writeFileSync } from "node:fs";
// Ship the browser guide with the browser app. Gateway relays this plain-text file
// to the shared Docs assistant; it must not receive the SPA fallback HTML.
const guide = readFileSync(new URL("../docs/assistant-guide.md", import.meta.url), "utf8");
if (!guide.trim() || Buffer.byteLength(guide) > 128 * 1024) throw new Error("Invalid Assistant browser documentation");
writeFileSync(new URL("../dist/llms.txt", import.meta.url), guide);

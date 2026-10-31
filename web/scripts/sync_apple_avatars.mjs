// Snapshot canonical compiled adapters and AbstractAvatar Wasm for standalone browser builds.
// The source of procedural geometry is AbstractAvatar; these files contain presentation only.
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
const root = fileURLToPath(new URL("../", import.meta.url));
const canonical = resolve(root, "../../abstractuic/ui-kit");
const target = resolve(root, "src/vendor/abstractavatar");
const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");
const files = ["avatar_renderer.js", "avatar_renderer.d.ts", "activity_avatar.js", "activity_avatar.d.ts", "avatars/avatar_core.wasm", "avatars/provenance.json"];
const sources = ["src/avatar_renderer.ts", "src/activity_avatar.tsx", "src/avatars/avatar_core.wasm", "src/avatars/provenance.json"];
if (process.argv.includes("--check")) {
  const manifest = JSON.parse(readFileSync(resolve(target, "provenance.json"), "utf8"));
  if (manifest.schema_version !== 1 || Object.keys(manifest.artifacts).length !== files.length)
    throw new Error("Unsupported AbstractAvatar snapshot manifest");
  for (const file of files) {
    if (hash(readFileSync(resolve(target, file))) !== manifest.artifacts[file])
      throw new Error(`Changed generated avatar artifact: ${file}`);
  }
  for (const file of sources) {
    const path = resolve(canonical, file);
    if (existsSync(path) && hash(readFileSync(path)) !== manifest.sources[file])
      throw new Error(`Avatar snapshot is stale: ${file}. Build ui-kit, then run npm run sync:avatars.`);
  }
  console.log("AbstractAvatar compiled adapter and Wasm snapshot integrity verified");
} else {
  const manifest = { schema_version: 1, owner: "AbstractAvatar", adapter_owner: "@abstractframework/ui-kit", sources: {}, artifacts: {} };
  for (const file of sources) manifest.sources[file] = hash(readFileSync(resolve(canonical, file)));
  for (const file of files) {
    const content = readFileSync(resolve(canonical, "dist", file));
    const destination = resolve(target, file);
    mkdirSync(dirname(destination), { recursive: true });
    writeFileSync(destination, content, { mode: 0o644 });
    manifest.artifacts[file] = hash(content);
  }
  writeFileSync(resolve(target, "provenance.json"), JSON.stringify(manifest, null, 2) + "\n");
  console.log("Updated canonical AbstractAvatar snapshot from built AbstractUIC adapters");
}

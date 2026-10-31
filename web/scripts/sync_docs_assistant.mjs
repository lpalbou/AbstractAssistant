// Snapshot the canonical shared Docs component while its next npm release is pending.
// React and ui-kit stay external so the application retains one audio/state owner.
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const upstream = resolve(root, "../../abstractuic/panel-chat");
const target = resolve(root, "src/vendor/abstractdocs");
const hash = bytes => createHash("sha256").update(bytes).digest("hex");
const read = path => readFileSync(path);
const safeArtifact = name => name === "docs_assistant.js" || /^[a-z0-9_]+\.d\.ts$/.test(name);

if (process.argv.includes("--check")) {
  const manifest = JSON.parse(readFileSync(resolve(target, "provenance.json"), "utf8"));
  const names = Object.keys(manifest.artifacts ?? {});
  if (manifest.schema_version !== 1 || manifest.owner !== "@abstractframework/panel-chat"
      || !names.includes("docs_assistant.js") || !names.includes("docs_assistant.d.ts")
      || !names.every(safeArtifact)) throw new Error("Unsupported shared Docs snapshot manifest");
  for (const name of names) {
    if (hash(read(resolve(target, name))) !== manifest.artifacts[name])
      throw new Error(`Changed generated shared Docs artifact: ${name}`);
  }
  if (process.argv.includes("--check-source")) {
    for (const [name, expected] of Object.entries(manifest.sources)) {
      if (!/^dist\/[a-z0-9_]+\.(?:js|d\.ts)$/.test(name))
        throw new Error("Invalid shared Docs source path");
      const path = resolve(upstream, name);
      if (!existsSync(path) || hash(read(path)) !== expected)
        throw new Error(`Shared Docs snapshot differs from upstream: ${name}`);
    }
  }
  console.log("Canonical shared Docs snapshot integrity verified");
} else {
  const require = createRequire(resolve(upstream, "package.json"));
  const { build } = require("esbuild");
  const result = await build({
    entryPoints: [resolve(upstream, "dist/docs_assistant.js")],
    bundle: true, write: false, metafile: true, minify: true, format: "esm", target: "es2020",
    external: ["react", "react/*", "react-dom", "react-dom/*", "@abstractframework/ui-kit"],
    banner: { js: "// Generated from @abstractframework/panel-chat. Edit the canonical source, then regenerate." },
  });
  if (result.outputFiles.length !== 1) throw new Error("Shared Docs bundle produced unexpected assets");
  mkdirSync(target, { recursive: true });
  const manifest = { schema_version: 1, owner: "@abstractframework/panel-chat", external: ["react", "react-dom", "@abstractframework/ui-kit"], sources: {}, artifacts: {} };
  const js = result.outputFiles[0].contents;
  writeFileSync(resolve(target, "docs_assistant.js"), js);
  manifest.artifacts["docs_assistant.js"] = hash(js);
  // Keep the canonical declaration graph rather than weakening the application's types.
  for (const name of readdirSync(resolve(upstream, "dist")).filter(name => /^[a-z0-9_]+\.d\.ts$/.test(name))) {
    const bytes = read(resolve(upstream, "dist", name));
    writeFileSync(resolve(target, name), bytes);
    manifest.artifacts[name] = hash(bytes);
    manifest.sources[`dist/${name}`] = hash(bytes);
  }
  for (const input of Object.keys(result.metafile.inputs)) {
    const absolute = resolve(input);
    if (dirname(absolute) !== resolve(upstream, "dist"))
      throw new Error(`Shared Docs bundle included an unexpected dependency: ${input}`);
    manifest.sources[`dist/${absolute.split(/[\\/]/).pop()}`] = hash(read(absolute));
  }
  writeFileSync(resolve(target, "provenance.json"), JSON.stringify(manifest, null, 2) + "\n");
  console.log("Updated canonical shared Docs snapshot");
}

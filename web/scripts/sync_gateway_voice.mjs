// Reproducible shared voice snapshot until the application adopts the next ui-kit release.
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("../", import.meta.url));
const upstream = resolve(root, "../../abstractuic/ui-kit");
const target = resolve(root, "src/vendor/abstractvoice");
const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");
const files = ["use_gateway_voice.js", "use_gateway_voice.d.ts", "af_voice_level_meter.js", "af_voice_level_meter.d.ts"];
if (process.argv.includes("--check")) {
  const manifest = JSON.parse(readFileSync(resolve(target, "provenance.json"), "utf8"));
  if (manifest.schema_version !== 1 || manifest.owner !== "@abstractframework/ui-kit" || Object.keys(manifest.artifacts).length !== files.length) throw new Error("Unsupported shared voice snapshot");
  for (const file of files) if (hash(readFileSync(resolve(target, file))) !== manifest.artifacts[file]) throw new Error(`Changed voice artifact: ${file}`);
  if (process.argv.includes("--check-source")) for (const [file, expected] of Object.entries(manifest.sources)) {
    if (!/^dist\/[a-z0-9_]+\.(?:js|d\.ts)$/.test(file)) throw new Error("Invalid voice source path");
    const path = resolve(upstream, file);
    if (!existsSync(path) || hash(readFileSync(path)) !== expected) throw new Error(`Shared voice snapshot differs from upstream: ${file}`);
  }
  console.log("Shared voice snapshot integrity verified");
} else {
  const require = createRequire(resolve(upstream, "package.json")), { build } = require("esbuild");
  const manifest = { schema_version: 1, owner: "@abstractframework/ui-kit", sources: {}, artifacts: {} };
  mkdirSync(target, { recursive: true });
  for (const name of ["use_gateway_voice", "af_voice_level_meter"]) {
    const result = await build({ absWorkingDir: upstream, entryPoints: [`dist/${name}.js`], bundle: true, write: false, metafile: true, format: "esm", target: "es2020", external: ["react", "react/*"] });
    const js = result.outputFiles[0].contents;
    writeFileSync(resolve(target, `${name}.js`), js);
    manifest.artifacts[`${name}.js`] = hash(js);
    const declaration = `dist/${name}.d.ts`, bytes = readFileSync(resolve(upstream, declaration));
    writeFileSync(resolve(target, `${name}.d.ts`), bytes);
    manifest.artifacts[`${name}.d.ts`] = hash(bytes);
    manifest.sources[declaration] = hash(bytes);
    for (const file of Object.keys(result.metafile.inputs)) {
      if (dirname(resolve(upstream, file)) !== resolve(upstream, "dist")) throw new Error("Unexpected voice dependency");
      manifest.sources[file] = hash(readFileSync(resolve(upstream, file)));
    }
  }
  writeFileSync(resolve(target, "provenance.json"), JSON.stringify(manifest, null, 2) + "\n");
  console.log("Updated shared voice snapshot");
}

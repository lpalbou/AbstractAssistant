#!/usr/bin/env node
// Ported from abstractcode/web/scripts/check_relative_urls.mjs (only the mount path in this comment and the optional public/ differ).
// Browser code never names a ROOT-ABSOLUTE same-origin URL: the app is also
// served under the gateway's /apps/assistant-web/, so "/api/…", "/assets/…" or
// "/apps/…" would escape its base and miss its server. Same-origin paths are
// relative ("api/…" via @abstractframework/ui-kit gatewayApiPath) and resolve
// under the page's <base href>. No allowlist: a literal in a comment fails too.
//
// Scans the shipped browser inputs (src without tests, public/, index.html)
// and, with --dist, the built bundle (dist/, which must exist and is scanned
// whole, the kit packages it bundles included). bin/ is Node server code
// whose routes are matched after the mount strips the base path.
//
// Usage: node scripts/check_relative_urls.mjs [--dist]
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const EXTENSIONS = [".ts", ".tsx", ".js", ".mjs", ".css", ".html", ".json", ".webmanifest"];
const ROOTED = /["'`(]\/(api|assets|apps)(?=[/?#"'`)])/g;

/** Every root-absolute same-origin URL under `path` ("file:line: text"). */
export function rootedUrls(path, { skipTests = true } = {}) {
  const found = [];
  const walk = (p) => {
    if (statSync(p).isDirectory()) {
      for (const name of readdirSync(p)) if (name !== "node_modules") walk(join(p, name));
      return;
    }
    if (!EXTENSIONS.some((e) => p.endsWith(e))) return;
    if (skipTests && /\.test\.[tj]sx?$/.test(p)) return;
    readFileSync(p, "utf8")
      .split("\n")
      .forEach((line, i) => {
        for (const m of line.matchAll(ROOTED)) found.push(`${relative(root, p)}:${i + 1}: ${line.slice(m.index, m.index + 60).trim()}`);
      });
  };
  walk(path);
  return found;
}

/** The shipped inputs (and the build with `dist`); throws when dist is asked for and missing. */
export function checkRelativeUrls({ dist = false } = {}) {
  // public/ is optional here (this app ships no static assets yet); src and index.html are not.
  const targets = ["src", ...(existsSync(join(root, "public")) ? ["public"] : []), "index.html"];
  if (dist) {
    const d = join(root, "dist");
    if (!existsSync(d) || readdirSync(d).length === 0) throw new Error("check_relative_urls: dist/ is missing — build first");
    targets.push("dist");
  }
  return { targets, found: targets.flatMap((t) => rootedUrls(join(root, t))) };
}

if (import.meta.url === pathToFileURL(process.argv[1] || "").href) {
  const { targets, found } = checkRelativeUrls({ dist: process.argv.includes("--dist") });
  if (found.length) {
    for (const f of found) console.error(`  FAIL root-absolute same-origin URL ${f}`);
    process.exit(1);
  }
  console.log(`check_relative_urls: OK (${targets.join(", ")})`);
}

#!/usr/bin/env node
/**
 * Checks what the npm package ships, before anything is published.
 *
 *   node scripts/check_package.mjs                 # what `npm pack` would ship from web/
 *   node scripts/check_package.mjs <file.tgz>      # an already packed tarball
 *   node scripts/check_package.mjs <file.tgz> --version 0.1.0
 *
 * Fails (exit 1) when:
 * - a file is outside the allow-list (dist/, bin/, README.md, CHANGELOG.md, LICENSE,
 *   package.json), or is a source map, an env file, a key or a lockfile;
 * - a required file is missing (dist/index.html, a dist/assets/*.js bundle, bin/cli.js,
 *   bin/server.js, README.md, CHANGELOG.md, LICENSE);
 * - a text file carries an absolute local path (/Users/…, /home/…, C:\Users\…) or a
 *   credential-shaped string (npm, GitHub, OpenAI/Anthropic-style keys, private keys);
 * - the package is not `@abstractframework/assistant`, is marked private, has no CHANGELOG
 *   section for its version, or does not match `--version`.
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, readdirSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const WEB_DIR = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const PACKAGE_NAME = "@abstractframework/assistant";

const ALLOWED = [
  /^package\.json$/,
  /^README\.md$/,
  /^CHANGELOG\.md$/,
  /^LICENSE$/,
  /^bin\/(cli|server)\.js$/,
  /^dist\/index\.html$/,
  /^dist\/llms\.txt$/,
  /^dist\/assets\/[A-Za-z0-9_.-]+\.(js|css|wasm|png|svg|ico|woff2|webp|json|webmanifest)$/,
];
const FORBIDDEN = [/\.map$/, /(^|\/)\.env/, /\.(pem|key|p12|npmrc)$/, /(^|\/)\.npmrc$/, /package-lock\.json$/];
const REQUIRED = ["package.json", "README.md", "CHANGELOG.md", "LICENSE", "bin/cli.js", "bin/server.js", "dist/index.html"];
const TEXT = /\.(js|css|html|txt|md|json|webmanifest|svg)$|^LICENSE$/;
const LEAKS = [
  [/\/Users\/[A-Za-z0-9._-]+\//, "an absolute macOS home path"],
  [/\/home\/[A-Za-z0-9._-]+\//, "an absolute Linux home path"],
  [/[A-Za-z]:\\Users\\/, "an absolute Windows home path"],
  [/\bnpm_[A-Za-z0-9]{36}\b/, "an npm token"],
  [/\bgh[pousr]_[A-Za-z0-9]{36,}\b/, "a GitHub token"],
  [/\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{32,}/, "an API key"],
  [/-----BEGIN [A-Z ]*PRIVATE KEY-----/, "a private key"],
];

function fail(problems) {
  for (const p of problems) console.error(`check_package: ${p}`);
  process.exit(1);
}

function walk(dir, base = dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...walk(full, base));
    else out.push(relative(base, full).split(sep).join("/"));
  }
  return out;
}

function changelogHasSection(text, version) {
  return text.split("\n").some((line) => line.startsWith(`## [${version}]`));
}

const args = process.argv.slice(2);
let expectVersion = null;
let tarball = null;
for (let i = 0; i < args.length; i += 1) {
  if (args[i] === "--version") expectVersion = String(args[++i] || "");
  else if (!tarball) tarball = resolve(args[i]);
  else fail([`unexpected argument ${args[i]}`]);
}

let root;
let files;
let scratch = null;
if (tarball) {
  scratch = mkdtempSync(join(tmpdir(), "assistant-web-pack-"));
  execFileSync("tar", ["-xzf", tarball, "-C", scratch]);
  const top = readdirSync(scratch);
  if (top.length !== 1 || top[0] !== "package") fail([`${tarball}: expected a single package/ folder, found ${top.join(", ")}`]);
  root = join(scratch, "package");
  files = walk(root);
} else {
  root = WEB_DIR;
  const out = execFileSync("npm", ["pack", "--dry-run", "--json", "--ignore-scripts"], { cwd: WEB_DIR, encoding: "utf8" });
  files = JSON.parse(out)[0].files.map((f) => f.path);
}

try {
  const problems = [];
  for (const f of files) {
    if (FORBIDDEN.some((re) => re.test(f))) problems.push(`${f} must not be published`);
    else if (!ALLOWED.some((re) => re.test(f))) problems.push(`${f} is outside the package allow-list`);
  }
  for (const f of REQUIRED) if (!files.includes(f)) problems.push(`${f} is missing (run npm run build first?)`);
  if (!files.some((f) => /^dist\/assets\/.+\.js$/.test(f))) problems.push("dist/assets has no JavaScript bundle (run npm run build first?)");

  for (const f of files.filter((name) => TEXT.test(name))) {
    const text = readFileSync(join(root, f), "utf8");
    for (const [re, what] of LEAKS) if (re.test(text)) problems.push(`${f} contains ${what}`);
  }

  const pkg = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
  if (pkg.name !== PACKAGE_NAME) problems.push(`package name is ${pkg.name}, expected ${PACKAGE_NAME}`);
  if (pkg.private) problems.push("package.json is marked private");
  if (expectVersion !== null && pkg.version !== expectVersion) problems.push(`package version is ${pkg.version}, expected ${expectVersion}`);
  if (files.includes("CHANGELOG.md") && !changelogHasSection(readFileSync(join(root, "CHANGELOG.md"), "utf8"), pkg.version)) {
    problems.push(`CHANGELOG.md has no "## [${pkg.version}]" section`);
  }

  if (problems.length) fail(problems);
  console.log(`check_package: OK, ${pkg.name}@${pkg.version}, ${files.length} files`);
  for (const f of [...files].sort()) console.log(`  ${f}`);
} finally {
  if (scratch) rmSync(scratch, { recursive: true, force: true });
}

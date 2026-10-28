#!/usr/bin/env node
// Layout check of the BUILT app in headless Chromium against a fake gateway
// (no network, no real gateway). Fails (exit 1) when, at any of the widths
// below, the page scrolls sideways (documentElement.scrollWidth >
// clientWidth), a control of the composer is off screen, or a visible
// button is smaller than 44 px — with a long conversation title, the case
// that broke at 420/760/1024/1280 (adversary finding 1).
//
// Usage: node scripts/check_layout.mjs [--shots <dir>]   (after `npm run build`)
import { existsSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

import { createAssistantServer } from "../bin/server.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
if (!existsSync(join(root, "dist", "index.html"))) throw new Error("check_layout: dist/ is missing — run npm run build first");
const shotsArg = process.argv.indexOf("--shots");
const shots = shotsArg > 0 ? resolve(process.argv[shotsArg + 1]) : "";
if (shots) mkdirSync(shots, { recursive: true });

const LONG =
  "Please read the whole quarterly planning document and tell me, section by section, what changed since the previous version, with a list of every owner and deadline, and also https://example.org/a/very/long/path/that/does/not/break/anywhere/at/all/because/it/is/one/word";
const sessions = [
  { run_id: "r1", session_id: "s1", session_kind: "chat", status: "completed", created_at: "2026-10-26T08:00:00Z", updated_at: "2026-10-26T09:00:00Z" },
  { run_id: "r2", session_id: "s2", session_kind: "chat", status: "waiting", created_at: "2026-10-25T08:00:00Z", updated_at: "2026-10-25T09:00:00Z" },
];
const titles = { r1: LONG, r2: "Short" };
const bundle = {
  warnings: [],
  session: {
    turns: [
      { run_id: "r1", status: "completed", created_at: "2026-10-26T08:00:00Z", prompt: LONG, answer: "Here is the list:\n\n```\n" + "x".repeat(300) + "\n```\n\nDone." },
      { run_id: "r0", status: "failed", created_at: "2026-10-26T07:00:00Z", prompt: "Before", answer: "The provider could not be reached." },
    ],
  },
};
const json = (body, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
/** A small replay_view_v1 of a finished turn (AbstractGateway >= 0.17.0 serves it). */
function viewFor(runId) {
  const order = (ts, seq) => [ts, runId, seq];
  return {
    version: "replay_view_v1", root_run_id: runId, workflow: { id: "basic-agent@0.0.5:main", bundle_id: "basic-agent", bundle_version: "0.0.5", flow_id: "main", entrypoint: "main" },
    session_id: "s1", status: "completed", display_status: null,
    cursor: { token: `${runId}:2~d1`, records: 2, runs: { [runId]: 2 } },
    runs: [{ run_id: runId, parent_run_id: null, status: "completed", depth: 0, order: ["", "", 0, runId], waiting: null, holds_interaction: false }],
    interaction: null, open_waits: [],
    messages: [
      { id: `${runId}:input`, role: "user", kind: "prompt", text: titles[runId] || "Hello", run_id: runId, step_ids: [], seqs: [], source: "run_input", artifact_ids: [], order: order("2026-10-26T08:00:00Z", 0) },
      { id: `${runId}:final`, role: "assistant", kind: "final", text: "Here is the list:\n\n```\n" + "x".repeat(300) + "\n```\n\nDone.", run_id: runId, step_ids: ["done"], seqs: [2], source: "ledger", artifact_ids: [], order: order("2026-10-26T09:00:00Z", 2) },
    ],
    activities: [{ id: `${runId}:t1`, run_id: runId, execution_id: "t1", node_id: "act", kind: "tool", effect_type: "tool_calls", name: "fetch_url", status: "completed", started_at: "2026-10-26T08:30:00Z", ended_at: "2026-10-26T08:31:00Z", seqs: [1], step_ids: ["t1"], order: order("2026-10-26T08:30:00Z", 1), tool_calls: [{ id: "c1", name: "fetch_url", arguments: { url: "https://example.org/a/very/long/path/that/does/not/break/anywhere/at/all" }, status: "completed", output: "ok" }] }],
    artifacts: [], usage: { input_tokens: 10, output_tokens: 20, total_tokens: 30, llm_calls: 1 }, warnings: [],
  };
}
const seen = { history: 0, view: 0 };
function answer(path, mode) {
  if (path === "api/connection/gateway") return json({ ok: true, has_session: true, gateway_url: "http://fake", gateway: { ok: true, principal: { user_id: "demo" } } });
  if (path.startsWith("api/gateway/runs?")) return json({ items: sessions, has_more: false });
  let m = /^api\/gateway\/runs\/([^/?]+)\/input_data/.exec(path);
  if (m) return json({ input_data: { prompt: titles[m[1]] || "" } });
  // "ledger_fold": a gateway before 0.17.0 (no view route: FastAPI's unmatched-route answer), so
  // the chat folds the ledger, labeled. "replay_view": AbstractGateway >= 0.17.0 serves the view.
  m = /^api\/gateway\/runs\/([^/?]+)\/view$/.exec(path);
  if (m) { seen.view += 1; return mode === "replay_view" ? json(viewFor(m[1])) : json({ detail: "Not Found" }, 404); }
  if (/^api\/gateway\/runs\/[^/?]+\/view\/stream$/.test(path)) return mode === "replay_view" ? { status: 200, contentType: "text/event-stream", body: "event: done\ndata: {}\n\n" } : json({ detail: "Not Found" }, 404);
  if (/^api\/gateway\/runs\/[^/?]+\/history_bundle/.test(path)) { seen.history += 1; return json(bundle); }
  if (/^api\/gateway\/runs\/[^/?]+\/ledger\/stream/.test(path)) return { status: 200, contentType: "text/event-stream", body: "" };
  if (/^api\/gateway\/runs\/[^/?]+\/ledger/.test(path)) return json({ items: [], next_after: 0 });
  m = /^api\/gateway\/runs\/([^/?]+)$/.exec(path);
  if (m) return json({ run_id: m[1], status: "completed", session_id: "s1" });
  if (path.startsWith("api/gateway/discovery/tools")) return json({ items: [] });
  if (path.startsWith("api/gateway/discovery/capabilities")) return json({ capabilities: {} });
  if (path.startsWith("api/gateway/voice/defaults")) return json({ tts: { configured: true, provider: "piper", model: "en_US-amy" }, stt: { configured: true, provider: "faster-whisper", model: "large-v3" }, source: "gateway" });
  if (path.startsWith("api/gateway/voice/voices")) return json({ items: [] });
  if (path.startsWith("api/gateway/me/events/stream")) return { status: 200, contentType: "text/event-stream", body: "" };
  if (path.startsWith("api/gateway/me/events")) return json({ events: [], head: 0, next_after: 0, more: false });
  return json({ detail: `fake gateway: no route for ${path}` }, 404);
}

const server = createAssistantServer({ defaultGatewayUrl: "http://127.0.0.1:9" });
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}/`;
const browser = await chromium.launch();
const failures = [];
try {
  for (const mode of ["ledger_fold", "replay_view"]) {
  for (const [w, h] of [[420, 700], [760, 700], [1024, 768], [1280, 900]]) {
    for (const scheme of ["light", "dark"]) {
      seen.history = 0; seen.view = 0;
      // Below 1024 px: a touch device (coarse pointer), where every target must reach 44 px.
      // From 1024 px: a mouse; the kit sizes its own controls for a fine pointer there, and
      // the 44 px rule covers the app's own controls (.aa-*).
      const touch = w < 1024;
      const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme, hasTouch: touch, isMobile: touch });
      await ctx.route("**/api/**", (route) => {
        const u = new URL(route.request().url());
        return route.fulfill(answer(u.pathname.slice(1) + u.search, mode));
      });
      const page = await ctx.newPage();
      const errors = [];
      page.on("pageerror", (e) => errors.push(String(e)));
      await page.goto(base);
      if (w < 1024) {
        await page.getByRole("button", { name: "Open Conversations" }).click();
        await page.locator(".aa-session").first().waitFor();
        if (shots) await page.screenshot({ path: join(shots, `list-${w}x${h}-${scheme}.png`) });
      }
      await page.locator(".aa-session").first().click();
      await page.locator(".pc-chat-item--user").first().waitFor();
      await page.waitForTimeout(150);
      const m = await page.evaluate(() => {
        const vw = window.innerWidth;
        const visible = (e) => {
          const r = e.getBoundingClientRect();
          const st = getComputedStyle(e);
          return r.width > 0 && r.height > 0 && st.visibility !== "hidden" && st.display !== "none";
        };
        const coarse = matchMedia("(pointer: coarse)").matches;
        const boxes = [...document.querySelectorAll("button, a[href]")].filter(visible).map((b) => {
          const r = b.getBoundingClientRect();
          const own = Boolean(b.closest("[class*='aa-']")) && !b.closest("[class*='pc-'], [class*='af-']");
          return { t: (b.getAttribute("aria-label") || b.textContent || "").trim().slice(0, 24), w: Math.round(r.width), h: Math.round(r.height), left: Math.round(r.left), right: Math.round(r.right), sized: coarse || own };
        });
        // Blocks of the conversation must sit inside the viewport too: a
        // scrolling container (the thread) can hide an overflow from the page.
        const blocks = [...document.querySelectorAll(".aa-chat__header, .aa-chat__notes, .pc-chat-item, .pc-workflow-interaction, .pc-composer, .aa-sidebar")]
          .filter(visible)
          .map((e) => ({ t: e.className.split(" ")[0], ...(({ left, right }) => ({ left: Math.round(left), right: Math.round(right) }))(e.getBoundingClientRect()) }))
          .filter((b) => b.right > vw + 0.5 || b.left < -0.5);
        const thread = document.querySelector(".pc-chat-thread");
        return {
          blocks,
          threadOverflow: thread ? thread.scrollWidth - thread.clientWidth : 0,
          sidebarShown: [...document.querySelectorAll(".aa-sidebar")].some(visible),
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
          offscreen: boxes.filter((b) => b.right > vw + 0.5 || b.left < -0.5),
          small: boxes.filter((b) => b.sized && (b.w < 44 || b.h < 44)),
          coarse,
        };
      });
      const tag = `${mode}-${w}x${h}-${scheme}`;
      // The conversation came from where the mode says, and the fallback is labeled.
      const hint = await page.locator(".aa-chat__source").count();
      if (mode === "replay_view" && (seen.history > 0 || seen.view === 0)) failures.push(`${tag}: not rendered from the replay view (history ${seen.history}, view ${seen.view})`);
      if (mode === "replay_view" && hint) failures.push(`${tag}: the ledger-fold label shows while the view is used`);
      if (mode === "ledger_fold" && !hint) failures.push(`${tag}: the ledger fold is not labeled`);
      if (touch && !m.coarse) failures.push(`${tag}: the touch emulation did not give a coarse pointer`);
      if (m.scrollWidth > m.clientWidth) failures.push(`${tag}: the page scrolls sideways (scrollWidth ${m.scrollWidth} > clientWidth ${m.clientWidth})`);
      for (const b of m.blocks) failures.push(`${tag}: ${b.t} is outside the viewport (${b.left}..${b.right})`);
      if (m.threadOverflow > 0) failures.push(`${tag}: the conversation scrolls sideways by ${m.threadOverflow} px`);
      // Below 1024 px an open conversation is the whole page: the list is a sheet, closed after picking.
      if (w < 1024 && m.sidebarShown) failures.push(`${tag}: the conversation list is still on screen after opening a conversation`);
      if (w >= 1024 && !m.sidebarShown) failures.push(`${tag}: no conversation list beside the conversation`);
      for (const b of m.offscreen) failures.push(`${tag}: "${b.t}" is off screen (${b.left}..${b.right})`);
      for (const b of m.small) failures.push(`${tag}: "${b.t}" is ${b.w}x${b.h}, under 44 px`);
      for (const e of errors) failures.push(`${tag}: page error ${e}`);
      if (shots) await page.screenshot({ path: join(shots, `conversation-${tag}.png`) });
      // Settings → Voice (a drawer panel): it opens, names the gateway default, and fits.
      await page.getByRole("tab", { name: "Settings" }).click();
      await page.getByRole("heading", { name: "Voice" }).waitFor();
      await page.waitForTimeout(150);
      const settings = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
        text: document.querySelector(".aa-settings")?.textContent || "",
      }));
      if (settings.scrollWidth > settings.clientWidth) failures.push(`${tag}: with Settings open the page scrolls sideways (${settings.scrollWidth} > ${settings.clientWidth})`);
      if (!/Gateway default · piper \/ en_US-amy/.test(settings.text)) failures.push(`${tag}: Settings → Voice does not name the gateway default`);
      if (shots) await page.screenshot({ path: join(shots, `settings-${tag}.png`) });
      console.log(`${tag}: scrollWidth ${m.scrollWidth}/${m.clientWidth}, off screen ${m.offscreen.length}, under 44 px ${m.small.length}`);
      await ctx.close();
    }
  }
  }
} finally {
  await browser.close();
  server.close();
}
if (failures.length) {
  for (const f of failures) console.error(`  FAIL ${f}`);
  process.exit(1);
}
console.log("check_layout: OK");

// Real built UI, virtual microphone and local fake Gateway; no inference or physical audio.
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { chromium } from "playwright";
import { createAssistantServer } from "../bin/server.js";

const server = createAssistantServer({ defaultGatewayUrl: "http://127.0.0.1:9" });
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const base = `http://127.0.0.1:${server.address().port}/`;
let browser;
const audioDir = mkdtempSync(join(tmpdir(), "assistant-voice-feedback-"));
const shotsAt = process.argv.indexOf("--shots");
const shots = shotsAt < 0 ? "" : process.argv[shotsAt + 1];
if (shots) mkdirSync(shots, { recursive: true });
// Alternating quiet/loud PCM exercises the real audio graph. --mute-audio blocks physical output.
const wav = Buffer.alloc(44 + 16000 * 2 * 12);
wav.write("RIFF"); wav.writeUInt32LE(wav.length - 8, 4); wav.write("WAVEfmt ", 8); wav.writeUInt32LE(16, 16);
wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22); wav.writeUInt32LE(16000, 24); wav.writeUInt32LE(32000, 28);
wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34); wav.write("data", 36); wav.writeUInt32LE(wav.length - 44, 40);
for (let i = 0; i < 16000 * 12; i++) {
  const amplitude = Math.floor(i / 12800) % 2 ? .22 : 0;
  wav.writeInt16LE(Math.round(32767 * amplitude * Math.sin(2 * Math.PI * 440 * i / 16000)), 44 + i * 2);
}
const microphoneFile = join(audioDir, "microphone.wav");
writeFileSync(microphoneFile, wav);
const json = (body, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
const runs = new Map([["history", { session_id: "history-session", prompt: "An earlier question", answer: "An earlier answer", status: "completed" }]]);
const calls = { starts: [], speech: 0, recordings: 0, commands: [] };
const report = {};
let failSend = false;
function view(id) {
  const r = runs.get(id);
  const order = (seq) => ["2026-10-31T02:00:00Z", id, seq];
  return {
    version: "replay_view_v1", root_run_id: id, session_id: r.session_id, status: r.status, display_status: null,
    workflow: { id: "assistant@1:main", bundle_id: "assistant", bundle_version: "1", flow_id: "main", entrypoint: "main" },
    cursor: { token: `${id}:2~d1`, records: 2, runs: { [id]: 2 } },
    runs: [{ run_id: id, parent_run_id: null, status: r.status, depth: 0, order: ["", id, 0, id], waiting: null, holds_interaction: false }],
    interaction: r.interaction || null, open_waits: [], activities: [], artifacts: [], warnings: [], usage: {},
    messages: [
      { id: `${id}:input`, role: "user", kind: "prompt", text: r.prompt, run_id: id, order: order(0), step_ids: [], seqs: [], source: "run_input", artifact_ids: [] },
      { id: `${id}:final`, role: "assistant", kind: "final", text: r.answer, run_id: id, order: order(2), step_ids: ["done"], seqs: [2], source: "ledger", artifact_ids: [] },
    ],
  };
}
try {
  browser = await chromium.launch({ args: ["--mute-audio", "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", `--use-file-for-fake-audio-capture=${microphoneFile}`] });
  const servedDocs = await fetch(new URL("llms.txt", base));
  assert.equal(servedDocs.status, 200);
  assert.match(servedDocs.headers.get("content-type"), /^text\/plain/);
  assert.match(await servedDocs.text(), /^# AbstractAssistant in your browser/);
  report.bundledDocs = true;
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, colorScheme: "dark", permissions: ["microphone"] });
  await context.addInitScript(() => {
    window.__avatarFrames = [];
    const instantiate = WebAssembly.instantiate;
    WebAssembly.instantiate = async function (...args) {
      const result = await instantiate.apply(this, args), instance = result.instance ?? result;
      if (!instance.exports.avatar_render) return result;
      const exports = { ...instance.exports, avatar_render(...values) {
        window.__avatarFrames.push({ style: values[1], pose: values[2], level: values[3], time: values[4] });
        if (window.__avatarFrames.length > 1500) window.__avatarFrames.shift();
        return instance.exports.avatar_render(...values);
      } };
      return result.instance ? { module: result.module, instance: { exports } } : { exports };
    };
  });
  await context.addInitScript(() => { document.cookie = "abstractassistant_gateway_csrf=local-test; path=/"; });
  await context.route("**/api/**", async (route) => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname.replace(/^\/api\//, "");
    const body = request.method() === "POST" && request.headers()["content-type"]?.includes("application/json") ? request.postDataJSON() : null;
    let result;
    if (path === "connection/gateway") result = json({ ok: true, has_session: true, gateway_url: "http://fake", gateway: { ok: true, principal: { user_id: "demo" } } });
    else if (path === "gateway/me") result = json({ ok: true, principal: { user_id: "demo" } });
    else if (path === "gateway/runs") result = json({ items: [...runs].map(([id, r]) => ({ run_id: id, session_id: r.session_id, session_kind: "chat", status: r.status, created_at: "2026-10-31T02:00:00Z", updated_at: "2026-10-31T02:00:00Z" })), has_more: false });
    else if (path === "gateway/bundles") result = json({ executable_for: "abstractassistant.agent.v1", items: [], default_agent_workflows: { "abstractassistant.agent.v1": { name: "Assistant" } }, default_agent_workflows_unavailable: {} });
    else if (path === "gateway/accounts/me/preferences") result = json({ preferences: { default_workflow: { "abstractassistant.agent.v1": null } } });
    else if (path === "gateway/docs/corpus" && url.searchParams.get("app") === "assistant-web") result = json({ text: "Assistant documentation: use the microphone to speak and review words before sending." });
    else if (path === "gateway/discovery/tools") result = json({ items: [] });
    else if (path === "gateway/discovery/capabilities") result = json({ capabilities: {} });
    else if (path === "gateway/voice/defaults") result = json({ tts: { configured: true, provider: "piper", model: "demo" }, stt: { configured: true, provider: "whisper", model: "demo" } });
    else if (path === "gateway/voice/voices") result = json({ items: [] });
    else if (path === "gateway/me/events") result = json({ events: [], head: 0, next_after: 0, more: false });
    else if (path === "gateway/attachments/upload") { calls.recordings++; result = json({ attachment: { $artifact: "voice-sample", content_type: "audio/webm" }, run_id: "memory" }); }
    else if (path.endsWith("/audio/transcribe")) { await new Promise((r) => setTimeout(r, 250)); result = json({ text: "Words from the virtual microphone" }); }
    else if (path.endsWith("/voice/tts/stream")) { calls.speech++; result = { status: 200, contentType: "application/x-ndjson", body: JSON.stringify({ type: "segment", audio_b64: wav.toString("base64") }) + '\n{"type":"done"}\n' }; }
    else if (path === "gateway/runs/start") {
      if (failSend) result = json({ detail: "The test Gateway is unavailable" }, 503);
      else { calls.starts.push(body); const id = `new-${calls.starts.length}`; runs.set(id, { session_id: body.session_id, prompt: body.input_data.prompt, answer: "A fresh answer", output: { response: "Use the microphone to speak, then review your words." }, status: "completed" }); result = json({ run_id: id }); }
    } else if (path === "gateway/commands") { calls.commands.push(body); result = json({ accepted: true }); }
    else {
      const m = /^gateway\/runs\/([^/]+)(.*)$/.exec(path), id = m?.[1], suffix = m?.[2];
      if (id && runs.has(id) && suffix === "/view") result = json(view(id));
      else if (id && runs.has(id) && ["/turns", "/history_bundle"].includes(suffix)) result = json({ session: { session_id: runs.get(id).session_id, turns: [{ run_id: id }] } });
      else if (id && runs.has(id) && suffix === "/input_data") result = json({ input_data: { prompt: runs.get(id).prompt } });
      else if (id && runs.has(id) && suffix === "") result = json({ run_id: id, ...runs.get(id) });
      else if (path.endsWith("/stream")) result = { status: 200, contentType: "text/event-stream", body: "" };
      else result = json({ detail: `Unexpected test route: ${path}` }, 404);
    }
    await route.fulfill(result);
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(base);
  await page.getByRole("heading", { name: "Ready when you are" }).waitFor();
  await page.waitForFunction(() => document.querySelector(".aa-orb")?.width > 0);
  if (shots) await page.screenshot({ path: `${shots}/home-desktop.png` });
  // Opening history remains silent, even with Read aloud on.
  await page.getByRole("button", { name: "Read new replies aloud" }).click();
  await page.locator(".aa-session").click();
  await page.getByText("An earlier answer", { exact: true }).waitFor();
  assert.equal(calls.speech, 0);
  report.historySilent = true;
  // One accessible orb owns the existing microphone pipeline, including transcription after stop.
  await page.getByRole("button", { name: "Tap the orb to talk" }).click();
  await page.getByRole("heading", { name: "Listening", exact: true }).waitFor();
  await page.waitForTimeout(2600);
  const listening = await page.evaluate(() => window.__avatarFrames.filter((f) => f.pose === 3).map((f) => f.level));
  assert.ok(Math.max(...listening) > .2 && Math.max(...listening) - Math.min(...listening) > .15, `Microphone amplitude reaches Listening frames: ${listening}`);
  assert.equal(Math.min(...listening), 0, "Microphone silence stays zero");
  report.microphoneDrivesAvatar = true;
  report.microphoneLevelRange = [Math.min(...listening), Math.max(...listening)];
  await page.getByRole("button", { name: "Recording — tap to stop" }).click();
  await page.getByRole("textbox", { name: "Message" }).waitFor();
  await page.waitForFunction(() => document.querySelector("textarea")?.value.includes("Words from the virtual microphone"));
  assert.equal(calls.recordings, 1);
  assert.equal(calls.starts.length, 0);
  report.dictationReview = true;
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await page.getByText("A fresh answer", { exact: true }).waitFor();
  await page.getByRole("heading", { name: "Speaking", exact: true }).waitFor();
  assert.equal(calls.speech, 1);
  report.newReplyReadOnce = true;
  await page.waitForTimeout(1800);
  const speaking = await page.evaluate(() => window.__avatarFrames.filter((f) => f.pose === 4).map((f) => f.level));
  assert.ok(Math.max(...speaking) > .2 && Math.max(...speaking) - Math.min(...speaking) > .15, `Played amplitude reaches Speaking frames: ${speaking}`);
  assert.equal(Math.min(...speaking), 0, "Playback silence stays zero");
  report.playbackDrivesAvatar = true;
  report.playbackLevelRange = [Math.min(...speaking), Math.max(...speaking)];
  await page.getByRole("button", { name: "Assistant settings", exact: true }).click();
  await page.getByRole("slider", { name: "Reply volume", exact: true }).press("Home");
  await page.keyboard.press("Escape");
  await page.waitForTimeout(250);
  assert.equal(await page.evaluate(() => window.__avatarFrames.at(-1).level), 0, "Zero reply volume silences the visual envelope");
  await page.getByRole("button", { name: "Assistant settings", exact: true }).click();
  await page.getByRole("slider", { name: "Reply volume", exact: true }).press("End");
  await page.keyboard.press("Escape");
  await page.waitForTimeout(100);
  const unmuteAt = await page.evaluate(() => window.__avatarFrames.length);
  await page.waitForTimeout(1700);
  assert.ok(await page.evaluate((from) => window.__avatarFrames.slice(from).some((f) => f.pose === 4 && f.level > .2), unmuteAt), "Restoring volume restores the real envelope");
  report.outputVolumeDrivesAvatar = true;

  await page.getByRole("button", { name: "Pause reply", exact: true }).last().click();
  await page.getByRole("heading", { name: "Paused", exact: true }).waitFor();
  await page.getByRole("button", { name: "Resume reply", exact: true }).last().click();
  await page.getByRole("heading", { name: "Speaking", exact: true }).waitFor();
  assert.equal(calls.speech, 1, "Resuming must reuse the selected reply audio");
  // A send failure keeps the draft but still interrupts the previous speech immediately.
  failSend = true;
  await page.getByRole("textbox", { name: "Message" }).fill("Keep my draft");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await page.getByRole("alert").filter({ hasText: "The test Gateway is unavailable" }).waitFor();
  assert.equal(await page.getByRole("textbox", { name: "Message" }).inputValue(), "Keep my draft");
  assert.equal(await page.getByRole("heading", { name: "Speaking", exact: true }).count(), 0);
  report.sendStopsSpeechAndKeepsFailedDraft = true;
  await page.getByRole("button", { name: "Speak (TTS)", exact: true }).click();
  await page.getByRole("heading", { name: "Speaking", exact: true }).waitFor();
  await page.locator('[data-toolbar="new"]').click();
  await page.getByRole("heading", { name: "What’s on your mind?" }).waitFor();
  assert.equal(await page.getByRole("textbox", { name: "Message" }).inputValue(), "");
  assert.equal(await page.getByRole("heading", { name: "Speaking", exact: true }).count(), 0);
  report.newConversationStopsSpeech = true;
  // Shared catalog, immediate selection, state previews and persisted preference.
  await page.getByRole("button", { name: "Assistant settings", exact: true }).click();
  // Every design comes from the same bundled generator and can be selected.
  const picker = page.getByLabel("Avatar", { exact: true });
  await page.waitForFunction(() => document.querySelector('#assistant-avatar-design')?.options.length === 44);
  const designs = await picker.locator("option").evaluateAll(options => options.map(option => option.value));
  assert.equal(new Set(designs).size,44);
  for (const design of designs) {
    await picker.selectOption(design);
    for (const phase of ["Ready", "Error"]) {
      await page.getByRole("group", { name: "Preview activity states" }).getByRole("button", { name: phase, exact: true }).click();
      await page.getByRole("img", { name: `Preview · ${phase.toLowerCase()}`, exact: true }).waitFor();
      await page.waitForTimeout(40);
      assert.ok(await page.locator(".aa-avatar-preview canvas").evaluate((c) => c.getContext("2d").getImageData(0, 0, c.width, c.height).data.some((v, i) => i % 4 === 3 && v > 0)), `${design}/${phase} paints visible pixels`);
    }
  }
  report.avatarCatalogDesigns = designs.length;
  for (const design of ["watch-halo", "watch-vortex", "watch-nebula", "watch-rings", "watch-liquid", "watch-galaxy", "iphone-weave"]) {
    await picker.selectOption(design);
    for (const phase of ["Ready", "Listening", "Thinking", "Working", "Speaking", "Waiting", "Error"]) {
      await page.getByRole("group", { name: "Preview activity states" }).getByRole("button", { name: phase, exact: true }).click();
      await page.getByRole("img", { name: `Preview · ${phase.toLowerCase()}`, exact: true }).waitFor();
      await page.waitForTimeout(60);
      assert.ok(await page.locator(".aa-avatar-preview canvas").evaluate((c) => c.getContext("2d").getImageData(0, 0, c.width, c.height).data.some((v, i) => i % 4 === 3 && v > 0)), `${design}/${phase} paints visible pixels`);
    }
    await page.getByRole("group", { name: "Preview activity states" }).getByRole("button", { name: "Speaking", exact: true }).click();
    await page.waitForTimeout(900);
    if (shots) await page.screenshot({ path: `${shots}/${design}.png` });
  }
  await picker.selectOption("watch-halo");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.waitForTimeout(200);
  const appleStill = await page.locator(".aa-avatar-preview canvas").evaluate((c) => c.toDataURL());
  await page.waitForTimeout(400);
  assert.equal(await page.locator(".aa-avatar-preview canvas").evaluate((c) => c.toDataURL()), appleStill);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  // A hidden preview must release its animation clock and resume when visible.
  await page.locator(".aa-avatar-preview canvas").evaluate((canvas) => {
    canvas._frames = 0;
    const original = CanvasRenderingContext2D.prototype.putImageData;
    window._restoreAvatarCounter = () => { CanvasRenderingContext2D.prototype.putImageData = original; };
    CanvasRenderingContext2D.prototype.putImageData = function (...args) {
      if (this.canvas === canvas) canvas._frames++;
      return original.apply(this, args);
    };
  });
  await page.waitForTimeout(250);
  const frames = () => page.locator(".aa-avatar-preview canvas").evaluate((c) => c._frames);
  assert.ok(await frames() > 0, "Visible Apple preview animates");
  await page.locator(".aa-avatar-preview").evaluate((el) => { el.style.visibility = "hidden"; el.style.position = "absolute"; el.style.top = "-10000px"; });
  await page.waitForTimeout(150);
  const hiddenFrames = await frames();
  await page.waitForTimeout(250);
  assert.equal(await frames(), hiddenFrames, "Offscreen preview stops its clock");
  await page.locator(".aa-avatar-preview").evaluate((el) => { el.style.visibility = ""; el.style.position = ""; el.style.top = ""; });
  await page.waitForTimeout(250);
  assert.ok(await frames() > hiddenFrames, "Visible preview resumes");
  await page.evaluate(() => window._restoreAvatarCounter());
  report.appleCatalogPhasesAndReducedMotion = true;
  await page.getByLabel("Avatar", { exact: true }).selectOption("hover");
  for (const phase of ["Ready", "Listening", "Thinking", "Working", "Speaking", "Waiting", "Error"]) {
    await page.getByRole("group", { name: "Preview activity states" }).getByRole("button", { name: phase, exact: true }).click();
    await page.getByRole("img", { name: `Preview · ${phase.toLowerCase()}`, exact: true }).waitFor();
  }
  await page.getByRole("img", { name: "Preview · error", exact: true }).waitFor();
  await page.waitForFunction(() => {
    const canvas = document.querySelector('.aa-avatar-preview canvas');
    const pixels = canvas?.getContext("2d")?.getImageData(0, 0, canvas.width, canvas.height).data;
    if (!pixels) return false;
    for (let i = 0; i < pixels.length; i += 4) if (pixels[i] > 160 && pixels[i] > 2 * pixels[i + 1] && pixels[i] > 2 * pixels[i + 2]) return true;
    return false;
  });
  assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem("abstractassistant.companion")).design), "hover");
  if (shots) await page.screenshot({ path: `${shots}/avatar-preview.png` });
  report.avatarSelectionAndPreview = true;
  await page.keyboard.press("Escape");
  assert.equal(await page.getByRole("heading", { name: "Make it yours" }).isVisible(), false);
  assert.equal(await page.evaluate(() => document.activeElement?.getAttribute("aria-label")), "Assistant settings");
  report.drawerKeyboardRecovery = true;
  await page.reload();
  await page.getByRole("heading", { name: "Ready when you are" }).waitFor();
  assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem("abstractassistant.companion")).design), "hover");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.waitForTimeout(600);
  const still = await page.locator(".aa-orb").evaluate((el) => el.toDataURL());
  await page.waitForTimeout(600);
  assert.equal(await page.locator(".aa-orb").evaluate((el) => el.toDataURL()), still);
  report.reducedMotion = true;
  await page.setViewportSize({ width: 420, height: 800 });
  await page.getByRole("button", { name: "Open Conversations", exact: true }).waitFor();
  if (shots) await page.screenshot({ path: `${shots}/home-phone.png` });
  const composerBox = await page.getByRole("textbox", { name: "Message", exact: true }).boundingBox();
  assert.ok(composerBox && composerBox.y >= 0 && composerBox.y + composerBox.height <= 800, "Phone composer must stay on screen");
  await page.getByRole("button", { name: "Open Conversations", exact: true }).click();
  await page.getByRole("textbox", { name: "Search conversations" }).fill("No such conversation");
  await page.getByText("No conversations match.", { exact: true }).waitFor();
  await page.keyboard.press("Escape");
  report.phoneComposerAndConversationSearch = true;
  const waiting = runs.get("history");
  waiting.status = "waiting";
  waiting.interaction = { kind: "tool_approval", run_id: "history", wait_key: "approval:1", step_id: "tool-1", seq: 3,
    prompt: "Read a document?", tool_calls: [{ name: "read_file", arguments: { path: "notes.txt" } }], details: null,
    command: { type: "resume", run_id: "history", payload: { wait_key: "approval:1" } }, answer_payload: "{approved: true|false}" };
  await page.reload();
  await page.getByRole("button", { name: "Open Conversations", exact: true }).click();
  await page.locator(".aa-session").filter({ hasText: "An earlier question" }).click();
  await page.getByRole("heading", { name: "Needs you", exact: true }).waitFor();
  await page.getByRole("button", { name: "Allow once", exact: true }).waitFor();
  const approvalBox = await page.getByRole("button", { name: "Allow once", exact: true }).boundingBox();
  assert.ok(approvalBox && approvalBox.x >= 0 && approvalBox.x + approvalBox.width <= 420);
  if (shots) await page.screenshot({ path: `${shots}/approval-phone.png` });
  await page.getByRole("button", { name: "Decide later", exact: true }).click();
  assert.equal(calls.commands.length, 0, "Deferring an approval must not authorize or deny it");
  await page.getByRole("button", { name: "Review", exact: true }).click();
  await page.getByRole("button", { name: "Allow once", exact: true }).waitFor();
  report.phoneApprovalAndDefer = true;
  // The Docs panel fills its drawer; the composer is anchored at the bottom on both sizes.
  failSend = false;
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Docs assistant", exact: true }).click();
  for (const width of [420, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    const docsInput = page.getByPlaceholder("Ask about the Assistant…");
    await docsInput.waitFor();
    const box = await docsInput.boundingBox();
    assert.ok(box && box.y > 650 && box.y + box.height < 900, `Docs composer fills height at ${width}`);
    assert.doesNotMatch(await page.locator("body").innerText(), /docs\/corpus|llms\.txt|docs-qa/);
    if (shots) await page.screenshot({ path: `${shots}/docs-${width}.png` });
  }
  await page.getByPlaceholder("Ask about the Assistant…").fill("How do I speak?");
  await page.locator(".pc-docs-assistant").getByRole("button", { name: "Send", exact: true }).click();
  await page.getByText("Use the microphone to speak, then review your words.", { exact: true }).waitFor();
  await page.getByRole("button", { name: "New conversation", exact: true }).click();
  await page.getByText("Ask anything about AbstractAssistant.", { exact: true }).waitFor();
  report.docsLayoutAndQuestion = true;
  assert.deepEqual(errors, []);
  report.javascriptErrors = 0;
  console.log(JSON.stringify(report));
} finally { await browser?.close(); server.close(); rmSync(audioDir, { recursive: true, force: true }); }

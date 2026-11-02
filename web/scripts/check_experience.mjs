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
const sharedReads = new Map();
const calls = { starts: [], speech: 0, recordings: 0, commands: [] };
const report = {};
const avatarCheck = process.argv.includes("--avatar");
let failSend = false;
let failWaits = false;
const failViews = new Set();
function view(id) {
  const r = runs.get(id);
  const order = (seq) => ["2026-10-31T02:00:00Z", id, seq];
  return {
    version: "replay_view_v1", root_run_id: id, session_id: r.session_id, status: r.status, display_status: null,
    workflow: { id: "assistant@1:main", bundle_id: "assistant", bundle_version: "1", flow_id: "main", entrypoint: "main" },
    cursor: { token: `${id}:${2+(r.public_updates?.length||0)}~d1`, records: 2+(r.public_updates?.length||0), runs: { [id]: 2+(r.public_updates?.length||0) } },
    runs: [{ run_id: id, parent_run_id: null, status: r.status, depth: 0, order: ["", id, 0, id], waiting: null, holds_interaction: false }, ...(r.child_runs || []).map(child => ({run_id:child,parent_run_id:id,status:r.status,depth:1,order:["",id,1,child],waiting:null,holds_interaction:false}))],
    interaction: r.interaction || null, open_waits: [], activities: [], artifacts: id === "history" ? [{id:"answer-file",run_id:id,path:"output.attachments[0]"},{id:"scratchpad-file",run_id:id,path:"output.scratchpad.steps"},{id:"session-file",run_id:id,path:"output.session.artifacts[0]"}] : [], warnings: [], usage: {},
    messages: [
      ...(r.public_updates || []).map((u, i) => ({ id: u.id, role: "assistant", kind: "public_update", text: u.text, run_id: u.run_id || id, source: "emit_event", source_call_ids: [], order: order(i+1), step_ids: [], seqs: [i+1], artifact_ids: [] })),
      { id: `${id}:input`, role: "user", kind: "prompt", text: r.prompt, run_id: id, order: order(0), step_ids: [], seqs: [], source: "run_input", artifact_ids: [] },
      { id: `${id}:final`, role: "assistant", kind: "final", text: r.answer, run_id: id, order: order(2), step_ids: ["done"], seqs: [2], source: "ledger", artifact_ids: id === "history" ? ["answer-file","scratchpad-file","session-file"] : [] },
    ],
  };
}
async function checkAvatar({page, runs, calls, report, shots}) {
  await page.getByRole("heading", { name: "Ready when you are" }).waitFor();
  await page.locator(".aa-session").click();
  await page.getByText("An earlier answer", {exact:true}).waitFor();
  const composer = page.getByRole("textbox", {name:"Message",exact:true});
  await composer.fill("Keep this draft while switching views");
  await page.getByRole("button", {name:"Avatar",exact:true}).click();
  await page.getByRole("region", {name:"Avatar conversation",exact:true}).waitFor();
  assert.equal(await composer.inputValue(),"Keep this draft while switching views");
  assert.equal(calls.speech,0);
  await page.getByRole("button", {name:"Conversation history",exact:true}).click();
  await page.getByRole("list",{name:"Public conversation history"}).getByText("An earlier answer",{exact:true}).waitFor();
  await page.getByRole("button", {name:"Conversation history",exact:true}).click();
  report.defaultHistoryAndDraftPreserved = true;
  await page.locator('[data-toolbar="new"]').click();
  await composer.fill("Find a place for lunch");
  await page.getByRole("button", {name:"Send",exact:true}).click();
  await page.waitForFunction(() => document.querySelector('.pc-avatar-conversation')?.dataset.state === 'working');
  assert.equal(calls.starts.length,1);
  assert.equal(calls.starts[0].conversation,true);
  const live = runs.get("new-1");
  live.child_runs = ["actor-child-1"];
  live.public_updates = [{id:"new-1:public:1",run_id:"actor-child-1",text:"I found a quiet restaurant near the park."}];
  live.answer = "";
  await page.reload();
  await page.locator(".aa-session").filter({hasText:"Find a place for lunch"}).click();
  const subtitles = page.getByLabel("Public subtitles",{exact:true});
  await subtitles.getByText("I found a quiet restaurant near the park.",{exact:true}).waitFor();
  assert.equal(calls.speech,0,"Restoring an existing update stays silent");
  await page.getByRole("button", {name:"Read new replies aloud",exact:true}).click();
  live.public_updates.push({id:"new-1:public:2",text:"I am keeping the riverside option while I check access."});
  await page.getByRole("button",{name:"Pause voice",exact:true}).waitFor();
  const synthesisCount = calls.speech;
  assert.equal(synthesisCount,1);
  await page.getByRole("button",{name:"Pause voice",exact:true}).click();
  await page.getByRole("button",{name:"Resume voice",exact:true}).waitFor();
  await page.getByRole("button",{name:"Resume voice",exact:true}).click();
  await page.getByRole("button",{name:"Pause voice",exact:true}).waitFor();
  assert.equal(calls.speech,synthesisCount,"Resuming a narrated brève reuses its active speech key/audio");
  await page.waitForFunction(()=>window.__avatarFrames.some(f=>f.pose===4 && f.level>.2));
  await page.getByRole("button",{name:"Silence voice",exact:true}).click();
  await page.getByRole("button",{name:"Read new replies aloud",exact:true}).click();
  report.busyPublicNarrationPauseResumeAndSpeakingPose = true;
  await page.getByRole("button", {name:"Conversation history",exact:true}).click();
  const update = page.getByRole('list', {name:'Public conversation history'}).getByRole('listitem').filter({hasText:'I found a quiet restaurant near the park.'});
  await update.getByRole('button',{name:'Reply to this',exact:true}).click();
  await composer.fill("Please keep the other restaurant too; it has wheelchair access.");
  await page.getByRole("button", {name:"Send",exact:true}).click();
  assert.equal(calls.commands.length,1);
  assert.equal(calls.commands[0].type,"inject_guidance");
  assert.match(JSON.stringify(calls.commands[0]),/wheelchair access/);
  assert.match(JSON.stringify(calls.commands[0]),/new-1:public:1/);
  assert.match(calls.commands[0].payload.guidance,/"run_id":"actor-child-1"/,"Replying to a public update preserves the actual actor child identity");
  report.activeReplyUsesGuidanceAndPinnedPublicContext = true;
  live.status = "waiting";
  live.interaction = {kind:"ask_user",run_id:"new-1",wait_key:"question:q1",step_id:"ask",seq:4,prompt:"Would you prefer lunch before one?",choices:[],allow_free_text:true,
    details:{question:{id:"q1",purpose:"conversation",importance:"essential",published_at:"2026-11-01T12:00:00Z",deadline:null,fallback:null}},
    command:{type:"resume",run_id:"new-1",payload:{wait_key:"question:q1"}},answer_payload:"{response: string}"};
  await page.reload();
  await page.locator(".aa-session").filter({hasText:"Find a place for lunch"}).click();
  await page.getByText("Would you prefer lunch before one?",{exact:true}).waitFor();
  await composer.fill("Yes, before one please.");
  await page.getByRole("button",{name:"Send",exact:true}).click();
  const answer = calls.commands.at(-1);
  assert.equal(answer.type,"resume");
  assert.equal(answer.payload.wait_key,"question:q1");
  assert.equal(answer.payload.payload.response,"Yes, before one please.");
  assert.equal(answer.payload.payload.approved,undefined);
  report.activeQuestionAnswerUsesExactWait = true;
  live.interaction = {kind:"tool_approval",run_id:"new-1",wait_key:"approval:1",step_id:"book",seq:5,prompt:"Reserve this table?",tool_calls:[{name:"reserve_table",arguments:{}}],details:null,command:{type:"resume",run_id:"new-1",payload:{wait_key:"approval:1"}},answer_payload:"{approved: true|false}"};
  await page.reload();
  await page.locator(".aa-session").filter({hasText:"Find a place for lunch"}).click();
  await page.getByRole("button",{name:"Deny",exact:true}).waitFor();
  assert.equal(await page.getByRole("button",{name:"Allow once",exact:true}).count(),0,"An undescribed reservation requires detailed review before approval");
  await composer.fill("I am still thinking about it.");
  const before = calls.commands.length;
  await page.getByRole("button",{name:"Send",exact:true}).click();
  await page.getByText("Use the request controls to answer it. A message does not grant permission.",{exact:false}).waitFor();
  assert.equal(calls.commands.length,before);
  assert.equal(await composer.inputValue(),"I am still thinking about it.");
  report.messageNeverApprovesAndFailedDraftPreserved = true;
  await page.setViewportSize({width:420,height:900});
  if(shots) await page.screenshot({path:`${shots}/avatar-approval-phone.png`});
  const sendBox = await page.getByRole("button",{name:"Send",exact:true}).boundingBox();
  assert.ok(sendBox && sendBox.y >= 0 && sendBox.y + sendBox.height <= 900,"Composer remains visible on phone");
  await page.getByRole("button",{name:"Review details",exact:true}).click();
  assert.equal(await composer.inputValue(),"I am still thinking about it.");
  report.defaultViewRestoredWithoutDraftLoss = true;
}
try {
  browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined, args: ["--mute-audio", "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", `--use-file-for-fake-audio-capture=${microphoneFile}`] });
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
      // Record the gaze each frame is drawn with, and the design it is drawn for.
      const e = instance.exports, gazes = new Map();
      const exports = { ...e,
        avatar_set_gaze(handle, x, y) { gazes.set(handle, [x, y]); return e.avatar_set_gaze(handle, x, y); },
        avatar_render(...values) {
          const id = new TextDecoder().decode(new Uint8Array(e.memory.buffer, e.avatar_style_field_ptr(values[1], 0), e.avatar_style_field_len(values[1], 0)));
          window.__avatarFrames.push({ style: values[1], design: id, gaze: gazes.get(values[0]) ?? [0, 0], pose: values[2], level: values[3], time: values[4] });
          if (window.__avatarFrames.length > 1500) window.__avatarFrames.shift();
          return e.avatar_render(...values);
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
    else if (path === "gateway/me/session-reads") {
      if (request.method() === "POST") {
        const items = (body.receipts || []).map(r => {
          const key = JSON.stringify([r.session_id,r.run_id,r.status]);
          if(!sharedReads.has(key)) sharedReads.set(key,{...r,event_id:`read-${sharedReads.size+1}`,sequence:sharedReads.size+1,at:new Date().toISOString()});
          return sharedReads.get(key);
        }); result = json({items,more:false});
      } else { const ids=url.searchParams.getAll("run_id"); result=json({items:[...sharedReads.values()].filter(r=>!ids.length||ids.includes(r.run_id)),more:false}); }
    }
    else if (path === "gateway/runs" && url.searchParams.get("status") === "waiting" && failWaits) result = json({ detail: "Wait listing unavailable" }, 503);
    else if (path === "gateway/runs") result = json({ items: [...runs].map(([id, r]) => ({ run_id: id, session_id: r.session_id, session_kind: "chat", status: r.status, created_at: r.created_at || r.at || "2026-10-31T02:00:00Z", updated_at: r.at || "2026-10-31T02:00:00Z", waiting: r.waiting || (r.interaction ? { reason: "user" } : null), parent_run_id: r.parent_run_id || null, tool_calls: r.tool_calls })), has_more: false });
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
      else { calls.starts.push(body); const id = `new-${calls.starts.length}`; runs.set(id, { session_id: body.session_id, prompt: body.input_data.prompt, answer: "A fresh answer", output: { response: "Use the microphone to speak, then review your words." }, status: avatarCheck ? "running" : "completed" }); result = json({ run_id: id }); }
    } else if (path === "gateway/commands") { calls.commands.push(body); result = json({ accepted: true }); }
    else {
      const m = /^gateway\/runs\/([^/]+)(.*)$/.exec(path), id = m?.[1], suffix = m?.[2];
      if (id && failViews.has(id) && suffix === "/view") result = json({ detail: "History unavailable" }, 503);
      else if (id && runs.has(id) && suffix === "/view") result = json(view(id));
      else if (id && runs.has(id) && ["/turns", "/history_bundle"].includes(suffix)) result = json({ session: { session_id: runs.get(id).session_id, turns: [...runs].filter(([,r]) => r.session_id === runs.get(id).session_id && !r.parent_run_id).map(([run_id]) => ({ run_id })) } });
      else if (id && runs.has(id) && suffix === "/input_data") result = json({ input_data: { prompt: runs.get(id).prompt, ...(id === "history" ? {context:{attachments:[{$artifact:"history-file",filename:"session-note.txt",run_id:"history"}]}} : {}) } });
      else if (id && suffix?.startsWith("/artifacts/")) result = json({tags:{filename:suffix.includes("history-file") ? "session-note.txt" : "answer-file.txt"}});
      else if (id && runs.has(id) && suffix === "") result = json({ run_id: id, ...runs.get(id) });
      else if (path.endsWith("/stream")) { if(avatarCheck) await new Promise(resolve=>setTimeout(resolve,500)); const v=avatarCheck && id && runs.has(id) && suffix === "/view/stream" ? view(id) : null; result = { status: 200, contentType: "text/event-stream", body: v ? `id: ${v.cursor.token}\nevent: view\ndata: ${JSON.stringify(v)}\n\n` : ": heartbeat\n\n" }; }
      else result = json({ detail: `Unexpected test route: ${path}` }, 404);
    }
    await route.fulfill(result);
  });
  const page = await context.newPage();
  if(avatarCheck) page.setDefaultTimeout(10000);
  const errors = [];
  page.on("pageerror", (e) => { errors.push(String(e)); console.error(e.stack || String(e)); });
  await page.goto(base);
  if (avatarCheck) {
    await checkAvatar({page, runs, calls, report, shots});
  } else {
  await page.getByRole("heading", { name: "Ready when you are" }).waitFor();
  await page.waitForFunction(() => document.querySelector(".aa-orb")?.width > 0);
  if (shots) await page.screenshot({ path: `${shots}/home-desktop.png` });
  // The orb (watch-halo, no eyes) never follows the pointer: not the element, not the drawing.
  const orbPlacement = () => page.locator(".aa-orb").evaluate((c) => { const r = c.getBoundingClientRect(); return [r.x, r.y, r.width, r.height, getComputedStyle(c).transform, getComputedStyle(c.parentElement).transform].join(); });
  const orbAt = await orbPlacement();
  await page.evaluate(() => { window.__avatarFrames = []; });
  for (const [x, y] of [[5, 5], [1430, 5], [720, 500], [5, 990], [1430, 990]]) { await page.mouse.move(x, y, { steps: 4 }); await page.waitForTimeout(80); }
  await page.waitForTimeout(300);
  assert.equal(await orbPlacement(), orbAt, "the orb is never translated, rotated or tilted toward the pointer");
  const orbFrames = await page.evaluate(() => window.__avatarFrames);
  assert.ok(orbFrames.some((f) => f.design === "watch-halo"), "the orb kept drawing while the pointer moved");
  assert.deepEqual(orbFrames.filter((f) => f.gaze[0] || f.gaze[1]), [], "a design without eyes receives no gaze target");
  report.orbIgnoresPointer = true;
  // Opening history remains silent, even with Read aloud on.
  await page.getByRole("button", { name: "Read new replies aloud" }).click();
  await page.locator(".aa-session").click();
  await page.getByText("An earlier answer", { exact: true }).waitFor();
  assert.equal(calls.speech, 0);
  await page.locator('.pc-chat-item--user').getByRole('button',{name:'session-note.txt',exact:true}).waitFor();
  await page.locator('.pc-chat-item--assistant').getByRole('button',{name:'answer-file.txt',exact:true}).waitFor();
  report.messageAttachmentsRetained = true;
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
  // The composer's own microphone (the same control as every chat box) stops the recording the orb started: one pipeline, two entry points.
  assert.equal(await page.getByRole("button", { name: "Recording — tap to stop" }).count(), 2, "orb and composer microphones reflect the same recording");
  await page.getByRole("region", { name: "Workflow chat" }).getByRole("button", { name: "Recording — tap to stop" }).click();
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
  await page.getByRole("button", { name: "Speak (TTS)", exact: true }).last().click();
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
  // Only a design with eyes (catalog `gaze: "eyes"`) receives the pointer, as a gaze target.
  for (const [design, eyes] of [["hover", true], ["watch-halo", false]]) {
    await picker.selectOption(design);
    await page.getByRole("group", { name: "Preview activity states" }).getByRole("button", { name: "Ready", exact: true }).click();
    await page.waitForTimeout(2100);
    const preview = await page.locator(".aa-avatar-preview canvas").boundingBox();
    await page.evaluate(() => { window.__avatarFrames = []; });
    for (const [dx, dy] of [[-200, -150], [preview.width + 200, -150], [-200, preview.height + 150]]) { await page.mouse.move(preview.x + dx, preview.y + dy, { steps: 3 }); await page.waitForTimeout(120); }
    const gazed = await page.evaluate(() => window.__avatarFrames.filter((f) => f.gaze[0] || f.gaze[1]).map((f) => f.design));
    if (eyes) assert.ok(gazed.length > 0 && gazed.every((d) => d === design), `${design} (eyes) receives the gaze target: ${gazed}`);
    else assert.deepEqual(gazed, [], `${design} (no eyes) receives no gaze target`);
  }
  report.gazeOnlyForEyes = true;
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
  await page.keyboard.press("Escape");
  const stamp = () => new Date().toISOString();
  runs.set("read-a", { session_id: "read-session", prompt: "A newly unread question", answer: "A newly unread answer", status: "completed", at: stamp(), tool_calls: 4 });
  await page.getByRole("button", { name: "Refresh conversations", exact: true }).click();
  const readCard = page.locator('.af-session-card').filter({ has: page.locator('[data-session-id="read-session"]') });
  await readCard.locator('[data-session-id="read-session"]').waitFor();
  assert.equal(await readCard.getAttribute("data-unread"), "true");
  failViews.add("read-a");
  await readCard.locator('.af-session-card__open').click();
  await page.waitForTimeout(600);
  assert.equal(await readCard.getAttribute("data-unread"), "true", "A failed history load does not consume content");
  failViews.delete("read-a");
  await readCard.locator('.af-session-card__open').click();
  await page.getByText("A newly unread answer", { exact: true }).waitFor();
  await page.waitForTimeout(500);
  assert.equal(await readCard.getAttribute("data-unread"), null, "Loaded, visible content is consumed");
  await page.locator('[data-toolbar="new"]').click();
  runs.set("read-b", { session_id: "read-session", prompt: "A request still running", answer: "", status: "running", at: stamp() });
  await page.getByRole("button", { name: "Refresh conversations", exact: true }).click();
  await page.waitForTimeout(400);
  assert.equal(await readCard.getAttribute("data-unread"), "true");
  await readCard.locator('.af-session-card__open').click();
  await page.getByText("A request still running", { exact: true }).waitFor();
  await page.waitForTimeout(500);
  assert.equal(await readCard.getAttribute("data-unread"), null);
  await page.locator('[data-toolbar="new"]').click();
  Object.assign(runs.get("read-b"), { status: "completed", answer: "The later completed answer", at: stamp() });
  await page.getByRole("button", { name: "Refresh conversations", exact: true }).click();
  await page.waitForTimeout(400);
  assert.equal(await readCard.getAttribute("data-unread"), "true", "Completion remains new after its running request was viewed");
  await readCard.locator('.af-session-card__open').click();
  await page.getByText("The later completed answer", { exact: true }).waitFor();
  await page.waitForTimeout(500);
  assert.equal(await readCard.getAttribute("data-unread"), null);
  // A real child-run human wait highlights its session and survives a failed wait refresh.
  runs.set("read-child", { session_id: "read-session", prompt: "", answer: "", status: "waiting", parent_run_id: "read-b", waiting: { reason: "user" }, at: stamp() });
  await page.getByRole("button", { name: "Refresh conversations", exact: true }).click();
  await page.waitForTimeout(400);
  assert.equal(await readCard.getAttribute("data-attention"), "true");
  failWaits = true;
  await page.getByRole("button", { name: "Refresh conversations", exact: true }).click();
  await page.getByText(/Pending questions and approvals could not be refreshed/).waitFor();
  assert.equal(await readCard.getAttribute("data-attention"), "true");
  failWaits = false; runs.get("read-child").status = "completed";
  await page.getByRole("button", { name: "Refresh conversations", exact: true }).click();
  await page.waitForTimeout(400);
  assert.equal(await readCard.getAttribute("data-attention"), null);
  if (shots) await page.screenshot({ path: `${shots}/read-session.png` });
  // Historical terminal failures have an actual visible outcome, not a prompt receipt.
  await page.locator('[data-toolbar="new"]').click();
  runs.set("historical-failure", { session_id: "failure-session", prompt: "An older request that failed", answer: "", status: "failed", created_at: new Date(Date.now()-1000).toISOString(), at: stamp() });
  runs.set("newer-success", { session_id: "failure-session", prompt: "A newer successful request", answer: "A newer answer", status: "completed", created_at: stamp(), at: stamp() });
  await page.getByRole("button", { name: "Refresh conversations", exact: true }).click();
  const failureCard = page.locator('.af-session-card').filter({ has: page.locator('[data-session-id="failure-session"]') });
  await failureCard.locator('.af-session-card__open').click();
  await page.getByText("Request failed.", { exact: true }).waitFor();
  await page.waitForTimeout(500);
  assert.equal(await failureCard.getAttribute("data-unread"), null, "Viewing an older failure outcome acknowledges that revision");
  report.sessionUnreadConsumptionAndAttention = true;
  assert.deepEqual(errors, []);
  }
  report.javascriptErrors = 0;
  console.log(JSON.stringify(report));
} catch (error) { if (shots && browser) { const p=browser.contexts()[0]?.pages()[0]; if(p) { await p.screenshot({path:`${shots}/failure.png`}); console.error((await p.locator(".aa-chat").innerText()).slice(0,6000)); console.error(JSON.stringify({calls,runs:[...runs]},null,2)); } } throw error; } finally { await browser?.close(); server.close(); rmSync(audioDir, { recursive: true, force: true }); }

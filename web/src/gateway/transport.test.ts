import { describe, expect, it, vi } from "vitest";

import { presentInteraction, WorkflowSessionController, workflowPendingInteraction } from "@abstractframework/panel-chat";

import type { AssistantHost } from "../host";
import { GatewayClient, GatewayHttpError } from "./client";
import { createAssistantTransport } from "./transport";

function host(csrf = "tok"): AssistantHost {
  return {
    kind: "browser",
    gatewayUrl: (route) => `api/gateway/${route}`,
    auth: {
      kind: "app-cookie-session",
      credentials: "same-origin",
      headers: (mutating) => {
        if (!mutating) return {};
        if (!csrf) throw new Error("You are signed out of the gateway");
        return { "X-AbstractAssistant-CSRF": csrf };
      },
    },
    signIn: "app-server-modal",
    capabilities: {
      tray: { available: false, reason: "" },
      globalHotkey: { available: false, reason: "" },
      systemNotifications: { available: false, reason: "" },
      autostart: { available: false, reason: "" },
      microphone: { available: true },
      audioPlayback: { available: true },
    },
  };
}

describe("the workflow transport (panel-chat's controller over this app's gateway calls)", () => {
  it("passes ledger steps as {cursor, record}, valid live frames as deltas, and skips a malformed frame", async () => {
    const client = new GatewayClient(host());
    const errors: string[] = [];
    vi.spyOn(client, "streamLedger").mockImplementation(async (_run, _after, handlers) => {
      handlers.onOpen?.();
      handlers.onStep({ cursor: 3, record: { status: "completed" } });
      handlers.onDelta?.("llm.delta", JSON.stringify({ kind: "llm.delta", run_id: "r", root_run_id: "r", node_id: "n", call_id: "c", seq: 0, text: "Hel", channel: "content", snapshot: false }));
      handlers.onDelta?.("llm.delta", "{not json");
      return { cursor: 3, done: true };
    });
    const t = createAssistantTransport(client, { onDeltaError: (m) => errors.push(m) });
    const steps: unknown[] = [];
    const deltas: unknown[] = [];
    let opened = false;
    await t.streamLedger("r", 0, (s) => steps.push(s), new AbortController().signal, () => (opened = true), (d) => deltas.push(d));
    expect(opened).toBe(true);
    expect(steps).toEqual([{ cursor: 3, record: { status: "completed" } }]);
    expect(deltas).toHaveLength(1);
    expect(errors).toHaveLength(1);
    expect(errors[0]).toMatch(/Malformed llm.delta/);
  });

  it("stamps this app's client id on commands", async () => {
    const client = new GatewayClient(host());
    const sent = vi.spyOn(client, "submitCommand").mockResolvedValue({ accepted: true });
    await createAssistantTransport(client, { onDeltaError: () => {} }).submitCommand({ command_id: "c", run_id: "r", type: "resume", payload: {} });
    expect(sent.mock.calls[0][0]).toMatchObject({ client_id: "abstractassistant-web", type: "resume" });
  });
});

describe("the kit's fetches go through the host", () => {
  it("fetchGateway sends the CSRF twin on a mutation and refuses one when signed out", async () => {
    const calls: Array<[string, RequestInit]> = [];
    vi.stubGlobal("fetch", async (url: string, init: RequestInit) => (calls.push([url, init]), new Response("{}", { status: 200 })));
    await new GatewayClient(host()).fetchGateway("api/gateway/about");
    await new GatewayClient(host()).fetchGateway("api/gateway/runs/start", { method: "POST" });
    expect((calls[0][1].headers as Record<string, string>)["X-AbstractAssistant-CSRF"]).toBeUndefined();
    expect((calls[1][1].headers as Record<string, string>)["X-AbstractAssistant-CSRF"]).toBe("tok");
    expect(calls[1][1].credentials).toBe("same-origin");
    await expect(new GatewayClient(host("")).fetchGateway("api/gateway/runs/start", { method: "POST" })).rejects.toThrow(/signed out/);
    vi.unstubAllGlobals();
  });

  it("policyRequest rejects a non-2xx answer with its status and body (the kit maps a 409)", async () => {
    vi.stubGlobal("fetch", async () => new Response(JSON.stringify({ detail: { reason_code: "revision_conflict" } }), { status: 409 }));
    const err = await new GatewayClient(host()).policyRequest("api/gateway/sessions/s/tool-policy", { method: "POST", body: {} }).catch((e) => e);
    expect(err).toBeInstanceOf(GatewayHttpError);
    expect(err.status).toBe(409);
    expect(err.body).toEqual({ detail: { reason_code: "revision_conflict" } });
    vi.unstubAllGlobals();
  });
});

/** A small replay_view_v1: a child run asks to approve write_file (the 2026-09-29 shape). */
function replayView(token = "root0000:3.child000:2~d1") {
  const call = { name: "write_file", arguments: { file_path: "a.txt", content: "x" }, call_id: "c1" };
  return {
    version: "replay_view_v1",
    root_run_id: "root0000-run",
    workflow: { id: "basic-agent@0.0.5:main", bundle_id: "basic-agent", bundle_version: "0.0.5", flow_id: "main", entrypoint: "main" },
    session_id: "sess-1",
    status: "waiting",
    display_status: null,
    cursor: { token, records: 5, runs: { "root0000-run": 3, "child000-run": 2 } },
    runs: [
      { run_id: "root0000-run", parent_run_id: null, status: "waiting", depth: 0, order: ["", "", 0, "root0000-run"], waiting: { kind: "delegation", wait_key: "subworkflow:child000-run", child_run_id: "child000-run" }, holds_interaction: false },
      { run_id: "child000-run", parent_run_id: "root0000-run", status: "waiting", depth: 1, order: ["", "", 0, "root0000-run", 0, "child000-run"], waiting: { kind: "tool_approval", wait_key: "tool_approval:child000-run:act:i1" }, holds_interaction: true },
    ],
    interaction: {
      kind: "tool_approval", run_id: "child000-run", wait_key: "tool_approval:child000-run:act:i1", step_id: "t1", seq: 2,
      prompt: null, choices: null, allow_free_text: null, details: { mode: "approval_required" }, tool_calls: [call],
      activity_id: "child000-run:t1", command: { type: "resume", run_id: "child000-run", payload: { wait_key: "tool_approval:child000-run:act:i1" } }, answer_payload: "{approved: true|false}",
    },
    open_waits: [],
    messages: [{ id: "root0000-run:input", role: "user", kind: "prompt", text: "write a.txt", run_id: "root0000-run", step_ids: [], seqs: [], source: "run_input", artifact_ids: [], order: ["2026-10-28T10:00:00+00:00", "root0000-run", 0] }],
    activities: [{ id: "child000-run:t1", run_id: "child000-run", execution_id: "t1", node_id: "act", kind: "tool", effect_type: "tool_calls", name: "write_file", status: "waiting", started_at: "2026-10-28T10:00:02+00:00", ended_at: null, seqs: [1, 2], step_ids: ["t1"], order: ["2026-10-28T10:00:02+00:00", "child000-run", 1], tool_calls: [{ id: "c1", name: "write_file", arguments: call.arguments, status: "waiting" }] }],
    artifacts: [],
    usage: { input_tokens: 0, output_tokens: 0, total_tokens: 0, llm_calls: 0 },
    warnings: [],
  };
}

describe("the replay view (panel-chat 0.6.0, AbstractGateway >= 0.17.0)", () => {
  it("reads GET runs/{id}/view and follows /view/stream with Last-Event-ID, through the host", async () => {
    const calls: Array<[string, RequestInit]> = [];
    const view = replayView();
    vi.stubGlobal("fetch", async (url: string, init: RequestInit) => {
      calls.push([url, init]);
      if (url.endsWith("/view")) return new Response(JSON.stringify(view), { status: 200, headers: { ETag: `"${view.cursor.token}"` } });
      return new Response("event: done\ndata: {}\n\n", { status: 200, headers: { "Content-Type": "text/event-stream" } });
    });
    const t = createAssistantTransport(new GatewayClient(host()), { onDeltaError: () => {} });
    expect(t.replayView).toBeDefined();
    const read = await t.replayView!.getView("root0000-run");
    expect(read.notModified).toBe(false);
    const frames: string[] = [];
    await t.replayView!.streamView("root0000-run", { lastEventId: view.cursor.token, signal: new AbortController().signal, onFrame: (f) => frames.push(f.event) });
    expect(calls.map((c) => c[0])).toEqual(["api/gateway/runs/root0000-run/view", "api/gateway/runs/root0000-run/view/stream"]);
    expect((calls[1][1].headers as Record<string, string>)["Last-Event-ID"]).toBe(view.cursor.token);
    expect(calls.every((c) => c[1].credentials === "same-origin")).toBe(true);
    expect(frames).toEqual(["done"]);
    vi.unstubAllGlobals();
  });

  it("the controller renders the conversation from the view: the child's approval, no ledger fold", async () => {
    const view = replayView();
    const urls: string[] = [];
    vi.stubGlobal("fetch", async (url: string, init: RequestInit) => {
      urls.push(url);
      if (url.endsWith("/view")) return new Response(JSON.stringify(view), { status: 200, headers: { ETag: `"${view.cursor.token}"` } });
      if (url.includes("/view/stream") || url.includes("/ledger/stream")) {
        return new Response(new ReadableStream({ start(c) { init.signal?.addEventListener("abort", () => { try { c.close(); } catch { /* closed */ } }); } }), { status: 200, headers: { "Content-Type": "text/event-stream" } });
      }
      if (url.endsWith("runs/root0000-run")) return new Response(JSON.stringify({ run_id: "root0000-run", status: "waiting", session_id: "sess-1" }), { status: 200 });
      return new Response(JSON.stringify({ detail: `unexpected ${url}` }), { status: 500 });
    });
    const ctl = new WorkflowSessionController(createAssistantTransport(new GatewayClient(host()), { onDeltaError: () => {} }));
    await ctl.load("root0000-run");
    await new Promise((r) => setTimeout(r, 20));
    const snap = ctl.getSnapshot();
    expect(snap.source).toBe("replay_view");
    expect(snap.status).toBe("waiting");
    expect(snap.records).toEqual([]);
    const pending = workflowPendingInteraction(snap);
    expect(pending?.runId).toBe("child000-run");
    expect(pending?.wait.wait_key).toBe("tool_approval:child000-run:act:i1");
    expect(snap.messages.map((m) => m.content)).toContain("write a.txt");
    expect(snap.messages.some((m) => m.toolActivity?.name === "write_file" && m.toolActivity.status === "waiting")).toBe(true);
    // With the empty records of view mode, the approval card is still the full control.
    const control = presentInteraction(pending, ctl, { records: snap.records, currentRun: snap.run, allowSkip: true });
    expect(control?.kind).toBe("tool-approval");
    expect(urls.some((u) => u.includes("history_bundle") || /\/ledger\?/.test(u))).toBe(false);
    ctl.dispose();
    vi.unstubAllGlobals();
  });

  it("the kit's abort signal reaches the view requests (dispose aborts them)", async () => {
    const view = replayView();
    const signals: Array<[string, AbortSignal | undefined]> = [];
    vi.stubGlobal("fetch", async (url: string, init: RequestInit) => {
      if (url.includes("/view")) signals.push([url, init.signal ?? undefined]);
      if (url.endsWith("/view")) return new Response(JSON.stringify(view), { status: 200, headers: { ETag: `"${view.cursor.token}"` } });
      if (url.includes("/stream")) return new Response(new ReadableStream({ start(c) { init.signal?.addEventListener("abort", () => { try { c.close(); } catch { /* closed */ } }); } }), { status: 200 });
      return new Response(JSON.stringify({ run_id: "root0000-run", status: "waiting" }), { status: 200 });
    });
    const ctl = new WorkflowSessionController(createAssistantTransport(new GatewayClient(host()), { onDeltaError: () => {} }));
    await ctl.load("root0000-run");
    await new Promise((r) => setTimeout(r, 20));
    expect(signals.map(([u]) => u)).toEqual(["api/gateway/runs/root0000-run/view", "api/gateway/runs/root0000-run/view/stream"]);
    expect(signals.every(([, s]) => s instanceof AbortSignal && !s.aborted)).toBe(true);
    ctl.dispose();
    expect(signals.every(([, s]) => s?.aborted)).toBe(true);
    vi.unstubAllGlobals();
  });

  it("an older gateway (no view route) keeps the ledger fold, labeled", async () => {
    vi.stubGlobal("fetch", async (url: string) => {
      if (url.endsWith("/view")) return new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 });
      if (url.includes("history_bundle")) return new Response(JSON.stringify({ ledgers: {} }), { status: 200 });
      if (url.includes("/ledger")) return new Response(JSON.stringify({ items: [], next_after: 0 }), { status: 200 });
      return new Response(JSON.stringify({ run_id: "r-old", status: "completed", output: { answer: "done" } }), { status: 200 });
    });
    const ctl = new WorkflowSessionController(createAssistantTransport(new GatewayClient(host()), { onDeltaError: () => {} }));
    await ctl.load("r-old");
    await new Promise((r) => setTimeout(r, 20));
    expect(ctl.getSnapshot().source).toBe("ledger_fold");
    expect(ctl.getSnapshot().sourceReason).toMatch(/0\.17\.0/);
    ctl.dispose();
    vi.unstubAllGlobals();
  });
});

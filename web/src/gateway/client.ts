/**
 * The gateway calls the web Assistant makes, through the host (src/host/):
 * the host builds every URL and authenticates every request. Routes and
 * shapes are the desktop's (abstractassistant/gateway/client.py) and the
 * iPhone's (phone/iphone/Packages/AssistantKit/Sources/PhoneGatewayClient/
 * GatewayClient.swift); file:line citations are in ADR 0007.
 *
 * Rules: a non-2xx answer throws GatewayHttpError with the gateway's own
 * sentence; an answer missing a field this client needs throws; nothing is
 * retried here (a failed run start is NEVER retried: the user checks the
 * conversation before resending, as on the iPhone).
 */
import type { AssistantHost } from "../host";
import { SseParser } from "./sse";

export class GatewayHttpError extends Error {
  readonly status: number;
  readonly reasonCode: string;
  constructor(message: string, status: number, reasonCode = "") {
    super(message);
    this.name = "GatewayHttpError";
    this.status = status;
    this.reasonCode = reasonCode;
  }
}

type Json = Record<string, unknown>;

function isObject(v: unknown): v is Json {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v);
}

async function errorFrom(resp: Response, label: string): Promise<GatewayHttpError> {
  let detail = "";
  let reason = "";
  try {
    const text = await resp.text();
    try {
      const body = JSON.parse(text);
      const d = isObject(body) ? body.detail : undefined;
      if (typeof d === "string") detail = d;
      else if (isObject(d)) {
        detail = String(d.message || d.detail || JSON.stringify(d));
        reason = String(d.reason_code || "");
      } else if (isObject(body) && typeof body.message === "string") detail = body.message;
      if (!reason && isObject(body) && typeof body.reason_code === "string") reason = body.reason_code;
      if (!detail) detail = text;
    } catch {
      detail = text;
    }
  } catch {
    detail = "";
  }
  return new GatewayHttpError(`${label}: ${detail || `HTTP ${resp.status}`}`, resp.status, reason);
}

export type StartRunRequest = {
  flow_id: string;
  input_data: Json;
  session_id: string;
  interface?: string;
  bundle_id?: string;
  bundle_version?: string;
  registry_scope?: string;
};

export type LedgerStep = { cursor: number; record: Json };

export type StreamHandlers = {
  onStep: (step: LedgerStep) => void;
  /** llm.delta / llm.delta_end frames (no cursor; never move the resume point). */
  onDelta?: (event: "llm.delta" | "llm.delta_end", data: Json) => void;
  /** The stream connected: drop live text, snapshots follow (api.md "Snapshots"). */
  onOpen?: () => void;
};

export type AttachmentRef = Json & { $artifact: string };

/** The run commands, as the desktop sends them (client.py wait_response_command). */
export function resumeWaitCommand(runId: string, waitKey: string, payload: Json): Json {
  const rid = String(runId || "").trim();
  const key = String(waitKey || "").trim();
  if (!rid || !key) throw new Error("resumeWaitCommand: run_id and wait_key are required");
  return {
    command_id: `resume_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`,
    run_id: rid,
    type: "resume",
    payload: { wait_key: key, payload },
    client_id: "abstractassistant-web",
  };
}

export class GatewayClient {
  constructor(private readonly host: AssistantHost) {}

  private async request(method: string, route: string, body?: unknown, label?: string): Promise<Json> {
    const mutating = method !== "GET" && method !== "HEAD";
    const headers: Record<string, string> = { Accept: "application/json", ...this.host.auth.headers(mutating) };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const resp = await fetch(this.host.gatewayUrl(route), {
      method,
      headers,
      credentials: this.host.auth.credentials,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!resp.ok) throw await errorFrom(resp, label || `${method} ${route}`);
    const parsed = await resp.json();
    if (!isObject(parsed)) throw new Error(`${label || route}: the gateway did not answer with a JSON object`);
    return parsed;
  }

  me() {
    return this.request("GET", "me", undefined, "Who am I");
  }

  capabilities() {
    return this.request("GET", "discovery/capabilities", undefined, "Gateway capabilities");
  }

  /** One page of turn roots, newest first. The query is the desktop's, pinned
   * (client.py session_listing_path): the gateway refuses unknown parameters. */
  listSessionRuns(limit: number, offset = 0) {
    const q =
      `runs?limit=${Math.max(1, Math.trunc(limit))}&offset=${Math.max(0, Math.trunc(offset))}` +
      "&root_only=true&include_ledger_len=false&session_kind=chat,discussion";
    return this.request("GET", q, undefined, "Conversations");
  }

  executableBundles(iface: string) {
    return this.request("GET", `bundles?executable_for=${encodeURIComponent(iface)}`, undefined, "Workflows");
  }

  discoveryTools() {
    return this.request("GET", "discovery/tools", undefined, "Tools");
  }

  accountPreferences() {
    return this.request("GET", "accounts/me/preferences", undefined, "Your preferences");
  }

  async startRun(req: StartRunRequest): Promise<{ run_id: string; resolved_workflow: Json | null }> {
    if (req.flow_id === "@default" && !req.interface) throw new Error("startRun: '@default' needs an interface");
    if (!req.session_id) throw new Error("startRun: a session_id is required");
    const out = await this.request("POST", "runs/start", req, "The message could not be sent");
    const runId = typeof out.run_id === "string" ? out.run_id.trim() : "";
    if (!runId) throw new Error("The gateway accepted the message but returned no run id.");
    return { run_id: runId, resolved_workflow: isObject(out.resolved_workflow) ? out.resolved_workflow : null };
  }

  inputData(runId: string) {
    return this.request("GET", `runs/${encodeURIComponent(runId)}/input_data`, undefined, "Run input");
  }

  /** One page of the person's event stream; `head` is the newest sequence. */
  meEvents(after: number, limit: number) {
    return this.request("GET", `me/events?after=${Math.max(0, after)}&limit=${Math.max(1, Math.trunc(limit))}`, undefined, "Your events");
  }

  getRun(runId: string) {
    return this.request("GET", `runs/${encodeURIComponent(runId)}`, undefined, "Run");
  }

  /** As the desktop reads it (gateway_worker.py _seed_history_from_gateway), plus
   * `detail=replay` (api.md: the transcript-fold projection; session.turns
   * with prompt/answer/attachments survive it — read on the local gateway
   * 2026-10-26, see the W3 report). */
  historyBundle(runId: string) {
    const q =
      `runs/${encodeURIComponent(runId)}/history_bundle?include_subruns=true&include_session=true` +
      "&session_turn_limit=200&ledger_mode=tail&ledger_max_items=2000&detail=replay";
    return this.request("GET", q, undefined, "Conversation history");
  }

  submitCommand(command: Json) {
    return this.request("POST", "commands", command, "The answer could not be sent");
  }

  cancelRun(runId: string) {
    return this.submitCommand({
      command_id: `cancel_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`,
      run_id: runId,
      type: "cancel",
      payload: { reason: "Stopped by the user" },
      client_id: "abstractassistant-web",
    });
  }

  /** `POST attachments/upload` (multipart): the ref the run input carries. */
  async uploadAttachment(sessionId: string, file: Blob, filename: string, extra: Record<string, string> = {}) {
    const form = new FormData();
    form.set("session_id", sessionId);
    for (const [k, v] of Object.entries(extra)) form.set(k, v);
    form.set("file", file, filename);
    const resp = await fetch(this.host.gatewayUrl("attachments/upload"), {
      method: "POST",
      headers: { Accept: "application/json", ...this.host.auth.headers(true) },
      credentials: this.host.auth.credentials,
      body: form,
    });
    if (!resp.ok) throw await errorFrom(resp, `${filename} could not be attached`);
    const out = await resp.json();
    const ref = isObject(out) ? (out.attachment ?? out.artifact) : undefined;
    if (!isObject(ref) || typeof ref.$artifact !== "string" || !ref.$artifact) {
      throw new Error(`${filename}: the gateway stored the file but returned no artifact reference.`);
    }
    return { ref: ref as AttachmentRef, ownerRunId: String((isObject(out) && out.run_id) || ref.run_id || "") };
  }

  /** Gateway STT on an uploaded recording (phone GatewayClient.swift transcribe). */
  async transcribe(ownerRunId: string, artifactId: string): Promise<string> {
    const out = await this.request(
      "POST",
      `runs/${encodeURIComponent(ownerRunId)}/audio/transcribe`,
      { audio_artifact: { $artifact: artifactId } },
      "Dictation failed",
    );
    if (typeof out.text !== "string") throw new Error("Dictation: the gateway returned no text.");
    return out.text.trim();
  }

  /** `POST runs/{id}/voice/tts/stream`: JSON Lines, one object per line. */
  async *speechStream(runId: string, text: string, signal?: AbortSignal): AsyncGenerator<Json> {
    const resp = await fetch(this.host.gatewayUrl(`runs/${encodeURIComponent(runId)}/voice/tts/stream`), {
      method: "POST",
      headers: { "Content-Type": "application/json", ...this.host.auth.headers(true) },
      credentials: this.host.auth.credentials,
      body: JSON.stringify({ text }),
      signal,
    });
    if (!resp.ok) throw await errorFrom(resp, "Read aloud failed");
    if (!resp.body) throw new Error("Read aloud: the gateway sent no stream.");
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      buf += dec.decode(value || new Uint8Array(), { stream: !done });
      let nl: number;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        if (line) yield JSON.parse(line) as Json;
      }
      if (done) break;
    }
    if (buf.trim()) yield JSON.parse(buf.trim()) as Json;
  }

  /**
   * Read one run's ledger over SSE from `after` (api.md "Stream ledger
   * updates"). Resolves when the server closes the stream, with the last
   * cursor and whether `event: done` was SEEN: a stream closed without it (a
   * proxy idle timeout, a gateway restart) says nothing about the run, and the
   * caller must ask the run (src/gateway/follow.ts). A malformed `step` frame
   * throws: dropping it would move past a record nobody read.
   */
  async streamLedger(runId: string, after: number, handlers: StreamHandlers, signal: AbortSignal): Promise<{ cursor: number; done: boolean }> {
    const done = await this.sse(`runs/${encodeURIComponent(runId)}/ledger/stream?after=${Math.max(0, after)}`, signal, (ev) => {
      if (ev.event === "step") {
        const parsed = JSON.parse(ev.data) as unknown;
        if (!isObject(parsed) || typeof parsed.cursor !== "number" || !isObject(parsed.record)) {
          throw new Error(`Live updates: a ledger step of run ${runId} had no cursor or record.`);
        }
        after = parsed.cursor;
        handlers.onStep({ cursor: parsed.cursor, record: parsed.record });
        return false;
      }
      if ((ev.event === "llm.delta" || ev.event === "llm.delta_end") && handlers.onDelta) {
        handlers.onDelta(ev.event, JSON.parse(ev.data) as Json);
        return false;
      }
      return ev.event === "done";
    }, handlers.onOpen);
    return { cursor: after, done };
  }

  /** `GET runs/{id}/ledger?after=&limit=`: one page of durable records (api.md "Replay the ledger"). */
  async ledgerPage(runId: string, after: number, limit = 500): Promise<{ items: Json[]; next_after: number }> {
    const out = await this.request("GET", `runs/${encodeURIComponent(runId)}/ledger?after=${Math.max(0, after)}&limit=${limit}`, undefined, "Run ledger");
    if (!Array.isArray(out.items) || typeof out.next_after !== "number") throw new Error(`Run ledger of ${runId}: no items or next_after in the answer.`);
    return { items: out.items.filter(isObject), next_after: out.next_after };
  }

  /** `GET me/events/stream`: the person's own event stream (api.md "Your event stream"). */
  followMeEvents(after: number, onEvent: (event: Json) => void, signal: AbortSignal): Promise<void> {
    return this.sse(`me/events/stream?after=${Math.max(0, after)}&heartbeat_s=15`, signal, (ev) => {
      if (ev.data) onEvent(JSON.parse(ev.data) as Json);
      return false;
    }).then(() => undefined);
  }

  private async sse(
    route: string,
    signal: AbortSignal,
    onEvent: (ev: { event: string; data: string }) => boolean,
    onOpen?: () => void,
  ): Promise<boolean> {
    const resp = await fetch(this.host.gatewayUrl(route), {
      headers: { Accept: "text/event-stream", ...this.host.auth.headers(false) },
      credentials: this.host.auth.credentials,
      signal,
    });
    if (!resp.ok) throw await errorFrom(resp, "Live updates");
    if (!resp.body) throw new Error("Live updates: the gateway sent no stream.");
    onOpen?.();
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    const parser = new SseParser();
    for (;;) {
      const { value, done } = await reader.read();
      // Closed by the server: `false` = no terminating event was seen.
      if (done) return false;
      for (const ev of parser.push(dec.decode(value, { stream: true }))) {
        if (onEvent(ev)) {
          await reader.cancel();
          return true;
        }
      }
    }
  }
}

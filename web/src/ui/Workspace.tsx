/**
 * The open conversation, composed from the kit (ADR 0001; backlog 0030, 0032):
 * - `useWorkflowSession` + this app's transport (src/gateway/transport.ts) fold the ledger,
 *   follow child runs, stream live replies and hold the pending question;
 * - `WorkflowChat` is the thread and the composer (typed attachment chips through
 *   `useAttachmentUploads`, Stop, a transcript toolbar);
 * - `presentInteraction` is the approval / question panel, with the ONE wording set and the
 *   chat's tool policy on the gateway when it advertises `session_tool_policy`;
 * - `useGatewayVoice` + `AfVoiceMicButton` read replies aloud and dictate.
 * Everything comes from the gateway; this page keeps no conversation and no token.
 */
import {
  WorkflowChat,
  presentInteraction,
  useAttachmentUploads,
  useWorkflowSession,
  workflowPendingInteraction,
  type ChatMessage,
} from "@abstractframework/panel-chat";
import {
  AfVoiceMicButton,
  createSessionToolPolicyClient,
  normalizeToolCatalog,
  planRunTools,
  sessionToolPolicyCapability,
  streamTtsJsonl,
  useGatewayVoice,
  withRunTools,
  type VoiceCaptureMode,
  type VoiceClientPreferences,
} from "@abstractframework/ui-kit";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { GatewayClient, type AttachmentRef } from "../gateway/client";
import { createAssistantTransport } from "../gateway/transport";
import type { AssistantHost } from "../host";
import { buildRunInputData } from "../lib/run_input";
import { STATE_WORDS, type SessionState } from "../lib/session_fold";
import { selectWorkflow } from "../lib/workflow_selection";
import type { AttentionSeen } from "./useConversations";

export function mintSessionId(): string {
  // The desktop mints `sess_<uuid hex>` (core/session_index.py); the gateway learns the id
  // with the first run.
  return `sess_${crypto.randomUUID().replace(/-/g, "")}`;
}

const TERMINAL = new Set(["completed", "failed", "cancelled"]);

/** The served `toolset` of each tool (`GET discovery/tools` rows), for the approval panel's
 * "Allow all <toolset> tools for this chat". A row without a served toolset gets none: the
 * panel never guesses a kind. */
export function toolsetsFromDiscovery(payload: unknown): Map<string, string> {
  const out = new Map<string, string>();
  const items = payload && typeof payload === "object" && Array.isArray((payload as { items?: unknown }).items) ? (payload as { items: unknown[] }).items : [];
  for (const row of items) {
    if (!row || typeof row !== "object") continue;
    const r = row as Record<string, unknown>;
    const name = typeof r.name === "string" ? r.name.trim() : "";
    const toolset = typeof r.toolset === "string" ? r.toolset.trim() : "";
    if (name && toolset) out.set(name, toolset);
  }
  return out;
}

/** Whether a `me/events` `attention.seen` names the wait shown here. */
export function seenMatches(seen: AttentionSeen | null, wait: { runId: string; waitKey: string; stepId?: string } | null): boolean {
  if (!seen || !wait) return false;
  if (seen.run_id !== wait.runId || seen.wait_key !== wait.waitKey) return false;
  return !seen.step_id || !wait.stepId || seen.step_id === wait.stepId;
}

export function Workspace(props: {
  client: GatewayClient;
  host: AssistantHost;
  /** The conversation's session (""= a new conversation, minted on the first upload or send). */
  sessionId: string;
  /** The root run to follow (the session's latest turn, or the turn just started). */
  runId: string;
  title: string;
  listState?: SessionState;
  /** The latest `me/events` `attention.seen`: a wait answered or dismissed on another device. */
  seen: AttentionSeen | null;
  /** Why updates from other devices are off ("" = on). */
  eventsNotice: string;
  voicePrefs: VoiceClientPreferences;
  captureMode: VoiceCaptureMode;
  onStarted: (runId: string, sessionId: string) => void;
  onNewChat: () => void;
  onTurnEnded: () => void;
  onSignedOut: () => void;
}) {
  const { client, host } = props;
  const [draft, setDraft] = useState("");
  const [notice, setNotice] = useState("");
  // A new conversation gets its session id on its first upload or send.
  const newSession = useRef("");
  const ensureSession = useCallback(() => {
    if (props.sessionId) return props.sessionId;
    if (!newSession.current) newSession.current = mintSessionId();
    return newSession.current;
  }, [props.sessionId]);
  useEffect(() => {
    if (!props.sessionId && !props.runId) newSession.current = "";
  }, [props.sessionId, props.runId]);

  const signedOut = useRef(props.onSignedOut);
  signedOut.current = props.onSignedOut;
  const onAuthError = useCallback(() => signedOut.current(), []);
  const transport = useMemo(
    () => createAssistantTransport(client, { onDeltaError: (m) => setNotice(`A live reply frame was malformed and skipped: ${m}`) }),
    [client],
  );
  const { controller, snapshot } = useWorkflowSession({ transport, runId: props.runId, clientId: "abstractassistant-web", onAuthError });

  // The chat's tool policy on the gateway (capability-gated). Absent capability = the local
  // grant, labeled; a failed capability read = "unavailable", with the reason.
  const capabilities = useRef<Promise<unknown> | null>(null);
  useEffect(() => {
    let cancelled = false;
    const sid = props.sessionId;
    if (!sid) {
      controller.setSessionToolPolicyClient(null);
      return;
    }
    capabilities.current ??= client.capabilities();
    capabilities.current.then(
      (caps) => {
        if (cancelled) return;
        const cap = sessionToolPolicyCapability(caps);
        controller.setSessionToolPolicyClient(cap ? createSessionToolPolicyClient(client.policyRequest, sid, cap, { client: "abstractassistant-web" }) : null);
      },
      (err) => {
        capabilities.current = null;
        if (!cancelled) controller.setSessionToolPolicyClient(null, { reason: `Could not read the gateway's capabilities (${err instanceof Error ? err.message : String(err)}).` });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [controller, client, props.sessionId]);

  // Toolsets for "Allow all <toolset> tools for this chat" (the served `toolset`, never guessed).
  const [toolsets, setToolsets] = useState<Map<string, string>>(new Map());
  useEffect(() => {
    let cancelled = false;
    client.discoveryTools().then(
      (payload) => !cancelled && setToolsets(toolsetsFromDiscovery(payload)),
      () => undefined,
    );
    return () => {
      cancelled = true;
    };
  }, [client]);

  // When a turn ends, the list refreshes (its state and recency changed).
  const ended = useRef("");
  useEffect(() => {
    if (props.runId && TERMINAL.has(snapshot.status) && ended.current !== props.runId) {
      ended.current = props.runId;
      props.onTurnEnded();
    }
  }, [props.runId, snapshot.status, props]);

  // ---- the pending question ------------------------------------------------------------
  const pending = workflowPendingInteraction(snapshot);
  const pendingTarget = pending ? { runId: pending.runId, waitKey: String(pending.wait.wait_key || ""), stepId: pending.stepId } : null;
  const pendingKey = pendingTarget ? `${pendingTarget.runId}|${pendingTarget.waitKey}|${pendingTarget.stepId || ""}` : "";
  const [deferred, setDeferred] = useState("");
  const answeredElsewhere = seenMatches(props.seen, pendingTarget);
  const interaction = useMemo(() => {
    if (!pending) return null;
    return presentInteraction(pending, controller, {
      records: snapshot.records,
      currentRun: snapshot.run,
      allowSkip: true,
      onDefer: () => setDeferred(pendingKey),
      sessionPolicy: { toolsetOf: (name) => toolsets.get(name) },
    });
    // The policy mode, reason and clamped list are the controller's: re-present when they change.
  }, [pending, controller, snapshot.records, snapshot.run, snapshot.sessionPolicyMode, snapshot.sessionPolicyReason, snapshot.sessionPolicyClamped, snapshot.sessionPolicy, toolsets, pendingKey]);
  const shown = interaction && deferred !== pendingKey && !answeredElsewhere ? interaction : null;

  // ---- voice: read aloud and dictation, on the gateway's engines ----------------------
  const runIdRef = useRef(props.runId);
  runIdRef.current = props.runId;
  const voice = useGatewayVoice({
    output_device_id: props.voicePrefs.output_device || "",
    input_device_id: props.voicePrefs.input_device || "",
    ...(typeof props.voicePrefs.input_gain === "number" ? { input_gain: props.voicePrefs.input_gain } : {}),
    ...(typeof props.voicePrefs.reply_volume === "number" ? { volume: props.voicePrefs.reply_volume } : {}),
    capture_mode: props.captureMode,
    tts_stream: host.capabilities.audioPlayback.available
      ? async function* (text, signal) {
          const run = runIdRef.current;
          if (!run) throw new Error("Read aloud needs a conversation turn on the gateway");
          yield* streamTtsJsonl({
            path: host.gatewayUrl(`runs/${encodeURIComponent(run)}/voice/tts/stream`),
            headers: host.auth.headers(true),
            body: { text },
            ...(signal ? { signal } : {}),
          });
        }
      : undefined,
    transcribe: host.capabilities.microphone.available
      ? async (blob, mime) => {
          const sid = ensureSession();
          const type = (mime || "audio/webm").split(";")[0];
          const ext = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
          const up = await client.uploadAttachment(sid, blob, `ask.${ext}`, { content_type: type, source_path: `voice/dictation/${crypto.randomUUID()}.${ext}` });
          return client.transcribe(up.ownerRunId || `session_memory_${sid}`, String(up.ref.$artifact));
        }
      : undefined,
    on_error: (message) => setNotice(message),
  });

  // ---- attachments -----------------------------------------------------------------------
  const uploads = useAttachmentUploads<AttachmentRef>({
    upload: async (file) => (await client.uploadAttachment(ensureSession(), file, file.name, file.type ? { content_type: file.type } : {})).ref,
  });

  // ---- send ---------------------------------------------------------------------------------
  const send = useCallback(
    async (text: string) => {
      const sid = ensureSession();
      const refs = uploads.attached;
      const [bundles, prefs, tools] = await Promise.all([
        client.executableBundles("abstractassistant.agent.v1"),
        client.accountPreferences(),
        client.discoveryTools(),
      ]);
      const start = selectWorkflow(bundles, prefs);
      const image = refs.find((r) => String(r.content_type || "").startsWith("image/"));
      // The tools the gateway offers (the kit's plan, backlog 0033). No layer of the person's
      // own yet, so approvals follow the gateway's defaults (its grant at run start).
      const input_data = withRunTools(buildRunInputData({ prompt: text, attachments: refs, primary_image_artifact: image ?? null, stream: true }), planRunTools(normalizeToolCatalog(tools)));
      // Never retried here: a failure keeps the draft and says why; the person resends.
      const { run_id } = await client.startRun(
        start.source === "gateway_default"
          ? { flow_id: "@default", interface: start.interface, session_id: sid, input_data }
          : { flow_id: start.flow_id, bundle_id: start.bundle_id, bundle_version: start.bundle_version, registry_scope: start.registry_scope, session_id: sid, input_data },
      );
      uploads.clear();
      setDraft("");
      setNotice("");
      props.onStarted(run_id, sid);
    },
    [client, ensureSession, uploads, props],
  );

  const busy = Boolean(props.runId) && !TERMINAL.has(snapshot.status) && !(snapshot.error && !snapshot.run);
  // The Assistant speaks as "Assistant" (the card's default is "Agent").
  const messages = useMemo<ChatMessage[]>(
    () => snapshot.messages.map((m) => (m.role === "assistant" && !m.title ? { ...m, title: "Assistant" } : m)),
    [snapshot.messages],
  );
  const listWords = props.listState ? STATE_WORDS[props.listState] : "";

  return (
    <WorkflowChat
      className="aa-chat"
      messages={messages}
      draft={draft}
      onDraftChange={setDraft}
      onSend={send}
      busy={busy}
      onCancel={() => controller.cancel()}
      stopState={snapshot.stop || null}
      placeholder="Message the Assistant"
      emptyState={<p className="aa-empty">Ask anything. Your conversations are kept on your gateway and follow you on every device.</p>}
      header={
        <div className="aa-chat__header">
          <h1 className="aa-chat__title">{props.title}</h1>
          {listWords ? <span className={`aa-state aa-state--${props.listState}`}>{listWords}</span> : null}
          {snapshot.connection === "reconnecting" ? <span className="aa-chat__status" role="status">Reconnecting…</span> : null}
          {snapshot.displayStatus ? <span className="aa-chat__status" role="status">{snapshot.displayStatus}</span> : null}
        </div>
      }
      toolbar={{ onNewSession: props.onNewChat, copyTranscript: true, exportTranscript: { filename: "conversation.md", heading: props.title } }}
      footer={
        snapshot.error || notice || props.eventsNotice || answeredElsewhere || (interaction && deferred === pendingKey) ? (
          <div className="aa-chat__notes">
            {snapshot.error ? <p className="aa-note aa-note--error" role="alert">{snapshot.error}</p> : null}
            {notice ? (
              <p className="aa-note" role="status">
                {notice}{" "}
                <button type="button" className="aa-link" onClick={() => setNotice("")}>
                  Dismiss
                </button>
              </p>
            ) : null}
            {props.eventsNotice ? <p className="aa-note" role="status">{props.eventsNotice}</p> : null}
            {answeredElsewhere && props.seen ? <p className="aa-note" role="status">Answered ({props.seen.outcome}).</p> : null}
            {interaction && deferred === pendingKey && !answeredElsewhere ? (
              <p className="aa-note" role="status">
                A request is waiting for you.{" "}
                <button type="button" className="aa-link" onClick={() => setDeferred("")}>
                  Review
                </button>
              </p>
            ) : null}
          </div>
        ) : null
      }
      interaction={shown}
      onFiles={(files) => void uploads.add(files)}
      attachmentItems={uploads.items}
      onRemoveAttachment={uploads.remove}
      onRetryAttachment={uploads.retry}
      composerExtras={
        <AfVoiceMicButton
          voice={voice}
          mode={props.captureMode}
          unavailableReason={host.capabilities.microphone.available ? null : host.capabilities.microphone.reason}
          // Review before sending (the iPhone's default, backlog 1048): the transcript joins the draft.
          onTranscript={(said) => setDraft((prev) => (prev.trim() ? `${prev.trim()}\n${said}` : said))}
        />
      }
      messageProps={{
        // "link": a model's text cannot make the browser fetch a remote image.
        images: "link",
        ...(voice.tts_supported
          ? {
              onSpeakToggle: (m: ChatMessage) => void voice.toggle_tts(String(m.id || ""), m.content),
              getSpeakState: (m: ChatMessage) => (voice.tts_playback.key === String(m.id || "") ? voice.tts_playback.status : "idle"),
            }
          : {}),
      }}
    />
  );
}

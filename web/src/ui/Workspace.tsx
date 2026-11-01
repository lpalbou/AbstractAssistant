import {WorkflowChat, useWorkflowSession, conversationSnapshot, useAvatarConversationPreferences, playConversationCue, conversationReply, presentInteraction} from "../vendor/abstractchat/conversation.js";
import "../vendor/abstractchat/conversation.css";
import { SessionReadMarker, sessionContentRevision, sessionReadTarget, sessionOpeningReceipts, type SessionReceipt, type SessionActivity } from "../vendor/abstractsessions/session_cards.js";
/**
 * The open conversation, composed from the kit (ADR 0001; backlog 0030, 0032):
 * - `useWorkflowSession` + this app's transport (src/gateway/transport.ts) render the
 *   conversation from the gateway's replay view (AbstractGateway >= 0.17.0; the controller folds
 *   the ledger itself on an older gateway, labeled here), stream live replies and hold the
 *   pending question;
 * - `WorkflowChat` is the thread and the composer (typed attachment chips through
 *   `useAttachmentUploads`, Stop, a transcript toolbar);
 * - `presentInteraction` is the approval / question panel, with the ONE wording set and the
 *   chat's tool policy on the gateway when it advertises `session_tool_policy`;
 * - `useGatewayVoice` + `AfVoiceMicButton` read replies aloud and dictate.
 * Everything comes from the gateway; this page keeps no conversation and no token.
 */
import {
  useAttachmentUploads,
  workflowPendingInteraction,
  workflowSourceLabel,
  type ChatMessage,
} from "@abstractframework/panel-chat";
import {
  Icon,
  AfVoiceMicButton,
  createSessionToolPolicyClient,
  normalizeToolCatalog,
  planRunTools,
  sessionToolPolicyCapability,
  streamTtsJsonl,
  gatewayVoiceOptions,
  voiceSttRequest,
  voiceTtsRequest,
  withRunTools,
  type VoiceCaptureMode,
  type VoiceClientPreferences,
} from "@abstractframework/ui-kit";
import { useGatewayVoice } from "../vendor/abstractvoice/use_gateway_voice.js";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { GatewayClient, type AttachmentRef } from "../gateway/client";
import { createAssistantTransport } from "../gateway/transport";
import type { AssistantHost } from "../host";
import { buildRunInputData } from "../lib/run_input";
import { selectWorkflow } from "../lib/workflow_selection";
import type { AttentionSeen } from "./useConversations";
import { assistantPresence, conversationPresentation, replyToRead } from "../lib/presentation";
import { VoiceStage, Orb } from "./VoiceStage";
import type { AssistantPreferences } from "./useAssistantPreferences";

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

/**
 * What the ended turn says when the transcript cannot: a failure's reason, or no written reply.
 * (Kit gap: the controller adds no line for a root run that ended failed or without an answer.)
 * A stop is the kit's own Stop state ("Stopped"), not repeated here.
 */
export function turnOutcome(runId: string, status: string, run: Record<string, unknown> | null, messages: ReadonlyArray<{ id?: string; role: string; runId?: string; live?: unknown; toolActivity?: unknown; content?: string }>): string {
  if (!runId || !TERMINAL.has(status) || status === "cancelled") return "";
  if (status === "failed") {
    const why = typeof run?.error === "string" ? run.error.trim() : "";
    return why ? `The run failed: ${why}` : "The run failed (the gateway gave no reason).";
  }
  const answered = messages.some((m) => m.role === "assistant" && !m.live && !m.toolActivity &&
    (m.id === `final:${runId}` || String(m.id || "").startsWith(`answer:${runId}:`) || (m.runId === runId && Boolean(m.content?.trim()))));
  return answered ? "" : "The run ended without a written reply.";
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
  /** The latest `me/events` `attention.seen`: a wait answered or dismissed on another device. */
  seen: AttentionSeen | null;
  /** Why updates from other devices are off ("" = on). */
  eventsNotice: string;
  /** The person's voice preferences (Settings → Voice; `useVoicePreferences`). */
  voicePrefs: VoiceClientPreferences;
  onVoicePrefsChange: (next: VoiceClientPreferences) => void;
  appearance: AssistantPreferences;
  onSettings: () => void;
  /** The microphone button's mode (the preference, else this app's default: tap to talk). */
  captureMode: VoiceCaptureMode;
  /** Send what was said at once (`auto_send`), else the transcript joins the draft for review. */
  autoSend: boolean;
  onStarted: (runId: string, sessionId: string) => void;
  onNewChat: () => void;
  onTurnEnded: () => void;
  onSignedOut: () => void;
  readScope: string;
  sessionActivity?: SessionActivity;
  canConsume: boolean;
  onRead: (receipt: SessionReceipt) => void;
}) {
  const { client, host } = props;
  const [draft, setDraft] = useState("");
  const avatarPreferences = useAvatarConversationPreferences(`abstractassistant:${props.readScope}`);
  const avatarMode = avatarPreferences.mode === "avatar";
  const [replyContext, setReplyContext] = useState<ChatMessage | null>(null);
  const [avatarAttended, setAvatarAttended] = useState(false);
  useEffect(() => setReplyContext(null), [props.readScope, props.sessionId]);
  const [notice, setNotice] = useState("");
  const [technical, setTechnical] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const mounted = useRef(true);
  const startedHere = useRef("");
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
  const voicePrefs = useRef(props.voicePrefs);
  voicePrefs.current = props.voicePrefs;
  const voice = useGatewayVoice({
    ...gatewayVoiceOptions(props.voicePrefs),
    capture_mode: props.captureMode,
    tts_stream: host.capabilities.audioPlayback.available
      ? async function* (text, signal) {
          const run = runIdRef.current;
          if (!run) throw new Error("Read aloud needs a conversation turn on the gateway");
          yield* streamTtsJsonl({
            path: host.gatewayUrl(`runs/${encodeURIComponent(run)}/voice/tts/stream`),
            headers: host.auth.headers(true),
            // The person's speech override (empty = the gateway default voice).
            body: { text, ...voiceTtsRequest(voicePrefs.current) },
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
          const route = Object.fromEntries(Object.entries(voiceSttRequest(voicePrefs.current)).filter(([, v]) => typeof v === "string" && v)) as Record<string, string>;
          return client.transcribe(up.ownerRunId || `session_memory_${sid}`, String(up.ref.$artifact), route);
        }
      : undefined,
    on_error: (message) => setNotice(message),
  });
  const voiceRef = useRef(voice);
  voiceRef.current = voice;
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      voiceRef.current.stop_tts();
      voiceRef.current.cancel_voice_ptt_recording?.();
    };
  }, []);

  // ---- attachments -----------------------------------------------------------------------
  const uploads = useAttachmentUploads<AttachmentRef>({
    upload: async (file) => (await client.uploadAttachment(ensureSession(), file, file.name, file.type ? { content_type: file.type } : {})).ref,
  });

  const busy = Boolean(props.runId) && !TERMINAL.has(snapshot.status) && !(snapshot.error && !snapshot.run);

  // ---- send ---------------------------------------------------------------------------------
  const send = useCallback(
    async (text: string) => {
      voiceRef.current.stop_tts();
      if (busy) {
        if (!avatarMode) throw new Error("The assistant is still working.");
        if (interaction?.kind === "ask-user") {
          await interaction.onSubmit(text);
        } else {
          if (interaction) throw new Error("Use the request controls to answer it. A message does not grant permission.");
          const guidance = conversationReply(text, replyContext, props.runId, snapshot.view?.root_run_id === props.runId ? snapshot.view.runs.map((run) => run.run_id) : []);
          const answer = await controller.sendCommand("inject_guidance", { guidance, display_text: text }) as { accepted?: boolean } | null;
          if (answer?.accepted === false) throw new Error("Your message was not accepted. Please try again.");
        }
        if (!mounted.current) return;
        setDraft(""); setReplyContext(null);
        setNotice("Sent. Your message is available to the assistant.");
        return;
      }
      const sid = ensureSession();
      const refs = uploads.attached;
      const [bundles, prefs, tools] = await Promise.all([
        client.executableBundles("abstractassistant.agent.v1"),
        client.accountPreferences(),
        client.discoveryTools(),
      ]);
      const start = selectWorkflow(bundles, prefs);
      if (!mounted.current) return;
      const image = refs.find((r) => String(r.content_type || "").startsWith("image/"));
      // The tools the gateway offers (the kit's plan, backlog 0033). No layer of the person's
      // own yet, so approvals follow the gateway's defaults (its grant at run start).
      const input_data = withRunTools(buildRunInputData({ prompt: text, attachments: refs, primary_image_artifact: image ?? null, stream: true }), planRunTools(normalizeToolCatalog(tools)));
      // Never retried here: a failure keeps the draft and says why; the person resends.
      const { run_id } = await client.startRun(
        start.source === "gateway_default"
          ? { flow_id: "@default", interface: start.interface, session_id: sid, input_data, ...(avatarMode ? { conversation: true } : {}) }
          : { flow_id: start.flow_id, bundle_id: start.bundle_id, bundle_version: start.bundle_version, registry_scope: start.registry_scope, session_id: sid, input_data, ...(avatarMode ? { conversation: true } : {}) },
      );
      if (!mounted.current) return;
      startedHere.current = run_id;
      uploads.clear();
      setDraft("");
      setNotice("");
      props.onStarted(run_id, sid);
    },
    [client, ensureSession, uploads, props, busy, avatarMode, interaction, replyContext, controller, snapshot.view],
  );

  // The Assistant speaks as "Assistant" (the card's default is "Agent").
  const presentation = useMemo(
    () => conversationPresentation(snapshot.messages),
    [snapshot.messages],
  );
  const messages = presentation.conversation;
  const reply = replyToRead(messages, props.runId);
  useEffect(() => {
    if (snapshot.status !== "completed" || startedHere.current !== props.runId || !reply) return;
    startedHere.current = "";
    if (props.voicePrefs.read_aloud === true && !props.voicePrefs.reply_muted && voice.tts_supported && !voice.voice_ptt_recording && !voice.voice_ptt_busy && (!avatarMode || (!avatarAttended && !draft.trim())))
      void voice.toggle_tts(String(reply.id || props.runId), reply.content);
  }, [snapshot.status, props.runId, props.voicePrefs.read_aloud, props.voicePrefs.reply_muted, reply, voice]);
  const listWords = pending && !answeredElsewhere ? "Needs you" : "";
  const outcome = turnOutcome(props.runId, snapshot.status, snapshot.run, snapshot.messages);
  const presence = assistantPresence({ recording: voice.voice_ptt_recording, transcribing: voice.voice_ptt_busy,
    playback: voice.tts_playback.status, pending: Boolean(pending && !answeredElsewhere), busy,
    working: messages.some((m) => m.toolActivity?.status === "running"), failed: snapshot.status === "failed", loading: snapshot.loading });
  const focusComposer = () => root.current?.querySelector<HTMLTextAreaElement>("textarea")?.focus();
  const transcript = (said: string) => {
    const next = draft.trim() ? `${draft.trim()}\n${said}` : said;
    setDraft(next);
    focusComposer();
    if (props.autoSend && (!busy || avatarMode)) void send(next).catch((err) => setNotice(`Not sent: ${err instanceof Error ? err.message : String(err)}`));
  };
  const playback = () => {
    const current = messages.find((m) => String(m.id || "") === voice.tts_playback.key.replace(/^brief:/, ""));
    if (current) void voice.toggle_tts(voice.tts_playback.key, current.content);
    else voice.stop_tts();
  };
  const stop = () => {
    voice.stop_tts();
    voice.cancel_voice_ptt_recording?.();
    if (busy) void controller.cancel().catch((error) => setNotice(error instanceof Error ? error.message : String(error)));
  };

  return (
    <div className="aa-experience" ref={root} data-has-messages={messages.length > 0} data-view={avatarMode ? "avatar" : "chat"}>
    {!avatarMode && <VoiceStage voice={voice} presence={presence} prefs={props.appearance} mode={props.captureMode} busy={busy}
      microphoneReason={host.capabilities.microphone.available ? null : host.capabilities.microphone.reason}
      readReplies={props.voicePrefs.read_aloud === true} onReadRepliesChange={(read_aloud) => props.onVoicePrefsChange({ ...props.voicePrefs, read_aloud })}
      onTranscript={transcript} onPlayback={playback} onStop={stop} onType={focusComposer} onSettings={props.onSettings} autoSend={props.autoSend} />}
    <WorkflowChat
      composerTrailingActions={<AfVoiceMicButton voice={voice} mode={props.captureMode} label="Talk" showStatus={false} onTranscript={transcript} unavailableReason={host.capabilities.microphone.available ? null : host.capabilities.microphone.reason} />}
      avatarConversation={avatarMode ? {
        onTechnicalView: () => { voice.stop_tts(); avatarPreferences.setMode("chat"); },
        sessionKey: `${props.readScope}:${props.sessionId || "new"}`,
        avatar: <Orb voice={voice} prefs={props.appearance} pose={voice.voice_ptt_recording ? "listening" : voice.tts_playback.status === "playing" ? "speaking" : snapshot.run?.paused === true && !TERMINAL.has(snapshot.status) ? "waiting" : presence.pose} size={320} onError={() => setNotice("The avatar could not load. Voice and messages still work.")} />,
        ...conversationSnapshot(snapshot),
        listening: voice.voice_ptt_recording,
        speaking: voice.tts_playback.status === "playing",
        preferences: avatarPreferences.preferences,
        onPreferencesChange: avatarPreferences.setPreferences,
        onCue: (cue) => { void playConversationCue(cue).catch((reason) => setNotice(reason instanceof Error ? reason.message : String(reason))); },
        onInterruptSpeech: () => voice.stop_tts(),
        onReplyContext: setReplyContext,
        onAttendedChange: setAvatarAttended,
        narrate: props.voicePrefs.read_aloud === true && !props.voicePrefs.reply_muted,
        onNarrate: (message) => { if (voice.tts_supported) void voice.toggle_tts(`brief:${message.id}`, message.content); },
        voiceControl: <span onPointerDown={() => voice.stop_tts()}><AfVoiceMicButton voice={voice} mode={props.captureMode} label="Talk" onTranscript={transcript} unavailableReason={host.capabilities.microphone.available ? null : host.capabilities.microphone.reason} /></span>,
        playbackControl: <span role="group" aria-label="Voice controls">
          {voice.tts_supported && <button type="button" aria-pressed={props.voicePrefs.read_aloud === true} onClick={() => { voice.stop_tts(); props.onVoicePrefsChange({ ...props.voicePrefs, read_aloud: !props.voicePrefs.read_aloud }); }}>Read new replies aloud</button>}
          {["playing", "paused"].includes(voice.tts_playback.status) && <><button type="button" onClick={playback}>{voice.tts_playback.status === "paused" ? "Resume voice" : "Pause voice"}</button><button type="button" onClick={() => voice.stop_tts()}>Silence voice</button></>}
          <button type="button" onClick={props.onSettings}>Assistant settings</button>
        </span>,
      } : undefined}
                artifactFetch={client.fetchGateway}
                attachmentScope={JSON.stringify([props.readScope,props.sessionId])}
                attachmentRun={{runId:props.runId,output:snapshot.run?.output}}
      className="aa-chat"
      messages={messages}
      draft={draft}
      onDraftChange={setDraft}
      onSend={send}
      busy={busy}
      steer={avatarMode && busy ? { modes: ["guide"], onSteer: async (text) => { await send(text); return { accepted: true }; }, parked: snapshot.status === "waiting" } : undefined}
      busyLabel={pending && !answeredElsewhere ? "Waiting for you…" : snapshot.loading ? "Opening…" : presence.pose === "working" ? "Working…" : "Thinking…"}
      onCancel={() => controller.cancel()}
      stopState={snapshot.stop || null}
      placeholder="Message the Assistant"
      emptyState={<div className="aa-empty"><h2>What’s on your mind?</h2>
        <p>Ask a question, work through an idea, or just talk.</p>
        <div className="aa-starters">{["Help me think through an idea", "Summarize something for me", "What can you help me with?"].map((text) =>
          <button type="button" key={text} onClick={() => { setDraft(text); focusComposer(); }}>{text}<Icon name="chevronRight" size={14} /></button>)}</div>
        <span className="aa-empty__foot">Your conversations follow you across devices.</span></div>}
      header={
        <div className="aa-chat__header">
          <div className="aa-view-choice" role="group" aria-label="Conversation view">
            <button type="button" aria-pressed={!avatarMode} onClick={() => { voice.stop_tts(); avatarPreferences.setMode("chat"); }}>Conversation</button>
            <button type="button" aria-pressed={avatarMode} onClick={() => { voice.stop_tts(); avatarPreferences.setMode("avatar"); }}>Avatar</button>
          </div>
          <h1 className="aa-chat__title" title={props.title}>{props.title}</h1>
          {listWords ? <span className="aa-state aa-state--waiting">{listWords}</span> : null}
          {snapshot.connection === "reconnecting" ? <span className="aa-chat__status" role="status">Reconnecting…</span> : null}
          {snapshot.displayStatus ? <span className="aa-chat__status" role="status">{snapshot.displayStatus}</span> : null}
          <details className="aa-chat-details" onToggle={(e) => setTechnical(e.currentTarget.open)}>
            <summary><Icon name="info" size={15} /> Details</summary>
            <div><p className={snapshot.source === "ledger_fold" ? "aa-chat__source" : undefined}>{workflowSourceLabel(snapshot) || "Your conversation is kept on Gateway."}</p>
              {presentation.diagnostics.map((m) => <p key={m.id}>{m.content}</p>)}
              {!presentation.diagnostics.length && <p>Message usage and timing appear below each reply while these details are open.</p>}
            </div>
          </details>
        </div>
      }
      toolbar={{ onNewSession: props.onNewChat, copyTranscript: true, exportTranscript: { filename: "conversation.md", heading: props.title } }}
      footer={
        snapshot.error || outcome || notice || props.eventsNotice || answeredElsewhere || (interaction && deferred === pendingKey) ? (
          <div className="aa-chat__notes">
            {outcome ? <p className={`aa-note${snapshot.status === "failed" ? " aa-note--error" : ""}`} role="status">{outcome}</p> : null}
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
      messageProps={{
        renderFooter: (m) => {
          const status = m.runId === props.runId ? snapshot.status : props.sessionActivity?.content.find((c) => c.runId === m.runId)?.status;
          if (!status) return null;
          const target = sessionReadTarget(m.kind === "attachments" ? [...messages,m] : messages, m.runId || "", status);
          return target.message === m && !snapshot.loading && !snapshot.historyLoading && !snapshot.error && props.readScope ? <><span>{target.outcome}</span><SessionReadMarker ownerKey={props.readScope} receipt={{ sessionId: props.sessionId, revision: sessionContentRevision(m.runId || "", status), updatedAt: "" }} relatedReceipts={sessionOpeningReceipts(messages, props.sessionActivity?.content, m.runId || "")} enabled={props.canConsume} onRead={props.onRead} /></> : null;
        },
        stats: technical ? undefined : [],
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
    </div>
  );
}

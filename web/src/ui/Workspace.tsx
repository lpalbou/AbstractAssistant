import {WorkflowChat, useWorkflowSession, conversationSnapshot, useAvatarConversationPreferences, playConversationCue, conversationReply, presentInteraction, chatAuthorOf, mentionResend, type ChatAuthor, type ChatMentionCandidate, type ChatMentionSent, type ChatMentionsUnsent, type ChatMessageMention, type MentionResend} from "../vendor/abstractchat/conversation.js";
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
 * - `useGatewayVoice` + `AfVoiceMicButton` read replies aloud and dictate;
 * - `@` mentions (lib/mentions.ts): the composer offers `@agent` and the entities of `GET entities`;
 *   a send with mentions starts the person's turn (or steers the running one), then asks each entity
 *   in order through the gateway's mention door; each answer is a turn of the session, shown from its
 *   own view. A message that mentions entities and not `@agent` starts no agent run (the gateway
 *   keeps the words as a turn, `agent: "not_addressed"` + `turn_id`): its words and the entities'
 *   answers follow the turn on screen; no spinner, no reply line; an answer on its way is a bubble
 *   with its dots in the thread (operator round 6), never a line above the field.
 * Everything comes from the gateway; this page keeps no conversation and no token.
 */
import {
  projectReplayView,
  useAttachmentUploads,
  workflowPendingInteraction,
  workflowSourceLabel,
  WorkingDots,
} from "@abstractframework/panel-chat";
import type { ChatMessage } from "../vendor/abstractchat/conversation.js";
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
import { MENTIONS_UNAVAILABLE, deliverMentions, entityCandidates, entityMentionCards, gatewayLacksTurnAuthors, matchCandidates, mentionRoster, mentionStatusLine, mentionTurn, mentionedEntities, sentMessageMentions, startRunMentions, viewAgentNotAddressed, viewRepeatOf, withPendingMentions, withSentMentions, pendingMentionsFor, PENDING_MENTION_ID, type EntityMentionCard, type MentionAnswer, type MentionTurn, type PendingMention } from "../lib/mentions";
import { mentionCard } from "./MentionCard";
import { VoiceStage, Orb } from "./VoiceStage";
import type { AssistantPreferences } from "./useAssistantPreferences";

export function mintSessionId(): string {
  // The desktop mints `sess_<uuid hex>` (core/session_index.py); the gateway learns the id
  // with the first run.
  return `sess_${crypto.randomUUID().replace(/-/g, "")}`;
}

const TERMINAL = new Set(["completed", "failed", "cancelled"]);

/**
 * What the ended turn says when the transcript cannot: a failure's reason, or no written reply.
 * (Kit gap: the controller adds no line for a root run that ended failed or without an answer.)
 * A stop is the kit's own Stop state ("Stopped"), not repeated here. `entitiesAnswer`: the turn was
 * started with `mentions` (its message mentioned entities): its agent may say nothing (an empty
 * reply, which the gateway serves as no answer) and the entities' answers follow, so a turn without
 * a reply of its own says nothing. `notAddressed`: the gateway started no agent run for the turn
 * (the message mentioned entities, not `@agent`): no reply is expected, nothing is said.
 */
export function turnOutcome(runId: string, status: string, run: Record<string, unknown> | null, messages: ReadonlyArray<{ id?: string; role: string; runId?: string; live?: unknown; toolActivity?: unknown; content?: string }>, turn: { entitiesAnswer?: boolean; notAddressed?: boolean } = {}): string {
  if (!runId || !TERMINAL.has(status) || status === "cancelled") return "";
  if (status === "failed") {
    const why = typeof run?.error === "string" ? run.error.trim() : "";
    return why ? `The run failed: ${why}` : "The run failed (the gateway gave no reason).";
  }
  const answered = messages.some((m) => m.role === "assistant" && !m.live && !m.toolActivity &&
    (m.id === `final:${runId}` || String(m.id || "").startsWith(`answer:${runId}:`) || (m.runId === runId && Boolean(m.content?.trim()))));
  return answered || turn.entitiesAnswer || turn.notAddressed ? "" : "The run ended without a written reply.";
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
  // Turns whose prompt repeats another turn's words (`repeat_of`, an `@` mention), learned from
  // each view the transport reads; who writes each live reply, from its frames.
  const repeats = useRef(new Map<string, string>());
  // Turns started here with entity mentions and `@agent`: the entities answer for themselves, the
  // agent may say nothing.
  const entitiesAnswer = useRef(new Set<string>());
  // Turns whose agent was not addressed (entity mentions without `@agent`, operator 2026-11-10): the
  // gateway kept the words and started no agent run. From the start's answer (`agent:
  // "not_addressed"`, its `turn_id`) and from every view read (`agent_addressed: false`), so a turn
  // on screen is never busy and never "ended without a written reply", live or after a reload.
  const notAddressed = useRef(new Set<string>());
  // The words of such a message, shown here (no run shows them): message id -> the kept turn.
  const keptWords = useRef(new Map<string, string>());
  const liveAuthors = useRef(new Map<string, ChatAuthor | null>());
  const transport = useMemo(
    () => createAssistantTransport(client, {
      onDeltaError: (m) => setNotice(`A live reply frame was malformed and skipped: ${m}`),
      onView: (view) => {
        const r = viewRepeatOf(view);
        if (r) repeats.current.set(r.runId, r.repeatOf);
        for (const runId of viewAgentNotAddressed(view)) notAddressed.current.add(runId);
      },
      onLiveAuthor: (runId, author) => { if (runId) liveAuthors.current.set(runId, chatAuthorOf(author)); },
    }),
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
      sessionPolicy: true,
    });
    // The policy mode, reason and clamped list are the controller's: re-present when they change.
  }, [pending, controller, snapshot.records, snapshot.run, snapshot.sessionPolicyMode, snapshot.sessionPolicyReason, snapshot.sessionPolicyClamped, snapshot.sessionPolicy, pendingKey]);
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

  // A turn whose agent was not addressed has no reply on the way: never busy.
  const busy = Boolean(props.runId) && !notAddressed.current.has(props.runId) && !TERMINAL.has(snapshot.status) && !(snapshot.error && !snapshot.run);

  // ---- @ mentions ---------------------------------------------------------------------------
  // The names: `@agent`, then the entities this account may see, read once per conversation view.
  const entityNames = useRef<Promise<ChatMentionCandidate[]> | null>(null);
  // The same rows as cards (name, orb, state sentence), for the card on a mention chip; and the
  // mentions each turn this page started carried, by run (a sent message shows them as chips).
  const entityCards = useRef<Map<string, EntityMentionCard> | null>(null);
  const sentMentions = useRef(new Map<string, ChatMessageMention[]>());
  // The entities' answers on their way, one bubble each with its dots (operator round 6), by anchor.
  const [pendingAnswers, setPendingAnswers] = useState<{ anchor: string; entries: PendingMention[] } | null>(null);
  const mentionCandidates = useCallback((query: string) => {
    const names = (entityNames.current ??= client.listEntities().then((listed) => {
      entityCards.current = entityMentionCards(listed);
      return mentionRoster(entityCandidates(listed));
    }));
    names.catch(() => { if (entityNames.current === names) entityNames.current = null; });
    return names.then((list) => matchCandidates(list, query));
  }, [client]);
  // The conversation a first pick counts in: fixed for this view, so a new chat's first send
  // (which mints its session id) does not repeat the notice.
  const [mentionScope] = useState(() => props.sessionId || `new:${mintSessionId()}`);
  // A sentence about the mentions just sent; typing the next message dismisses it.
  const [mentionStatus, setMentionStatus] = useState("");
  const [mentionRouteMissing, setMentionRouteMissing] = useState(false);
  // The answers to this view's own mentions, shown after the turn that mentioned them until the
  // conversation moves to another turn (then they are earlier turns, read by the controller). A
  // message the agent was not addressed in also puts its words here, first (no run shows them).
  const [mentionAnswers, setMentionAnswers] = useState<{ anchor: string; messages: ChatMessage[] }>({ anchor: "", messages: [] });
  // A message whose mentions stopped partway (an entity could not answer): its words, its turn
  // (`turn`: shown after, `repeat_of`) and the mentions not answered. Sending the same words again
  // with chips asks only those (`mentionResend`): never a new turn of the person, never an entity
  // that already answered.
  const pendingResend = useRef<{ sid: string; message: string; turn: MentionTurn; resend: MentionResend } | null>(null);

  /** Ask each mentioned entity, in order, after the person's own turn (or guidance) was sent;
   * `turn` (`mentionTurn`): `anchor` is the turn the answers are shown after (the words are shown
   * once, there), `repeatOf` the turn sent as `repeat_of`, none for guidance (no turn carries its
   * words). `message`: a resend's key (the `mention_id`s it was first sent with, so the gateway
   * answers each once). Returns the mentions not answered when an entity could not answer (the
   * chips the composer keeps), else []. */
  const sendMentions = async (sid: string, turn: MentionTurn, text: string, mentions: readonly ChatMentionSent[], signal?: AbortSignal, message?: string): Promise<ChatMentionSent[]> => {
    const anchor = turn.anchor;
    // Each entity's answer shows as a bubble with its dots where it will land until it is shown.
    const looks = entityCards.current;
    setPendingAnswers({ anchor, entries: pendingMentionsFor(message || `${anchor}:${text.length}`, mentions, (m) => looks?.get(m.id)?.avatar) });
    const forThis = (update: (entries: PendingMention[]) => PendingMention[]) =>
      setPendingAnswers((now) => (now && now.anchor === anchor ? { anchor, entries: update(now.entries) } : now));
    const show = async (answer: MentionAnswer, mention: ChatMentionSent) => {
      // The answer is a session turn: read from its view, like a reload reads it.
      let shown: ChatMessage[];
      try {
        const read = await transport.replayView!.getView(answer.run_id, signal ? { signal } : {});
        if (read.notModified) throw new Error("the gateway answered without a view");
        shown = projectReplayView(read.view).messages as ChatMessage[];
      } catch (error) {
        if (signal?.aborted) throw error;
        shown = [{ id: `mention:${answer.run_id}:unshown`, role: "system", level: "warn", title: "Mention", content: `${mention.name} answered, but the answer cannot be shown here (${error instanceof Error ? error.message : String(error)}). It is kept in this conversation.` }];
      }
      // The words are shown once: in the turn the mention repeats (the person's started turn, or
      // the turn kept for a message the agent was not addressed in), else after the running turn.
      repeats.current.set(answer.run_id, turn.repeatOf || anchor);
      if (!mounted.current) return;
      setMentionAnswers((prev) => ({ anchor, messages: [...(prev.anchor === anchor ? prev.messages : []), ...shown] }));
      forThis((entries) => entries.map((e) => (e.mention.id === mention.id && e.mention.index === mention.index ? { ...e, runId: answer.run_id } : e)));
    };
    // Every answer is shown before deliverMentions returns: a bubble still pending then has no answer
    // coming (refused, stopped, unasked) and goes, on success or failure.
    // A refusal that does not stop the run: its bubble goes and its sentence shows now (F3).
    const skipped = (mention: ChatMentionSent, sentence: string) => {
      forThis((entries) => entries.filter((e) => !(e.mention.id === mention.id && e.mention.index === mention.index)));
      if (mounted.current) setMentionStatus(sentence);
    };
    const outcome = await deliverMentions({ text, mentions, repeatOf: turn.repeatOf, ...(message ? { message } : {}), post: (req, s) => client.mention(sid, req, s), ...(signal ? { signal } : {}), onAnswer: show, onSkipped: skipped })
      .finally(() => setPendingAnswers((now) => (now && now.anchor === anchor ? null : now)));
    if (outcome.stopped && outcome.unsent.length) pendingResend.current = { sid, message: outcome.message, turn, resend: { text, repeatOf: turn.repeatOf || null, unsent: outcome.unsent } };
    if (!mounted.current) return outcome.unsent;
    // A name the gateway refused (hidden, elsewhere) is read again on the next `@`.
    if (outcome.notes.length) entityNames.current = null;
    if (outcome.unavailable) setMentionRouteMissing(true);
    setMentionStatus(mentionStatusLine(outcome));
    // Each answer is a new turn of the session: the list's turns and latest turn moved.
    if (outcome.answered.length) props.onTurnEnded();
    // An entity that could not answer: the message goes back to the composer, with the chips not
    // answered (the send resolves naming them; the kit keeps only those).
    if (outcome.stopped) setDraft((current) => (current.trim() ? current : text));
    return outcome.unsent;
  };
  const unsentResult = (unsent: ChatMentionSent[]): ChatMentionsUnsent | undefined => (unsent.length ? { unsentMentions: unsent } : undefined);

  // ---- send ---------------------------------------------------------------------------------
  const send = useCallback(
    async (text: string, ctx?: { signal?: AbortSignal; mentions?: readonly ChatMentionSent[] }): Promise<ChatMentionsUnsent | undefined> => {
      const mentions = ctx?.mentions ?? [];
      voiceRef.current.stop_tts();
      setMentionStatus("");
      // The same words again, with chips, after a stop: only those mentions, nothing else. A message
      // with `@agent` is a new message (it starts the agent's turn).
      const held = pendingResend.current;
      pendingResend.current = null;
      const again = held && held.sid === ensureSession() && !mentions.some((m) => m.kind === "agent") ? mentionResend(held.resend, text, mentions) : null;
      if (held && again) {
        const unsent = await sendMentions(held.sid, held.turn, held.resend.text, again, ctx?.signal, held.message);
        if (mounted.current && !unsent.length) setDraft("");
        return unsentResult(unsent);
      }
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
        // Guidance (or an answer) starts no turn: its mentions name no `repeat_of` (`mentionTurn`).
        if (mentionedEntities(mentions).length) return unsentResult(await sendMentions(ensureSession(), mentionTurn({ steered: props.runId }), text, mentions, ctx?.signal));
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
      // The chips ride the start (`mentions`, `@agent` as "agent"). Entities without `@agent`: the
      // gateway starts no agent run. With it, the agent is told they answer for themselves.
      const mentioned = startRunMentions(mentions);
      // Never retried here: a failure keeps the draft and says why; the person resends.
      const started = await client.startRun(
        start.source === "gateway_default"
          ? { flow_id: "@default", interface: start.interface, session_id: sid, input_data, ...(avatarMode ? { conversation: true } : {}), ...mentioned }
          : { flow_id: start.flow_id, bundle_id: start.bundle_id, bundle_version: start.bundle_version, registry_scope: start.registry_scope, session_id: sid, input_data, ...(avatarMode ? { conversation: true } : {}), ...mentioned },
      );
      // The message shows the chips its send carried (panel-chat 0.9.13), with their looks.
      const shown = sentMessageMentions(mentions, (m) => (m.kind === "entity" ? entityCards.current?.get(m.id)?.avatar : null));
      const mentionsField = shown.length ? { mentions: shown } : {};
      if (started.agentNotAddressed) {
        // No agent run: the gateway kept the words as a turn (`turn_id`) no run shows. The words
        // follow the turn on screen, the entities' answers after them; the mentions name that turn.
        notAddressed.current.add(started.turn_id);
        if (!mounted.current) return;
        uploads.clear();
        setDraft("");
        setNotice("");
        const turn = mentionTurn({ unaddressed: started.turn_id, after: props.runId });
        // No `runId` on the words: the kit reads a run's input for each one (`kept` folds instead).
        const words: ChatMessage = { id: `kept:${started.turn_id}`, role: "user", kind: "prompt", content: text, ...mentionsField };
        keptWords.current.set(words.id!, started.turn_id);
        setMentionAnswers((prev) => ({ anchor: turn.anchor, messages: [...(prev.anchor === turn.anchor ? prev.messages : []), words] }));
        return unsentResult(await sendMentions(sid, turn, text, mentions, ctx?.signal));
      }
      const { run_id } = started;
      if (shown.length) sentMentions.current.set(run_id, shown);
      if (mentionedEntities(mentions).length) entitiesAnswer.current.add(run_id);
      if (!mounted.current) return;
      startedHere.current = run_id;
      uploads.clear();
      setDraft("");
      setNotice("");
      props.onStarted(run_id, sid);
      if (mentionedEntities(mentions).length) return unsentResult(await sendMentions(sid, mentionTurn({ started: run_id }), text, mentions, ctx?.signal));
      return undefined;
    },
    // sendMentions reads refs, state setters, the client and the transport.
    [client, transport, ensureSession, uploads, props, busy, avatarMode, interaction, replyContext, controller, snapshot.view],
  );

  // Who answered: the gateway's turn `author` on every reply (the kit's header) and on every live
  // reply frame; mention answers follow the turn they answer (`repeat_of`).
  // ("" = a new conversation: a message the agent was not addressed in starts no run to follow.)
  const answersShown = mentionAnswers.messages.length && mentionAnswers.anchor === props.runId ? mentionAnswers.messages : null;
  const presentation = useMemo(
    () => conversationPresentation(answersShown ? [...withSentMentions(snapshot.messages, sentMentions.current), ...answersShown] : withSentMentions(snapshot.messages, sentMentions.current), { repeats: repeats.current, liveAuthors: liveAuthors.current, kept: keptWords.current, notAddressed: notAddressed.current }),
    // The maps and the set are filled by the transport before the messages they label change.
    [snapshot.messages, answersShown],
  );
  // An older gateway: no mention door (it answered 404) or turns without `author`.
  const mentionsUnavailable = mentionRouteMissing || gatewayLacksTurnAuthors(snapshot.messages) ? MENTIONS_UNAVAILABLE : null;
  const messages = presentation.conversation;
  const reply = replyToRead(messages, props.runId);
  useEffect(() => {
    if (snapshot.status !== "completed" || startedHere.current !== props.runId || !reply) return;
    startedHere.current = "";
    if (props.voicePrefs.read_aloud === true && !props.voicePrefs.reply_muted && voice.tts_supported && !voice.voice_ptt_recording && !voice.voice_ptt_busy && (!avatarMode || (!avatarAttended && !draft.trim())))
      void voice.toggle_tts(String(reply.id || props.runId), reply.content);
  }, [snapshot.status, props.runId, props.voicePrefs.read_aloud, props.voicePrefs.reply_muted, reply, voice]);
  const listWords = pending && !answeredElsewhere ? "Needs you" : "";
  // A turn started here with entity mentions: an agent that said nothing, or was not addressed,
  // shows no answer and no line; the entities' answers follow.
  const outcome = turnOutcome(props.runId, snapshot.status, snapshot.run, snapshot.messages, { entitiesAnswer: entitiesAnswer.current.has(props.runId), notAddressed: notAddressed.current.has(props.runId) });
  const presence = assistantPresence({ recording: voice.voice_ptt_recording, transcribing: voice.voice_ptt_busy,
    playback: voice.tts_playback.status === "playing" && !voice.tts_speaking ? "loading" : voice.tts_playback.status, pending: Boolean(pending && !answeredElsewhere), busy,
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
        avatar: <Orb voice={voice} prefs={props.appearance} pose={voice.voice_ptt_recording ? "listening" : voice.tts_speaking ? "speaking" : snapshot.run?.paused === true && !TERMINAL.has(snapshot.status) ? "waiting" : presence.pose} size={320} onError={() => setNotice("The avatar could not load. Voice and messages still work.")} />,
        ...conversationSnapshot(snapshot),
        listening: voice.voice_ptt_recording,
        speaking: voice.tts_speaking,
        preferences: avatarPreferences.preferences,
        onPreferencesChange: avatarPreferences.setPreferences,
        onCue: (cue) => { void playConversationCue(cue).catch((reason) => setNotice(reason instanceof Error ? reason.message : String(reason))); },
        onInterruptSpeech: () => voice.stop_tts(),
        onReplyContext: setReplyContext,
        onAttendedChange: setAvatarAttended,
        narrate: props.voicePrefs.read_aloud === true && !props.voicePrefs.reply_muted,
        onNarrate: (message) => { if (voice.tts_supported) void voice.toggle_tts(message.id || message.content, message.content); },
      } : undefined}
                artifactFetch={client.fetchGateway}
                attachmentScope={JSON.stringify([props.readScope,props.sessionId])}
                attachmentRun={{runId:props.runId,output:snapshot.run?.output}}
      className="aa-chat"
      messages={withPendingMentions(messages, pendingAnswers && pendingAnswers.anchor === props.runId ? pendingAnswers.entries : [])}
      draft={draft}
      onDraftChange={(next) => { setDraft(next); if (mentionStatus) setMentionStatus(""); }}
      onSend={send}
      mentionCandidates={mentionCandidates}
      mentionSessionKey={mentionScope}
      mentionStatus={mentionStatus || null}
      mentionsUnavailable={mentionsUnavailable}
      busy={busy}
      steer={avatarMode && busy ? { modes: ["guide"], onSteer: async (text, _mode, ctx) => ({ ...(await send(text, { mentions: ctx?.mentions ?? [] })), accepted: true }), parked: snapshot.status === "waiting" } : undefined}
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
        renderMentionCard: (mention) => mentionCard(mention, entityCards.current),
        renderFooter: (m) => {
          // An answer on its way: its three dots in its bubble.
          if (String(m.id || "").startsWith(PENDING_MENTION_ID)) return <WorkingDots label={`${m.author?.name || "The entity"} is answering`} />;
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

/**
 * The Assistant space (ADR 0007, v1): conversations on the left, the open
 * conversation on the right. Everything comes from the gateway; the page
 * keeps nothing between visits (no localStorage, no token).
 */
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import { followTurn } from "../gateway/follow";
import { GatewayClient, resumeWaitCommand, type AttachmentRef } from "../gateway/client";
import type { AssistantHost } from "../host";
import { messagesFromHistoryBundle } from "../lib/history";
import { liveAnswerText, waitStillMatches } from "../lib/run_events";
import { buildRunInputData } from "../lib/run_input";
import { runToolsFromDiscovery } from "../lib/tool_policy";
import { foldSessionRows, STATE_WORDS, type SessionRow } from "../lib/session_fold";
import { eventTouchesList, loadTitles } from "../lib/titles";
import { createTurnStore, type TurnStore } from "../lib/turn_store";
import type { ChatMessage, PendingWait } from "../lib/types";
import { ChunkPlayer, base64ToBytes, extensionFor, interpretTtsLine, startRecording } from "../lib/voice";
import { selectWorkflow } from "../lib/workflow_selection";
import { Composer } from "./Composer";
import { Conversation } from "./Conversation";
import { SessionList } from "./SessionList";

const SESSION_PAGE_RUNS = 200; // core/gateway_sessions.py SESSION_PAGE_RUNS

function mintSessionId(): string {
  // The desktop mints `sess_<uuid hex>` (core/session_index.py); the gateway
  // learns the id with the first run.
  return `sess_${crypto.randomUUID().replace(/-/g, "")}`;
}

const EMPTY_STORE: TurnStore = createTurnStore("");

export function Workspace(props: { client: GatewayClient; host: AssistantHost; onSignedOut: () => void; onSignOut: () => void }) {
  const { client, host } = props;
  const [rows, setRows] = useState<SessionRow[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [titles, setTitles] = useState<Record<string, string>>({});
  const [listError, setListError] = useState("");
  const [sessionId, setSessionId] = useState<string>("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [banner, setBanner] = useState<{ tone: "info" | "warn" | "error"; text: string } | null>(null);
  const [turn, setTurn] = useState<TurnStore>(EMPTY_STORE);
  const [speaking, setSpeaking] = useState<string>("");
  // Below 1024 px the conversation list is a full-screen sheet (CSS); this opens it.
  const [listOpen, setListOpen] = useState(false);
  const stopFollow = useRef<() => void>(() => {});
  const playerRef = useRef<ChunkPlayer | null>(null);
  const titleCache = useRef(new Map<string, string>());
  const [titleError, setTitleError] = useState("");
  const visibleIds = useRef(new Set<string>());
  // Callbacks from the parent are read through a ref: a new function on a
  // parent render must not re-run the list fetch or re-open the event stream.
  const signedOutRef = useRef(props.onSignedOut);
  signedOutRef.current = props.onSignedOut;

  const turnState = useSyncExternalStore(turn.subscribe, turn.getState);
  const turnRef = useRef(turn);
  turnRef.current = turn;

  const fail = useCallback(
    (err: unknown, prefix = "") => {
      const status = (err as { status?: number })?.status;
      if (status === 401) signedOutRef.current();
      setBanner({ tone: "error", text: `${prefix}${err instanceof Error ? err.message : String(err)}` });
    },
    [],
  );

  const refreshSessions = useCallback(async () => {
    try {
      const page = await client.listSessionRuns(SESSION_PAGE_RUNS);
      const folded = foldSessionRows(page);
      setRows(folded.rows);
      visibleIds.current = new Set(folded.rows.map((r) => r.session_id));
      setTruncated(folded.truncated);
      setListError("");
      // Opening prompts name the rows: a few at a time, cached, failures retried next refresh.
      const load = await loadTitles(folded.rows, titleCache.current, (rid) => client.inputData(rid));
      setTitleError(load.failed ? `${load.failed} conversation title${load.failed === 1 ? "" : "s"} could not be loaded; they will be asked again.` : "");
      setTitles(Object.fromEntries(titleCache.current));
    } catch (err) {
      setListError(err instanceof Error ? err.message : String(err));
      if ((err as { status?: number })?.status === 401) signedOutRef.current();
    }
  }, [client]);

  useEffect(() => {
    void refreshSessions();
  }, [refreshSessions]);

  // The person's event stream: a run started or finished anywhere (another
  // device, an automation's discussion) refreshes the list; a wait answered
  // elsewhere closes its card here (api.md "Your event stream").
  useEffect(() => {
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    (async () => {
      try {
        const page = await client.meEvents(0, 1);
        const head = typeof page.head === "number" ? page.head : 0;
        await client.followMeEvents(head, (ev) => {
          const type = String(ev.type || "");
          const data = (ev.data || {}) as Record<string, unknown>;
          if ((type === "run.started" || type === "run.finished") && eventTouchesList(data, visibleIds.current)) {
            clearTimeout(timer);
            timer = setTimeout(() => void refreshSessions(), 500);
          }
          if (type === "attention.seen" && typeof data.wait_key === "string" && typeof data.run_id === "string") {
            turnRef.current.dispatch({
              type: "wait_closed",
              run_id: data.run_id,
              wait_key: data.wait_key,
              step_id: typeof data.step_id === "string" ? data.step_id : undefined,
              note: `Answered (${String(data.outcome || "answered")}).`,
            });
          }
        }, abort.signal);
      } catch (err) {
        if (!abort.signal.aborted) setBanner({ tone: "warn", text: `Updates from your other devices are off: ${err instanceof Error ? err.message : String(err)}` });
      }
    })();
    return () => {
      abort.abort();
      clearTimeout(timer);
    };
  }, [client, refreshSessions]);

  const attach = useCallback(
    (rootRunId: string) => {
      stopFollow.current();
      const store = createTurnStore(rootRunId);
      setTurn(store);
      stopFollow.current = followTurn({
        client,
        rootRunId,
        dispatch: store.dispatch,
        getState: store.getState,
        onError: (m) => setBanner({ tone: "warn", text: m }),
      });
    },
    [client],
  );

  // When a turn ends, its answer joins the transcript and the list refreshes.
  useEffect(() => {
    const s = turnState;
    if (!s.root_run_id || !["completed", "failed", "cancelled"].includes(s.status)) return;
    setMessages((prev) => {
      if (prev.some((m) => m.id === `${s.root_run_id}:answer`)) return prev;
      const extra: ChatMessage[] = [];
      if (s.answer) extra.push({ id: `${s.root_run_id}:answer`, role: "assistant", text: s.answer, run_id: s.root_run_id, ts: new Date().toISOString() });
      else
        extra.push({
          id: `${s.root_run_id}:answer`,
          role: "notice",
          text: s.status === "cancelled" ? "Stopped." : s.error ? `The run failed: ${s.error}` : "The run ended without a written reply.",
          run_id: s.root_run_id,
          ts: new Date().toISOString(),
        });
      return [...prev, ...extra];
    });
    void refreshSessions();
  }, [turnState, refreshSessions]);

  const openSession = useCallback(
    async (row: SessionRow) => {
      stopFollow.current();
      setTurn(EMPTY_STORE);
      setSessionId(row.session_id);
      setMessages([]);
      setBanner(null);
      try {
        const seed = messagesFromHistoryBundle(await client.historyBundle(row.latest_run_id));
        const live = row.state === "running" || row.state === "waiting";
        setMessages(live ? seed.messages.filter((m) => m.id !== `${row.latest_run_id}:answer`) : seed.messages);
        if (seed.warnings.length) setBanner({ tone: "warn", text: `The gateway's history is incomplete: ${seed.warnings.join("; ")}` });
        if (live) attach(row.latest_run_id);
      } catch (err) {
        fail(err, "This conversation could not be opened: ");
      }
    },
    [client, attach, fail],
  );

  const newChat = useCallback(() => {
    stopFollow.current();
    setTurn(EMPTY_STORE);
    setSessionId("");
    setMessages([]);
    setBanner(null);
  }, []);

  const busy = Boolean(turnState.root_run_id) && !["completed", "failed", "cancelled"].includes(turnState.status);

  const send = useCallback(
    async (text: string, files: File[]): Promise<boolean> => {
      const sid = sessionId || mintSessionId();
      try {
        const refs: AttachmentRef[] = [];
        for (const f of files) refs.push((await client.uploadAttachment(sid, f, f.name, f.type ? { content_type: f.type } : {})).ref);
        const [bundles, prefs, tools] = await Promise.all([
          client.executableBundles("abstractassistant.agent.v1"),
          client.accountPreferences(),
          client.discoveryTools(),
        ]);
        const start = selectWorkflow(bundles, prefs);
        const image = refs.find((r) => String(r.content_type || "").startsWith("image/"));
        // Explicit tool lists, as the desktop sends them (ADR 0007 §6).
        const input_data = buildRunInputData({ prompt: text, attachments: refs, primary_image_artifact: image ?? null, stream: true, ...runToolsFromDiscovery(tools) });
        const { run_id } = await client.startRun(
          start.source === "gateway_default"
            ? { flow_id: "@default", interface: start.interface, session_id: sid, input_data }
            : { flow_id: start.flow_id, bundle_id: start.bundle_id, bundle_version: start.bundle_version, registry_scope: start.registry_scope, session_id: sid, input_data },
        );
        setSessionId(sid);
        setMessages((prev) => [
          ...prev,
          {
            id: `${run_id}:user`,
            role: "user",
            text,
            run_id,
            ts: new Date().toISOString(),
            ...(refs.length ? { attachments: refs.map((r) => ({ $artifact: String(r.$artifact), filename: String(r.filename || ""), content_type: String(r.content_type || "") })) } : {}),
          },
        ]);
        attach(run_id);
        return true;
      } catch (err) {
        // Never retried: the person checks the conversation, then resends.
        fail(err, "Not sent: ");
        return false;
      }
    },
    [sessionId, client, attach, fail],
  );

  const answerWait = useCallback(
    async (w: PendingWait, answer: { approved: boolean } | { response: string }) => {
      const store = turnRef.current;
      store.dispatch({ type: "wait_sending", run_id: w.run_id, wait_key: w.wait_key, step_id: w.step_id });
      try {
        if (store.getState().follow === "lost") throw new Error("Live updates stopped: reopen the conversation before answering.");
        // Re-read the run first, as the iPhone does: another device may have
        // answered, and a NEWER batch may wait on the same reused key.
        const check = waitStillMatches(w, await client.getRun(w.run_id));
        if (!check.ok) {
          store.dispatch({ type: "wait_closed", run_id: w.run_id, wait_key: w.wait_key, step_id: w.step_id, stale: true, note: check.why });
          return;
        }
        const payload = "approved" in answer ? (answer.approved ? { approved: true } : { approved: false, reason: "Denied by user" }) : { response: answer.response };
        await client.submitCommand(resumeWaitCommand(w.run_id, w.wait_key, payload));
        store.dispatch({ type: "wait_closed", run_id: w.run_id, wait_key: w.wait_key, step_id: w.step_id, note: "approved" in answer ? (answer.approved ? "Approved." : "Denied.") : "Answered." });
      } catch (err) {
        store.dispatch({ type: "wait_failed", run_id: w.run_id, wait_key: w.wait_key, step_id: w.step_id, note: err instanceof Error ? err.message : String(err) });
      }
    },
    [client],
  );

  const stop = useCallback(async () => {
    const root = turnRef.current.getState().root_run_id;
    if (!root) return;
    try {
      await client.cancelRun(root);
      setBanner({ tone: "info", text: "Stopping…" });
    } catch (err) {
      fail(err, "Could not stop: ");
    }
  }, [client, fail]);

  const readAloud = useCallback(
    async (m: ChatMessage) => {
      playerRef.current?.stop();
      playerRef.current = null;
      if (speaking === m.id) {
        setSpeaking("");
        return;
      }
      if (!host.capabilities.audioPlayback.available) {
        setBanner({ tone: "warn", text: host.capabilities.audioPlayback.reason });
        return;
      }
      const player = new ChunkPlayer();
      playerRef.current = player;
      setSpeaking(m.id);
      try {
        for await (const line of client.speechStream(m.run_id, m.text)) {
          const ev = interpretTtsLine(line);
          if (playerRef.current !== player) return;
          if (ev.kind === "audio") await player.enqueue(base64ToBytes(ev.wav_b64));
          else if (ev.kind === "queued") setBanner({ tone: "info", text: ev.message });
          else if (ev.kind === "error") throw new Error(ev.message);
          else if (ev.kind === "done" || ev.kind === "cancelled") break;
        }
        await player.drained();
      } catch (err) {
        fail(err, "Read aloud: ");
      } finally {
        if (playerRef.current === player) {
          playerRef.current = null;
          setSpeaking("");
        }
      }
    },
    [client, host, speaking, fail],
  );

  const dictate = useMemo(() => {
    if (!host.capabilities.microphone.available) return { available: false as const, reason: host.capabilities.microphone.reason };
    return {
      available: true as const,
      start: async () => {
        const rec = await startRecording();
        return {
          cancel: rec.cancel,
          finish: async (): Promise<string> => {
            const { blob, type } = await rec.stop();
            const sid = sessionId || mintSessionId();
            if (!sessionId) setSessionId(sid);
            const name = `ask.${extensionFor(type)}`;
            const up = await client.uploadAttachment(sid, blob, name, { content_type: type, source_path: `voice/dictation/${crypto.randomUUID()}.${extensionFor(type)}` });
            return client.transcribe(up.ownerRunId || `session_memory_${sid}`, String(up.ref.$artifact));
          },
        };
      },
    };
  }, [host, client, sessionId]);

  const current = rows.find((r) => r.session_id === sessionId);
  return (
    <div className={`aa-shell${listOpen ? " aa-shell--list" : ""}`}>
      <SessionList
        rows={rows}
        titles={titles}
        truncated={truncated}
        error={listError}
        notice={titleError}
        activeId={sessionId}
        onOpen={(r) => {
          setListOpen(false);
          void openSession(r);
        }}
        onNew={() => {
          setListOpen(false);
          newChat();
        }}
        onClose={() => setListOpen(false)}
        onRefresh={() => void refreshSessions()}
        onSignOut={props.onSignOut}
      />
      <main className="aa-main">
        <header className="aa-main__header">
          <button type="button" className="aa-button aa-only-compact" aria-label="Conversations" onClick={() => setListOpen(true)}>
            Conversations
          </button>
          <h1 className="aa-main__title">{sessionId ? titles[sessionId] || "Conversation" : "New conversation"}</h1>
          {current && STATE_WORDS[current.state] ? <span className={`aa-state aa-state--${current.state}`}>{STATE_WORDS[current.state]}</span> : null}
        </header>
        {banner ? (
          <div className={`aa-banner aa-banner--${banner.tone}`} role={banner.tone === "error" ? "alert" : "status"}>
            <span>{banner.text}</span>
            <button type="button" className="aa-link" onClick={() => setBanner(null)}>
              Dismiss
            </button>
          </div>
        ) : null}
        <Conversation
          messages={messages}
          turn={turnState}
          liveText={liveAnswerText(turnState)}
          speakingId={speaking}
          canSpeak={host.capabilities.audioPlayback.available}
          onReadAloud={(m) => void readAloud(m)}
          onAnswer={(w, a) => void answerWait(w, a)}
        />
        <Composer busy={busy} onSend={send} onStop={() => void stop()} dictation={dictate} />
      </main>
    </div>
  );
}

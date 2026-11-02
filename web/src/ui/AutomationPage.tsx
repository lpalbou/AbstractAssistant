import { Icon, describeToolCall, isApiError, readableKey, trustAfterApproveAll, waitToolCalls, type AttentionWait, type AutomationDefinition, type AutomationSummary, type OccurrenceRow, type ToolCatalogItem } from "@abstractframework/ui-kit";
import { WorkflowChat } from "../vendor/abstractchat/conversation.js";
import { automationCardNext, automationCardSchedule } from "../vendor/abstractsessions/session_cards.js";
import { useCallback, useEffect, useRef, useState } from "react";

import type { GatewayClient } from "../gateway/client";
import { automationToolModes, automationTrust, setAutomationTrust } from "../lib/automation_tools";
import { RUNS_SHOWN, latestDiscussable, runMessages, waitingRun } from "../lib/automations";
import { answerToolWait, automationErrorText, type Automations } from "./useAutomations";

/** "0:07", "1:05": how long a Run has been starting. */
export function elapsedText(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** The automation's task (what it is asked each run), from its definition. */
export function taskOf(definition: AutomationDefinition | null): string {
  const prompt = (definition?.target as { input_data?: { prompt?: unknown } } | undefined)?.input_data?.prompt;
  return typeof prompt === "string" ? prompt : "";
}

/**
 * One automation, as the watch shows it: its name, how many times it ran, how often and when next
 * (Paused for a paused one), Run (Stop while a run is in progress) and Edit, its task; then its
 * runs as a conversation (what its trigger sent, the answer), the latest ten. Opening it marks its
 * new results seen. Talking here never writes into the automation: it opens a conversation about
 * its latest run. A run waiting for you opens in the conversation view, where it is answered.
 */
export function AutomationPage(props: {
  client: GatewayClient;
  automations: Automations;
  summary: AutomationSummary;
  onEdit: () => void;
  /** A conversation was started (about this automation, or a run to answer): open it. */
  onOpenConversation: (sessionId: string, runId: string) => void;
}) {
  const { api, replace, catalog, approveTrusted, trustScope } = props.automations;
  const id = props.summary.automation_id;
  const [summary, setSummary] = useState(props.summary);
  const [definition, setDefinition] = useState<AutomationDefinition | null>(null);
  const [runs, setRuns] = useState<OccurrenceRow[] | null>(null);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now());
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState("");
  const [tools, setTools] = useState<ToolCatalogItem[]>([]);
  const [trust, setTrust] = useState<string[]>(() => automationTrust(trustScope, props.summary.automation_id));
  const [answering, setAnswering] = useState(false);
  useEffect(() => void catalog().then(setTools, () => undefined), [catalog]);
  const mounted = useRef(true);
  useEffect(() => () => void (mounted.current = false), []);
  useEffect(() => setSummary(props.summary), [props.summary]);

  /** Reads it again: the row (to the list too) and its definition. */
  const reread = useCallback(async () => {
    let detail = await api.getAutomation(id);
    // A request its Approve all covers is answered by this browser (the watch's rule).
    if (await approveTrusted([detail.summary]).catch(() => false)) detail = await api.getAutomation(id);
    if (!mounted.current) return detail.summary;
    setSummary(detail.summary);
    setDefinition(detail.definition);
    replace(detail.summary);
    return detail.summary;
  }, [api, id, replace]);

  const readRuns = useCallback(async () => {
    const page = await api.listOccurrences(id, { limit: RUNS_SHOWN });
    if (mounted.current) setRuns(page.items);
  }, [api, id]);

  // Opening: its runs, then its new results are seen (read fresh: the cursor known before a run
  // ended would leave that run new).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await readRuns();
        const fresh = await reread();
        if (cancelled) return;
        const attention = fresh.attention;
        if (attention.cursor && (attention.unseen_count > 0 || attention.unread)) {
          // As the watch: a failed "seen" leaves the results new, nothing else to say.
          await api.markSeen(id, attention.cursor).then(async () => { if (!cancelled) await reread(); }, () => undefined);
        }
      } catch (e) {
        if (!cancelled) setError(automationErrorText(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [api, id, readRuns, reread]);

  // While a run is in progress (or starting): read it every 3 s; its runs again once it is over.
  const running = Boolean(summary.current_occurrence) || summary.attention.pending_waits > 0;
  useEffect(() => {
    if (!running && starting === null) return;
    const timer = setInterval(() => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
      setNow(Date.now());
      void reread().then((fresh) => {
        if (!mounted.current) return;
        if (fresh.current_occurrence) setStarting(null);
        else if (starting === null || Date.now() - starting > 20_000) {
          setStarting(null);
          void readRuns();
        }
      }, () => undefined);
    }, starting !== null ? 1000 : 3000);
    return () => clearInterval(timer);
  }, [running, starting, reread, readRuns]);

  const run = async () => {
    setError("");
    setBusy(true);
    setStarting(Date.now());
    try {
      await api.sendAutomationCommand(id, { type: "automation.run_now" });
    } catch (e) {
      setStarting(null);
      const inner = isApiError(e) ? e : (e as { error?: unknown }).error;
      if (isApiError(inner) && inner.status === 409) {
        setError("It is already running.");
        void reread();
      } else setError(`Couldn't start it. ${automationErrorText(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    setError("");
    setBusy(true);
    try {
      await api.sendAutomationCommand(id, { type: "automation.stop_current" });
      await reread();
    } catch {
      setError("Couldn't stop it.");
    } finally {
      setBusy(false);
    }
  };

  const talk = async (text: string) => {
    const index = latestDiscussable(runs ?? []);
    if (index === null) throw new Error("It has not run yet: there is nothing to talk about.");
    const started = await api.discuss(id, { occurrence_index: index, prompt: text });
    setDraft("");
    props.onOpenConversation(started.session_id, started.run_id);
  };

  const answer = async (row: OccurrenceRow) => {
    try {
      const r = await props.client.getRun(row.run_id);
      const session = typeof r.session_id === "string" ? r.session_id : "";
      if (!session) throw new Error("This run has no conversation to open.");
      props.onOpenConversation(session, row.run_id);
    } catch (e) {
      setError(automationErrorText(e));
    }
  };

  // The run's tool request (the newest), answered here as on the watch's approval page.
  const toolWait: AttentionWait | null = summary.attention.waits.filter((w) => w.kind === "tool_approval" && waitToolCalls(w)).slice(-1)[0] ?? null;
  const calls = toolWait ? waitToolCalls(toolWait) ?? [] : [];
  const modes = definition ? automationToolModes(tools, definition) : null;
  const widened = modes && calls.length && calls.every((c) => modes[c.name] && modes[c.name] !== "off")
    ? trustAfterApproveAll(tools, modes, calls.map((c) => c.name), trust) : null;
  const decide = async (approved: boolean, all = false) => {
    if (!toolWait) return;
    setAnswering(true);
    setError("");
    try {
      if (all && widened) {
        setAutomationTrust(trustScope, id, widened);
        setTrust(widened);
      }
      await answerToolWait(props.client, toolWait, approved);
      await reread();
    } catch (e) {
      setError(automationErrorText(e));
    } finally {
      setAnswering(false);
    }
  };
  const askAgain = () => {
    setAutomationTrust(trustScope, id, []);
    setTrust([]);
  };

  const task = taskOf(definition);
  const count = Number.isSafeInteger(summary.occurrence_count) ? summary.occurrence_count : null;
  const paused = summary.status === "paused";
  const ended = summary.status === "completed" || summary.status === "failed";
  const next = summary.status === "active" ? automationCardNext(summary.next_run_at, now) : "";
  const waiting = toolWait ? null : waitingRun(runs ?? []);
  const showStop = Boolean(summary.current_occurrence) && starting === null;
  const messages = runMessages(runs ?? []);
  const canTalk = latestDiscussable(runs ?? []) !== null;

  return (
    <div className="aa-automation-page" data-automation-id={id}>
      <WorkflowChat
        className="aa-chat"
        messages={messages}
        draft={draft}
        onDraftChange={setDraft}
        onSend={talk}
        disabled={!canTalk}
        placeholder={canTalk ? "Talk about its latest run" : "It has not run yet"}
        emptyState={<div className="aa-empty"><h2>{runs === null && !error ? "Loading its runs…" : "It has not run yet"}</h2></div>}
        header={
          <div className="aa-automation-head">
            <div className="aa-automation-head__line">
              <h1 className="aa-chat__title" title={summary.title}>{summary.title || "Automation"}</h1>
              <div className="aa-automation-head__actions">
                <button type="button" className="aa-button" onClick={props.onEdit} aria-label="Edit"><Icon name="edit" size={16} /> Edit</button>
                <button type="button" className={`aa-button${showStop ? " aa-button--stop" : " aa-button--primary"}`} disabled={busy || ended}
                  onClick={() => void (showStop ? stop() : run())} aria-label={starting !== null ? "Starting the run" : showStop ? "Stop this run" : "Run"}>
                  {starting !== null ? <Icon name="loader" size={16} /> : <Icon name={showStop ? "stop" : "play"} size={16} />} {showStop ? "Stop" : "Run"}
                </button>
              </div>
            </div>
            <p className="aa-automation-head__facts">
              {count !== null && <span title={`Ran ${count} ${count === 1 ? "time" : "times"}`}><Icon name="loop" size={14} /> {count}</span>}
              <span title={summary.trigger_text || summary.schedule_rule_text || ""}>
                <Icon name={paused ? "pause" : ended ? "stop" : "clock"} size={14} /> {paused ? "Paused" : ended ? "Ended" : automationCardSchedule(summary)}
              </span>
              {next && <span title="Next run"><Icon name="playCircle" size={14} /> {next}</span>}
            </p>
            {starting !== null && <p className="aa-automation-head__starting" role="status">{running ? "Running…" : "Starting…"} {elapsedText(now - starting)}</p>}
            {task && task !== summary.title && <p className="aa-automation-head__task"><span>Task</span>{task}</p>}
            {summary.context_mode === "growing" && <p className="aa-automation-head__note"><Icon name="loop" size={14} /> Builds on its earlier runs</p>}
            {trust.length > 0 && (
              <div className="aa-trust" role="group" aria-label="Allowed for its runs">
                <p className="aa-trust__title"><Icon name="check" size={14} /> Allowed for its runs</p>
                <p>{trust.map(readableKey).join(", ")}</p>
                <p className="aa-trust__note">Approved by this browser when it sees them.</p>
                <button type="button" className="aa-button" onClick={askAgain}>Ask again</button>
              </div>
            )}
            {toolWait && (
              <div className="aa-approval" role="group" aria-label="A run asks for approval">
                <p className="aa-approval__title">A run asks to:</p>
                <ul>{calls.map((c, i) => <li key={i}>{describeToolCall(c).sentence}</li>)}</ul>
                <div className="aa-approval__actions">
                  <button type="button" className="aa-button" disabled={answering} onClick={() => void decide(false)}>Deny</button>
                  {widened && <button type="button" className="aa-button" disabled={answering} onClick={() => void decide(true, true)}>Approve all</button>}
                  <button type="button" className="aa-button aa-button--primary" disabled={answering} onClick={() => void decide(true)}>Approve</button>
                </div>
              </div>
            )}
          </div>
        }
        footer={error || waiting ? (
          <div className="aa-chat__notes">
            {waiting ? (
              <p className="aa-note" role="status">
                A run is waiting for you.{" "}
                <button type="button" className="aa-link" onClick={() => void answer(waiting)}>Answer</button>
              </p>
            ) : null}
            {error ? <p className="aa-note aa-note--error" role="alert">{error}</p> : null}
          </div>
        ) : null}
        messageProps={{ images: "link" }}
      />
    </div>
  );
}

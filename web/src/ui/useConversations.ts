/**
 * The conversation list, as the gateway knows it: one `GET runs?root_only=true` page folded
 * into sessions (lib/session_fold.ts), titles from each session's opening prompt
 * (lib/titles.ts), and the person's event stream (`me/events/stream`) so a run started or
 * finished anywhere (another device, an automation's discussion) refreshes it. The same
 * stream reports `attention.seen` (a wait answered elsewhere) to `onAttentionSeen`.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { sessionActivityFromRuns, sessionNeedsAttention, type SessionActivity } from "../vendor/abstractsessions/session_cards.js";
import type { GatewayClient } from "../gateway/client";
import { foldSessionRows, type SessionRow } from "../lib/session_fold";
import { eventTouchesList, loadTitles } from "../lib/titles";

const SESSION_PAGE_RUNS = 200; // core/gateway_sessions.py SESSION_PAGE_RUNS

/** A wait another device (or this one) answered or dismissed (`me/events` `attention.seen`). */
export type AttentionSeen = { run_id: string; wait_key: string; step_id?: string; outcome: string };

export type Conversations = {
  rows: SessionRow[];
  activity: Record<string, SessionActivity>;
  titles: Record<string, string>;
  truncated: boolean;
  /** Why the list could not be read ("" = it was). */
  error: string;
  /** One line about titles that could not be loaded. */
  notice: string;
  /** Why updates from other devices are off ("" = they are on). */
  eventsError: string;
  refresh: () => Promise<void>;
};

export function useConversations(
  client: GatewayClient,
  opts: { onSignedOut: () => void; scope?: string; onAttentionSeen?: (seen: AttentionSeen) => void; onSessionRead?: () => void },
): Conversations {
  const generation = useRef(0);
  const priorAttention = useRef(new Set<string>());
  const [activity, setActivity] = useState<Record<string, SessionActivity>>({});
  const [rows, setRows] = useState<SessionRow[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [titles, setTitles] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [eventsError, setEventsError] = useState("");
  const titleCache = useRef(new Map<string, string>());
  const visibleIds = useRef(new Set<string>());
  // Callbacks are read through refs: a new function on a parent render must not re-run the
  // list fetch or re-open the event stream.
  const signedOut = useRef(opts.onSignedOut);
  signedOut.current = opts.onSignedOut;
  const seen = useRef(opts.onAttentionSeen);
  seen.current = opts.onAttentionSeen;
  const sessionRead = useRef(opts.onSessionRead); sessionRead.current = opts.onSessionRead;

  const refresh = useCallback(async () => {
    try {
      const current = ++generation.current;
      const [listed, waiting] = await Promise.allSettled([client.listSessionRuns(SESSION_PAGE_RUNS), client.listWaitingRuns()]);
      if (current !== generation.current) return;
      if (listed.status === "rejected") throw listed.reason;
      const folded = foldSessionRows(listed.value);
      const facts = sessionActivityFromRuns(listed.value);
      const waitingRows = waiting.status === "fulfilled" && Array.isArray(waiting.value.items) ? waiting.value.items : [];
      const completeWaits = waiting.status === "fulfilled" && waiting.value.has_more === false;
      if (!completeWaits) for (const id of priorAttention.current) if (facts[id]) facts[id].needsAttention = true;
      for (const r of waitingRows) if (r && typeof r.session_id === "string" && sessionNeedsAttention(r) && facts[r.session_id]) facts[r.session_id].needsAttention = true;
      priorAttention.current = new Set(Object.keys(facts).filter((id) => facts[id].needsAttention));
      setActivity(facts);
      setRows(folded.rows);
      visibleIds.current = new Set(folded.rows.map((r) => r.session_id));
      setTruncated(folded.truncated);
      setError("");
      // Opening prompts name the rows: a few at a time, cached, failures retried next refresh.
      const load = await loadTitles(folded.rows, titleCache.current, (rid) => client.inputData(rid));
      if (current !== generation.current) return;
      const waitNotice = waiting.status === "rejected" ? "Pending questions and approvals could not be refreshed. " : !completeWaits ? "Pending questions and approvals are partially listed. " : "";
      setNotice(waitNotice + (load.failed ? `${load.failed} conversation title${load.failed === 1 ? "" : "s"} could not be loaded; they will be asked again.` : ""));
      setTitles(Object.fromEntries(titleCache.current));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      if ((err as { status?: number })?.status === 401) signedOut.current();
    }
  }, [client, opts.scope]);

  useEffect(() => {
    titleCache.current.clear(); priorAttention.current.clear(); setRows([]); setActivity({}); setTitles({});
    void refresh();
    return () => { generation.current++; };
  }, [refresh]);

  useEffect(() => {
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    (async () => {
      try {
        const page = await client.meEvents(0, 1);
        const head = typeof page.head === "number" ? page.head : 0;
        setEventsError("");
        await client.followMeEvents(head, (ev) => {
          const type = String(ev.type || "");
          if (type === "session.read") sessionRead.current?.();
          const data = (ev.data || {}) as Record<string, unknown>;
          if (type === "attention.raised" && typeof data.wait_key === "string" && typeof data.session_id === "string") priorAttention.current.add(data.session_id);
          if ((type === "attention.raised" || type === "attention.seen" || ((type === "run.started" || type === "run.finished") && eventTouchesList(data, visibleIds.current)))) {
            clearTimeout(timer);
            timer = setTimeout(() => void refresh(), 500);
          }
          if (type === "attention.seen" && typeof data.wait_key === "string" && typeof data.run_id === "string") {
            seen.current?.({
              run_id: data.run_id,
              wait_key: data.wait_key,
              ...(typeof data.step_id === "string" ? { step_id: data.step_id } : {}),
              outcome: String(data.outcome || "answered"),
            });
          }
        }, abort.signal);
      } catch (err) {
        if (!abort.signal.aborted) setEventsError(`Updates from your other devices are off: ${err instanceof Error ? err.message : String(err)}`);
      }
    })();
    return () => {
      abort.abort();
      clearTimeout(timer);
    };
  }, [client, refresh]);

  return { rows, activity, titles, truncated, error, notice, eventsError, refresh };
}

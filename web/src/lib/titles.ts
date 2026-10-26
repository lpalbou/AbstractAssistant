/**
 * Conversation titles: each one is the opening prompt of the session's first
 * run (`GET /runs/{first_run_id}/input_data`, as the desktop and abstractcode
 * read it). Fetched a few at a time (a browser page has six connections per
 * origin, two of them held by live streams), cached for the page's life,
 * and a failed fetch is NOT cached: it is retried on the next refresh and
 * reported once (adversary findings 16 and 23).
 */
import { promptFromInputData, type SessionRow } from "./session_fold";

export const TITLE_CONCURRENCY = 4;
export const TITLE_BATCH = 40; // core/gateway_sessions.py SESSION_PROMPT_MAX

/** Run `fn` over `items`, at most `limit` at a time; results in input order. */
export async function mapLimit<T, R>(items: T[], limit: number, fn: (item: T) => Promise<R>): Promise<R[]> {
  const out = new Array<R>(items.length);
  let next = 0;
  const worker = async () => {
    while (next < items.length) {
      const i = next++;
      out[i] = await fn(items[i]);
    }
  };
  await Promise.all(Array.from({ length: Math.max(1, Math.min(limit, items.length)) }, worker));
  return out;
}

export type TitleLoad = { fetched: number; failed: number };

/** Fill `cache` for the rows that lack a title (newest first, at most TITLE_BATCH). */
export async function loadTitles(
  rows: SessionRow[],
  cache: Map<string, string>,
  inputData: (runId: string) => Promise<unknown>,
): Promise<TitleLoad> {
  const missing = rows.filter((r) => !cache.has(r.session_id)).slice(0, TITLE_BATCH);
  let failed = 0;
  await mapLimit(missing, TITLE_CONCURRENCY, async (row) => {
    try {
      cache.set(row.session_id, promptFromInputData(await inputData(row.first_run_id)));
    } catch {
      failed += 1;
    }
  });
  return { fetched: missing.length - failed, failed };
}

/** Whether a `run.started` / `run.finished` event can change the visible list. */
export function eventTouchesList(data: Record<string, unknown>, visible: Set<string>): boolean {
  const sid = typeof data.session_id === "string" ? data.session_id : "";
  if (sid && visible.has(sid)) return true;
  // A NEW conversation (here or on another device) is a person's run; an
  // automation's occurrence is not listed here.
  const origin = data.origin && typeof data.origin === "object" ? (data.origin as Record<string, unknown>) : {};
  return origin.kind === "person";
}

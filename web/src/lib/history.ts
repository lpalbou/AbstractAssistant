/**
 * A conversation's past turns from the gateway history bundle
 * (`GET /runs/{latest_run_id}/history_bundle?include_session=true`): a PORT
 * of abstractassistant/gateway/history_seed.py `_seed_from_session_turns`
 * (one user line per turn prompt, with its attachment refs; one assistant
 * line per answer). The run store is the only source: nothing is cached in
 * the browser.
 */
import type { ChatAttachment, ChatMessage } from "./types";

type Json = Record<string, unknown>;
const isObj = (v: unknown): v is Json => Boolean(v) && typeof v === "object" && !Array.isArray(v);

function attachmentsOf(raw: unknown): ChatAttachment[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((a): a is Json => isObj(a) && typeof a.$artifact === "string" && Boolean(a.$artifact))
    .map((a) => ({
      $artifact: String(a.$artifact),
      ...(typeof a.filename === "string" ? { filename: a.filename } : {}),
      ...(typeof a.content_type === "string" ? { content_type: a.content_type } : {}),
      ...(typeof a.run_id === "string" ? { run_id: a.run_id } : {}),
    }));
}

export type HistorySeed = { messages: ChatMessage[]; warnings: string[] };

export function messagesFromHistoryBundle(bundle: unknown): HistorySeed {
  if (!isObj(bundle)) throw new Error("The conversation history was not a JSON object.");
  const warnings = (Array.isArray(bundle.warnings) ? bundle.warnings : [])
    .filter(isObj)
    .map((w) => `${String(w.code || "warning")}: ${String(w.detail || "")}`.trim());
  const session = bundle.session;
  const turns = isObj(session) && Array.isArray(session.turns) ? session.turns : null;
  if (!turns) {
    // The desktop falls back to the root prompt; a bundle with no session
    // turns at all is reported instead of guessed at.
    throw new Error("The gateway's history for this conversation has no session turns (history bundle without session.turns).");
  }
  const out: ChatMessage[] = [];
  for (const t of turns) {
    if (!isObj(t)) continue;
    const runId = typeof t.run_id === "string" ? t.run_id.trim() : "";
    const tsUser = String(t.created_at || t.updated_at || "");
    const tsAnswer = String(t.updated_at || t.created_at || "");
    const prompt = typeof t.prompt === "string" ? t.prompt : "";
    const answer = typeof t.answer === "string" ? t.answer : "";
    if (prompt.trim()) {
      const atts = attachmentsOf(t.attachments);
      out.push({ id: `${runId}:user`, role: "user", text: prompt, run_id: runId, ts: tsUser, ...(atts.length ? { attachments: atts } : {}) });
    }
    if (answer.trim()) out.push({ id: `${runId}:answer`, role: "assistant", text: answer, run_id: runId, ts: tsAnswer });
  }
  return { messages: out, warnings };
}

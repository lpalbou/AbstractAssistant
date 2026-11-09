/**
 * `@entity` mentions in the Assistant's chat (operator 2026-11-08). The gateway half is
 * AbstractGateway's mention door (`POST /api/gateway/sessions/{session_id}/mentions`,
 * gateway f32c8ca9; docs/entities.md "Mentioning an entity from any chat"):
 * `{entity, text, mention_index}` -> `{run_id (the session turn), author, reply, ...}`.
 *
 * - The names come from `GET /api/gateway/entities` (the entities this account may see). A
 *   mention is the kit's structured chip; the text is never read for `@` (no-heuristics ruling).
 * - Several mentions in one message are sent one after the other, in their order, each after
 *   the previous one returned, so the second entity sees the first one's answer (an entity named
 *   twice is asked once). Each names the
 *   person's own turn that carries the same words (`repeat_of`): the mention turn keeps the words
 *   as its prompt, and the conversation shows them once (lib/presentation.ts folds them).
 * - Refusals, per the contract: 409 = "<name> is in another conversation", go on with the next;
 *   404 `entity_not_found` = this name cannot be mentioned (hidden is missing), go on; 503 = the
 *   gateway's sentence, stop, the message goes back to the composer; 422 `repeat_of_unknown` =
 *   one sentence, stop; a gateway without the route (a plain 404/405, no code) = "This gateway
 *   does not offer mentions yet", stop.
 *
 * DOM-free; checked by mentions.test.ts.
 */
import { uniqueMentions, type ChatMentionCandidate, type ChatMentionSent, type ChatMessage } from "../vendor/abstractchat/conversation.js";

/** The one sentence an older gateway gets (no mention route, or turns without `author`). */
export const MENTIONS_UNAVAILABLE = "This gateway does not offer mentions yet.";

const text = (value: unknown): string => (typeof value === "string" ? value.trim() : "");
const record = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;

/**
 * The names the composer offers, from a `GET /entities` answer: one per listed entity, its
 * `slug` as the id the mention door resolves, its display `name`, and its look from the row's
 * identity record (`identity.avatar.{style, color}`, the record the door stamps on `author`).
 * A row the gateway marks as broken (`error`) is not offered.
 */
export function entityCandidates(payload: unknown): ChatMentionCandidate[] {
  const rows = record(payload)?.entities;
  if (!Array.isArray(rows)) return [];
  const out: ChatMentionCandidate[] = [];
  for (const raw of rows) {
    const row = record(raw);
    if (!row || row.error !== undefined) continue;
    const slug = text(row.slug);
    if (!slug) continue;
    const look = record(record(row.identity)?.avatar);
    const style = text(look?.style) || null;
    const color = text(look?.color) || null;
    out.push({ id: slug, name: text(row.name) || slug, kind: "entity", ...(style || color ? { avatar: { style, color } } : {}) });
  }
  return out;
}

/** The names that start with what was typed after `@` (name or id, any case). */
export function matchCandidates(list: readonly ChatMentionCandidate[], query: string): ChatMentionCandidate[] {
  const q = String(query || "").trim().toLowerCase();
  if (!q) return [...list];
  return list.filter((c) => c.name.toLowerCase().startsWith(q) || c.id.toLowerCase().startsWith(q));
}

/** The sentence under a chip the first time a name is picked in a conversation. */
export function mentionNotice(candidate: ChatMentionCandidate): string | null {
  return candidate.kind === "entity" ? `${candidate.name} will read this conversation's history.` : null;
}

/** What the mention door answered (200): the session turn the answer is (its view carries `author`). */
export type MentionAnswer = { run_id: string; reply: string; mention_index: number };

/** `repeat_of`: the person's own turn of this session that carries the same words. */
export type MentionRequest = { entity: string; text: string; mention_index: number; repeat_of?: string };

/** One `POST sessions/{id}/mentions` (the client binds the session). */
export type MentionPost = (request: MentionRequest, signal?: AbortSignal) => Promise<MentionAnswer>;

/** How a refused mention is handled (see the module doc). */
export type MentionRefusal = "route_missing" | "elsewhere" | "not_offered" | "cannot_answer" | "repeat_unknown" | "failed";

/** The refusal an error from the mention door stands for (`status` and `code` of a GatewayHttpError). */
export function mentionRefusal(error: unknown): MentionRefusal {
  const e = record(error);
  const status = typeof e?.status === "number" ? e.status : 0;
  const code = text(e?.code);
  // Every refusal of the door is coded; an uncoded 404/405 is a gateway without the route.
  if ((status === 404 || status === 405) && !code) return "route_missing";
  if (status === 409) return "elsewhere";
  if (status === 404) return "not_offered";
  if (status === 503) return "cannot_answer";
  if (status === 422 && code === "repeat_of_unknown") return "repeat_unknown";
  return "failed";
}

export type MentionDelivery = {
  /** The answers, in the order they were sent. */
  answered: MentionAnswer[];
  /** One sentence per mention that was skipped (another conversation, not offered). */
  notes: string[];
  /** The gateway has no mention route: nothing more was sent. */
  unavailable: boolean;
  /** Why the remaining mentions were not sent (an entity could not answer, or the call failed). */
  stopped: string | null;
  /** Not answered because of `stopped`: that mention and every one after it, with their index
   * (the chips the composer keeps; a resend asks only these, with the same `repeat_of`). */
  unsent: ChatMentionSent[];
};

/**
 * Send the message's mentions one after the other, in their order (`index` = the gateway's
 * `mention_index`), each after the previous one returned; `onAnswer` runs for each answer before
 * the next is sent. A Stop (`signal` aborted) rejects with the abort.
 */
export async function deliverMentions(opts: {
  text: string;
  mentions: readonly ChatMentionSent[];
  post: MentionPost;
  /** The person's own turn of this session that carries `text` (sent as `repeat_of`). */
  repeatOf?: string;
  signal?: AbortSignal;
  onAnswer?: (answer: MentionAnswer, mention: ChatMentionSent) => void | Promise<void>;
}): Promise<MentionDelivery> {
  const out: MentionDelivery = { answered: [], notes: [], unavailable: false, stopped: null, unsent: [] };
  const mentions = uniqueMentions(opts.mentions);
  for (const [at, mention] of mentions.entries()) {
    opts.signal?.throwIfAborted();
    let answer: MentionAnswer;
    try {
      answer = await opts.post({ entity: mention.id, text: opts.text, mention_index: mention.index, ...(opts.repeatOf ? { repeat_of: opts.repeatOf } : {}) }, opts.signal);
    } catch (error) {
      if (opts.signal?.aborted) throw error;
      const refusal = mentionRefusal(error);
      if (refusal === "route_missing") {
        out.unavailable = true;
        return out;
      }
      if (refusal === "elsewhere") {
        out.notes.push(`${mention.name} is in another conversation.`);
        continue;
      }
      if (refusal === "not_offered") {
        out.notes.push(`${mention.name} cannot be mentioned here.`);
        continue;
      }
      out.unsent = mentions.slice(at);
      if (refusal === "repeat_unknown") {
        out.stopped = `${mention.name} was not asked: the gateway did not find your message in this conversation.`;
        return out;
      }
      const e = record(error);
      const detail = text(e?.detail) || (error instanceof Error ? error.message : String(error));
      out.stopped = refusal === "cannot_answer" ? detail : `${mention.name} did not answer: ${detail}`;
      return out;
    }
    out.answered.push(answer);
    await opts.onAnswer?.(answer, mention);
  }
  return out;
}

/** The one line under the composer about the mentions just sent ("" = nothing to say). */
export function mentionStatusLine(outcome: MentionDelivery): string {
  return [...outcome.notes, outcome.unavailable ? MENTIONS_UNAVAILABLE : "", outcome.stopped || ""].filter(Boolean).join(" ");
}

/**
 * An older gateway shows its age in its turns: a newer one puts `author` (null included) on
 * every user and assistant message of a turn it serves. A shown user message without the key
 * means the gateway predates mentions.
 */
export function gatewayLacksTurnAuthors(messages: readonly ChatMessage[]): boolean {
  return messages.some((m) => m.role === "user" && !("author" in m));
}

/**
 * The turn a view's prompt repeats: the view's input message carries `repeat_of` (the person's
 * own turn whose words a mention answers again). Null when the view's prompt is its own.
 */
export function viewRepeatOf(view: unknown): { runId: string; repeatOf: string } | null {
  const v = record(view);
  const runId = text(v?.root_run_id);
  const messages = Array.isArray(v?.messages) ? v.messages : [];
  for (const raw of messages) {
    const m = record(raw);
    if (m?.role === "user" && text(m.run_id) === runId && text(m.repeat_of)) return runId ? { runId, repeatOf: text(m.repeat_of) } : null;
  }
  return null;
}

import { chatAuthorOf, type ChatAuthor, type ChatMessage } from "../vendor/abstractchat/conversation.js";
import type { AvatarPose } from "../vendor/abstractavatar/avatar_renderer.js";

export type PresentationOptions = {
  /** Turns whose prompt repeats another turn's words (`repeat_of`): turn run id -> the turn it
   * repeats. An `@` mention keeps the person's words as its prompt; they are shown once, in the
   * repeated turn, when that turn is on screen. */
  repeats?: ReadonlyMap<string, string>;
  /** Who writes each run's live reply, from the live reply frames (`author`): live text is named
   * like its finished answer will be. */
  liveAuthors?: ReadonlyMap<string, ChatAuthor | null>;
};

const when = (m: ChatMessage): number => (typeof m.ts === "string" ? Date.parse(m.ts) : Number.NaN);

/**
 * Transport diagnostics stay available in Details, outside the conversation. Errors stay visible.
 * Who answered is the gateway's turn `author` (the kit's header); without one (an older gateway)
 * the Assistant speaks as "Assistant" (the card's default is "Agent"), and so does an agent author
 * without a name. An entity's (or person's) answer is never titled "Assistant": without a name the
 * kit says its kind ("Entity"). The answers to one message
 * (its own turn's and those of the turns repeating it) are ordered by when they came.
 */
export function conversationPresentation(messages: readonly ChatMessage[], opts: PresentationOptions = {}) {
  const diagnostics: ChatMessage[] = [];
  const conversation: ChatMessage[] = [];
  const repeats = opts.repeats;
  const asked = new Set(messages.filter((m) => m.role === "user" && m.runId).map((m) => m.runId as string));
  const repeated = (runId: string | undefined) => {
    const of = runId ? repeats?.get(runId) : undefined;
    return of && asked.has(of) ? of : "";
  };
  for (const message of messages) {
    if (message.role === "system" && message.level === "info" && String(message.id || "").startsWith("stream-unavailable:")) {
      diagnostics.push(message);
      continue;
    }
    if (message.role === "user" && repeated(message.runId)) continue;
    let m = message;
    const live = m.role === "assistant" && m.live && m.author === undefined && m.runId ? opts.liveAuthors?.get(m.runId) : undefined;
    if (live) m = { ...m, author: live };
    const who = m.role === "assistant" ? chatAuthorOf(m.author) : null;
    conversation.push(m.role === "assistant" && !m.title && (!who || who.kind === "agent") ? { ...m, title: "Assistant" } : m);
  }
  // The answers to one message, in the order they came (each answer's own time).
  for (const anchor of new Set([...(repeats?.values() || [])].filter((of) => asked.has(of)))) {
    const slots = conversation
      .map((m, i) => (m.role === "assistant" && m.kind === "final" && (m.runId === anchor || repeated(m.runId) === anchor) ? i : -1))
      .filter((i) => i >= 0);
    if (slots.length < 2 || slots.some((i) => Number.isNaN(when(conversation[i])))) continue;
    const answers = slots.map((i) => conversation[i]).sort((a, b) => when(a) - when(b));
    slots.forEach((slot, k) => { conversation[slot] = answers[k]; });
  }
  return { conversation, diagnostics };
}

export function assistantPresence(state: {
  recording: boolean;
  transcribing: boolean;
  playback: string;
  pending: boolean;
  busy: boolean;
  working: boolean;
  failed: boolean;
  loading: boolean;
}): { pose: AvatarPose; label: string; hint: string } {
  if (state.recording) return { pose: "listening", label: "Listening", hint: "Your words will appear here before you send." };
  if (state.transcribing) return { pose: "thinking", label: "Writing down what you said", hint: "One moment…" };
  if (state.pending) return { pose: "waiting", label: "Needs you", hint: "There’s a request to review in the conversation." };
  if (state.loading) return { pose: "thinking", label: "Opening your conversation", hint: "Reading the history from your Gateway." };
  if (state.busy) return state.working
    ? { pose: "working", label: "Working", hint: "Taking care of your request." }
    : { pose: "thinking", label: "Thinking", hint: "Making sense of your question." };
  if (state.playback === "playing") return { pose: "speaking", label: "Speaking", hint: "Tap to pause. Your answer is below." };
  if (state.playback === "paused") return { pose: "waiting", label: "Paused", hint: "Tap to keep listening." };
  if (state.playback === "loading") return { pose: "thinking", label: "Getting ready to speak", hint: "Preparing your answer’s audio." };
  if (state.failed) return { pose: "error", label: "Something went wrong", hint: "The conversation explains what happened." };
  return { pose: "ready", label: "Ready when you are", hint: "Talk to me, or write a message below." };
}

/** A fresh answer can be read automatically; opening history never counts as a new answer. */
export function replyToRead(messages: readonly ChatMessage[], runId: string): ChatMessage | undefined {
  return [...messages].reverse().find((m) => m.role === "assistant" && m.runId === runId && !m.live && !m.toolActivity && m.content.trim());
}

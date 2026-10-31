import type { ChatMessage } from "@abstractframework/panel-chat";
import type { AvatarPose } from "@abstractframework/ui-kit";

/** Transport diagnostics stay available in Details, outside the conversation. Errors stay visible. */
export function conversationPresentation(messages: readonly ChatMessage[]) {
  const diagnostics: ChatMessage[] = [];
  const conversation: ChatMessage[] = [];
  for (const message of messages) {
    if (message.role === "system" && message.level === "info" && String(message.id || "").startsWith("stream-unavailable:")) {
      diagnostics.push(message);
    } else {
      conversation.push(message.role === "assistant" && !message.title ? { ...message, title: "Assistant" } : message);
    }
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

/** One line of a conversation, as the web Assistant renders it. */
export type ChatAttachment = { $artifact: string; filename?: string; content_type?: string; run_id?: string };

export type ChatMessage = {
  /** Stable key: `<run_id>:user`, `<run_id>:answer`, `<run_id>:note:<n>`, `local:<n>`. */
  id: string;
  role: "user" | "assistant" | "notice";
  text: string;
  run_id: string;
  ts: string;
  attachments?: ChatAttachment[];
  /** Still being written (live deltas), replaced by the durable answer. */
  live?: boolean;
};

/** A run parked on the person: approve tools, or answer a question. */
export type PendingWait = {
  kind: "tool_approval" | "ask_user";
  run_id: string;
  wait_key: string;
  step_id: string;
  prompt: string;
  tool_calls: Array<{ name: string; arguments: unknown; call_id?: string }>;
  /** Set while the answer is being sent, or once the gateway says it was answered elsewhere. */
  state: "open" | "sending" | "answered" | "stale";
  note?: string;
};

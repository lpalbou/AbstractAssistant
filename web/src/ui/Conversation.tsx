import { Markdown } from "@abstractframework/panel-chat";
import { useState } from "react";

import type { TurnState } from "../lib/run_events";
import type { ChatMessage, PendingWait } from "../lib/types";

function argsText(args: unknown): string {
  if (args === undefined || args === null || args === "") return "";
  if (typeof args === "string") return args;
  try {
    return JSON.stringify(args, null, 2);
  } catch {
    return String(args);
  }
}

/** A tool approval or a question, in the conversation (not a modal). */
function WaitCard(props: { wait: PendingWait; frozen: boolean; onAnswer: (w: PendingWait, a: { approved: boolean } | { response: string }) => void }) {
  const { wait } = props;
  const [reply, setReply] = useState("");
  const closed = wait.state === "answered" || wait.state === "stale";
  // Once live updates are lost the card may be out of date: no answer from it.
  const sending = wait.state === "sending" || props.frozen;
  return (
    <section className={`aa-wait aa-wait--${wait.kind}`} aria-label={wait.kind === "tool_approval" ? "Approval needed" : "A question for you"}>
      <h2 className="aa-wait__title">{wait.kind === "tool_approval" ? "The Assistant wants to use a tool" : wait.prompt}</h2>
      {wait.kind === "tool_approval"
        ? wait.tool_calls.map((tc, i) => (
            <div key={`${tc.call_id || i}`} className="aa-wait__tool">
              <span className="aa-wait__tool-name">{tc.name}</span>
              {argsText(tc.arguments) ? <pre className="aa-wait__args">{argsText(tc.arguments)}</pre> : null}
            </div>
          ))
        : null}
      {wait.note ? <p className="aa-wait__note">{wait.note}</p> : null}
      {props.frozen && !closed ? <p className="aa-wait__note">Live updates stopped: reopen the conversation to answer.</p> : null}
      {closed ? null : wait.kind === "tool_approval" ? (
        <div className="aa-wait__actions">
          <button type="button" className="aa-button aa-button--primary" disabled={sending} onClick={() => props.onAnswer(wait, { approved: true })}>
            Approve
          </button>
          <button type="button" className="aa-button" disabled={sending} onClick={() => props.onAnswer(wait, { approved: false })}>
            Deny
          </button>
        </div>
      ) : (
        <form
          className="aa-wait__actions"
          onSubmit={(e) => {
            e.preventDefault();
            if (reply.trim()) props.onAnswer(wait, { response: reply.trim() });
          }}
        >
          <input className="aa-input" value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Your answer" aria-label="Your answer" disabled={sending} />
          <button type="submit" className="aa-button aa-button--primary" disabled={sending || !reply.trim()}>
            Answer
          </button>
        </form>
      )}
    </section>
  );
}

function Bubble(props: { m: ChatMessage; speaking: boolean; canSpeak: boolean; onReadAloud: (m: ChatMessage) => void }) {
  const { m } = props;
  return (
    <article className={`aa-msg aa-msg--${m.role}${m.live ? " aa-msg--live" : ""}`}>
      {m.role === "assistant" ? (
        // "link": a model's text cannot make the browser fetch a remote image.
        <Markdown text={m.text} images="link" />
      ) : (
        <p className="aa-msg__text">{m.text}</p>
      )}
      {m.attachments?.length ? (
        <ul className="aa-msg__files">
          {m.attachments.map((a) => (
            <li key={a.$artifact}>{a.filename || a.$artifact}</li>
          ))}
        </ul>
      ) : null}
      {m.role === "assistant" && !m.live && props.canSpeak ? (
        <button type="button" className="aa-link" onClick={() => props.onReadAloud(m)} aria-pressed={props.speaking}>
          {props.speaking ? "Stop reading" : "Read aloud"}
        </button>
      ) : null}
    </article>
  );
}

export function Conversation(props: {
  messages: ChatMessage[];
  turn: TurnState;
  liveText: string;
  speakingId: string;
  canSpeak: boolean;
  onReadAloud: (m: ChatMessage) => void;
  onAnswer: (w: PendingWait, a: { approved: boolean } | { response: string }) => void;
}) {
  const t = props.turn;
  const active = Boolean(t.root_run_id) && !["completed", "failed", "cancelled"].includes(t.status);
  return (
    <div className="aa-thread" aria-live="polite">
      {props.messages.length === 0 && !active ? <p className="aa-empty">Ask anything. Your conversations are kept on your gateway and follow you on every device.</p> : null}
      {props.messages.map((m) => (
        <Bubble key={m.id} m={m} speaking={props.speakingId === m.id} canSpeak={props.canSpeak} onReadAloud={props.onReadAloud} />
      ))}
      {active ? (
        <>
          {t.notes.map((n, i) => (
            <Bubble key={`note:${i}`} m={{ id: `note:${i}`, role: "assistant", text: n, run_id: t.root_run_id, ts: "", live: true }} speaking={false} canSpeak={false} onReadAloud={props.onReadAloud} />
          ))}
          {props.liveText ? (
            <Bubble m={{ id: "live", role: "assistant", text: props.liveText, run_id: t.root_run_id, ts: "", live: true }} speaking={false} canSpeak={false} onReadAloud={props.onReadAloud} />
          ) : null}
          {t.waits.map((w) => (
            <WaitCard key={`${w.run_id}|${w.wait_key}|${w.step_id}`} wait={w} frozen={t.follow === "lost"} onAnswer={props.onAnswer} />
          ))}
          <p className="aa-activity" role="status">
            {t.activity || (t.status === "starting" ? "Starting…" : "Working…")}
          </p>
        </>
      ) : null}
    </div>
  );
}

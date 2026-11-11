// Operator round 6 (2026-11-11), Assistant: an entity's answer on its way is a bubble in the thread
// (its orb and name, three dots), replaced by the answer, never a line above the field; the person's
// words show once before the answers (each mention turn repeats them: `repeat_of`).
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { WorkingDots } from "@abstractframework/panel-chat";
import { WorkflowChat, type ChatMessage } from "../vendor/abstractchat/conversation.js";
import { pendingMentionsFor, PENDING_MENTION_ID, withPendingMentions } from "../lib/mentions";
import { conversationPresentation } from "../lib/presentation";

const LOOK = { style: "watch-halo", color: "#336699" };
const castor = { id: "castor", name: "Castor", kind: "entity" as const, index: 0, start: 4 };
const pollux = { id: "pollux", name: "Pollux", kind: "entity" as const, index: 1, start: 12 };
const ws = readFileSync(new URL("./Workspace.tsx", import.meta.url), "utf8");
const entity = (name: string) => ({ kind: "entity" as const, name, entity_id: null, identity_ref: null, avatar: null });

describe("the person's words show once before both answers", () => {
  it("two mirrors of a turn not on screen: one user bubble, then both answers", () => {
    const shown = conversationPresentation([
      { id: "m:input", runId: "m", role: "user", kind: "prompt", content: "hey @Castor @Pollux" },
      { id: "m:final", runId: "m", role: "assistant", kind: "final", content: "Castor here.", author: entity("Castor") },
      { id: "n:input", runId: "n", role: "user", kind: "prompt", content: "hey @Castor @Pollux" },
      { id: "n:final", runId: "n", role: "assistant", kind: "final", content: "Pollux here.", author: entity("Pollux") },
    ], { repeats: new Map([["m", "p"], ["n", "p"]]) }).conversation;
    expect(shown.map((m) => `${m.role}:${m.id}`)).toEqual(["user:m:input", "assistant:m:final", "assistant:n:final"]);
  });
});

describe("an answer on its way is a bubble with its dots", () => {
  const pending = pendingMentionsFor("msg-1", [castor, pollux, castor], (m) => (m.id === "castor" ? LOOK : null));

  it("one per entity, named as its answer will be; replaced, not duplicated, once its answer shows", () => {
    expect(pending.map((p) => [p.author.name, p.author.avatar])).toEqual([["Castor", LOOK], ["Pollux", null]]);
    expect(withPendingMentions([], pending).map((m) => [m.author?.name, m.live?.label, m.id])).toEqual([
      ["Castor", "answering", `${PENDING_MENTION_ID}msg-1:0`],
      ["Pollux", "answering", `${PENDING_MENTION_ID}msg-1:1`],
    ]);
    const answer: ChatMessage = { id: "m:final", runId: "m", role: "assistant", kind: "final", content: "Castor here.", author: entity("Castor") };
    expect(withPendingMentions([answer], [{ ...pending[0], runId: "m" }, pending[1]]).map((m) => m.id)).toEqual(["m:final", `${PENDING_MENTION_ID}msg-1:1`]);
  });

  it("the thread draws its author and its three dots", () => {
    const html = renderToStaticMarkup(
      <WorkflowChat messages={withPendingMentions([], pending.slice(0, 1))} draft="" onDraftChange={() => {}} onSend={async () => {}}
        messageProps={{ renderFooter: (m) => (String(m.id || "").startsWith(PENDING_MENTION_ID) ? <WorkingDots label={`${m.author?.name} is answering`} /> : null) }} />,
    );
    expect(html).toContain("Castor");
    expect(html).toContain("pc-working-dots");
  });

  it("the workspace: bubbles from the ask, marked as each answer shows, gone when delivery ends; dots in the footer", () => {
    expect(ws).toContain("setPendingAnswers({ anchor, entries: pendingMentionsFor(");
    expect(ws).toContain("forThis((entries) => entries.map((e) => (e.mention.id === mention.id && e.mention.index === mention.index ? { ...e, runId: answer.run_id } : e)));");
    expect(ws).toContain(".finally(() => setPendingAnswers((now) => (now && now.anchor === anchor ? null : now)));");
    expect(ws).toContain("messages={withPendingMentions(messages, pendingAnswers && pendingAnswers.anchor === props.runId ? pendingAnswers.entries : [])}");
    expect(ws).toContain('if (String(m.id || "").startsWith(PENDING_MENTION_ID)) return <WorkingDots');
    expect(ws).not.toMatch(/is answering…/);
  });
});

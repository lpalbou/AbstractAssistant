// Mentions in the conversation (panel-chat 0.9.13, operator 2026-11-10): a message this page sent
// shows the chips its send carried, placed by `start` (the words are never read for "@"), with the
// `@` list's looks; resting on a chip shows a small card (orb, name, state sentence) from the
// `GET /entities` rows the `@` list loaded. A reloaded turn carries no mentions: no chip.
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { WorkflowChat, type ChatMessage } from "../vendor/abstractchat/conversation.js";
import { entityMentionCards, entityStateSentence, sentMessageMentions, withSentMentions } from "../lib/mentions";
import { mentionCard } from "./MentionCard";

const LOOK = { style: "watch-halo", color: "#336699" };
const LISTED = {
  entities: [
    { slug: "castor", name: "Castor", identity: { avatar: LOOK }, state: { state: "awake", mode: "visiting" } },
    { slug: "pollux", name: "Pollux", state: { state: "asleep" } },
    { slug: "ghost", error: "unreadable" },
  ],
};
const ws = readFileSync(new URL("./Workspace.tsx", import.meta.url), "utf8");

describe("a sent message carries its chips", () => {
  it("each chip as sent (its start on the words as typed), the look from the @ list; the assistant's chip too", () => {
    const cards = entityMentionCards(LISTED);
    const sent = [
      { id: "castor", name: "Castor", kind: "entity" as const, index: 0, start: 3 },
      { id: "agent", name: "Assistant", kind: "agent" as const, index: 1, start: 15 },
    ];
    const shown = sentMessageMentions(sent, (m) => (m.kind === "entity" ? cards.get(m.id)?.avatar : null));
    expect(shown).toEqual([
      { id: "castor", name: "Castor", kind: "entity", index: 0, start: 3, avatar: LOOK },
      { id: "agent", name: "Assistant", kind: "agent", index: 1, start: 15 },
    ]);
  });

  it("the run's prompt gets them (by run, not by words); other messages, a reload: untouched", () => {
    const mentions = [{ id: "castor", name: "Castor", kind: "entity" as const, index: 0, start: 3 }];
    const view: ChatMessage[] = [
      { id: "p1", role: "user", kind: "prompt", runId: "r1", content: "hi @Castor" },
      { id: "a1", role: "assistant", kind: "answer", runId: "r1", content: "@Castor said hi" },
      { id: "p2", role: "user", kind: "prompt", runId: "r2", content: "hi @Castor" },
    ];
    expect(withSentMentions(view, new Map([["r1", mentions]])).map((m) => m.mentions ?? null)).toEqual([mentions, null, null]);
    expect(withSentMentions(view, new Map())).toBe(view);
  });

  it("the workspace sets them on the kept words and by run on a started turn, and shows them", () => {
    expect(ws).toContain('const shown = sentMessageMentions(mentions, (m) => (m.kind === "entity" ? entityCards.current?.get(m.id)?.avatar : null));');
    expect(ws).toContain("content: text, ...mentionsField };");
    expect(ws).toContain("if (shown.length) sentMentions.current.set(run_id, shown);");
    expect(ws.match(/withSentMentions\(snapshot\.messages, sentMentions\.current\)/g)?.length).toBe(2);
  });

  it("the bubble draws the kit's chip; without mentions, none", () => {
    const mentions = [{ id: "castor", name: "Castor", kind: "entity" as const, index: 0, start: 3, avatar: LOOK }];
    const chat = (messages: ChatMessage[]) =>
      renderToStaticMarkup(<WorkflowChat messages={messages} draft="" onDraftChange={() => {}} onSend={async () => {}} messageProps={{ renderMentionCard: () => null }} />);
    expect(chat([{ id: "m1", role: "user", content: "hi @Castor", mentions }])).toContain("pc-mention-chip--message");
    const plain = chat([{ id: "m1", role: "user", content: "hi @Castor" }]);
    expect(plain).not.toContain("pc-mention-chip");
    expect(plain).toContain("@Castor");
  });
});

describe("the card on a chip", () => {
  it("an entity the loaded rows hold: orb, name, state sentence; the assistant or a stranger: no card", () => {
    expect(entityStateSentence("Pollux", { state: "asleep" })).toBe("Pollux is asleep.");
    expect(entityStateSentence("Vega", null)).toBe("");
    const cards = entityMentionCards(LISTED);
    expect([...cards.keys()]).toEqual(["castor", "pollux"]);
    const out = renderToStaticMarkup(<>{mentionCard({ id: "castor", name: "Castor", kind: "entity", index: 0, start: 0 }, cards)}</>);
    expect(out).toContain('class="aa-mention-card"');
    expect(out).toContain("Castor is in a conversation.");
    expect(out).toContain("pc-author-mark");
    expect(mentionCard({ id: "agent", name: "Assistant", kind: "agent", index: 0, start: 0 }, cards)).toBeNull();
    expect(mentionCard({ id: "nobody", name: "Nobody", kind: "entity", index: 0, start: 0 }, cards)).toBeNull();
    expect(mentionCard({ id: "castor", name: "Castor", kind: "entity", index: 0, start: 0 }, null)).toBeNull();
    expect(ws).toContain("renderMentionCard: (mention) => mentionCard(mention, entityCards.current),");
  });
});

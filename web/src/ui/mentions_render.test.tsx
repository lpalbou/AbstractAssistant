// The conversation as this app renders it (the vendored kit's WorkflowChat, fed by this app's
// presentation and mention outcome): every left bubble says who answered, from the gateway's turn
// `author`; no author (an older gateway) is today's header; an older gateway's mention attempt
// leaves one visible sentence.
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { WorkflowChat, type ChatMessage } from "../vendor/abstractchat/conversation.js";
import { conversationPresentation } from "../lib/presentation";
import { MENTIONS_UNAVAILABLE, deliverMentions, mentionNotice, mentionStatusLine } from "../lib/mentions";
import { GatewayHttpError } from "../gateway/client";

const castor = { kind: "entity" as const, name: "Castor", entity_id: "entity:castor", identity_ref: "entity:castor#3", avatar: { style: "watch-halo", color: "#336699" } };
const agent = { kind: "agent" as const, name: "Basic agent", entity_id: null, identity_ref: null, avatar: null };
const person = { kind: "person" as const, name: "Laurent", entity_id: null, identity_ref: null, avatar: null };

function render(messages: ChatMessage[], extra: Partial<React.ComponentProps<typeof WorkflowChat>> = {}): string {
  return renderToStaticMarkup(
    <WorkflowChat messages={messages} draft="" onDraftChange={() => {}} onSend={async () => {}} mentionCandidates={async () => []} mentionNotice={mentionNotice} mentionSessionKey="s" {...extra} />,
  );
}

/** The markup of each card of one variant (`pc-chat-item--assistant`), from its opening tag to the next card. */
function cards(html: string, variant: string): Array<{ open: string; body: string }> {
  const starts = [...html.matchAll(new RegExp(`<div[^>]*class="pc-chat-item [^"]*${variant}[^"]*"[^>]*>`, "g"))];
  return starts.map((m, i) => ({ open: m[0], body: html.slice(m.index!, i + 1 < starts.length ? starts[i + 1].index! : html.length) }));
}

/** Each assistant bubble's header: [data-author, the name shown, the kind tag]. */
function headers(html: string): Array<[string | null, string, string | null]> {
  return cards(html, "pc-chat-item--assistant").map((item) => [
    /data-author="([^"]+)"/.exec(item.open)?.[1] ?? null,
    /<span class="pc-chat-role">([^<]*)<\/span>/.exec(item.body)?.[1] ?? "",
    /pc-chat-author-kind[^>]*>(?:<[^>]*>)*([^<]+)</.exec(item.body)?.[1] ?? null,
  ]);
}

describe("who answered, on every left bubble", () => {
  const turn: ChatMessage[] = [
    { id: "r:input", runId: "r", role: "user", kind: "prompt", content: "Which plan holds?", author: person },
    { id: "r:final", runId: "r", role: "assistant", kind: "final", content: "The second plan.", author: agent },
    { id: "m:input", runId: "m", role: "user", kind: "prompt", content: "Which plan holds?", author: person },
    { id: "m:final", runId: "m", role: "assistant", kind: "final", content: "The bridge holds.", author: castor },
  ];

  it("names the entity (its orb, tag 'entity') and the agent (tag 'agent'); the mention's prompt shows once", () => {
    const html = render(conversationPresentation(turn, { repeats: new Map([["m", "r"]]) }).conversation);
    expect(headers(html)).toEqual([["agent", "Basic agent", "agent"], ["entity", "Castor", "entity"]]);
    expect(html.match(/pc-chat-item--user/g)?.length).toBe(1);
    expect(html).toContain('data-design="watch-halo"');
  });

  it("an older gateway (no author) keeps today's header: 'Assistant', no mark, no tag", () => {
    const html = render(conversationPresentation([
      { id: "r:input", runId: "r", role: "user", content: "Hi" },
      { id: "r:final", runId: "r", role: "assistant", content: "Hello." },
    ]).conversation);
    expect(headers(html)).toEqual([[null, "Assistant", null]]);
  });

  it("a reply still being written carries its run's name", () => {
    const html = render(conversationPresentation([
      { id: "live:r:c", runId: "r", role: "assistant", content: "Writing", live: { callId: "c", reasoning: "" } },
    ], { liveAuthors: new Map([["r", agent]]) }).conversation);
    expect(headers(html)).toEqual([["agent", "Basic agent", "agent"]]);
  });
});

describe("an older gateway's mention attempt", () => {
  it("leaves one visible sentence under the composer", async () => {
    const outcome = await deliverMentions({
      text: "hi",
      mentions: [{ id: "castor", name: "Castor", kind: "entity", index: 0 }],
      post: vi.fn(async () => { throw new GatewayHttpError("Mention of castor: Not Found", 404, "", { detail: "Not Found" }); }),
    });
    const html = render([], { mentionStatus: mentionStatusLine(outcome), mentionsUnavailable: MENTIONS_UNAVAILABLE });
    expect(html.split(MENTIONS_UNAVAILABLE).length - 1).toBe(1);
    expect(html).toContain('role="status"');
  });

  it("says nothing when no mention was sent", () => {
    expect(render([], { mentionStatus: null, mentionsUnavailable: MENTIONS_UNAVAILABLE })).not.toContain(MENTIONS_UNAVAILABLE);
  });
});

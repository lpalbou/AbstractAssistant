// The conversation as this app renders it (the vendored kit's WorkflowChat, fed by this app's
// presentation and mention outcome): every left bubble says who answered, from the gateway's turn
// `author`; no author (an older gateway) is today's header; an older gateway's mention attempt
// leaves one visible sentence; what an entity's reply kept shows as badges under its words (the
// npm kit's projectReplayView carries the view's `notices`, the vendored card renders them).
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { projectReplayView } from "@abstractframework/panel-chat";
import { WorkflowChat, type ChatMessage } from "../vendor/abstractchat/conversation.js";
import { conversationPresentation } from "../lib/presentation";
import { MENTIONS_UNAVAILABLE, deliverMentions, mentionStatusLine, viewAgentNotAddressed } from "../lib/mentions";
import { GatewayHttpError } from "../gateway/client";

const castor = { kind: "entity" as const, name: "Castor", entity_id: "entity:castor", identity_ref: "entity:castor#3", avatar: { style: "watch-halo", color: "#336699" } };
const agent = { kind: "agent" as const, name: "Basic agent", entity_id: null, identity_ref: null, avatar: null };
const person = { kind: "person" as const, name: "Laurent", entity_id: null, identity_ref: null, avatar: null };

function render(messages: ChatMessage[], extra: Partial<React.ComponentProps<typeof WorkflowChat>> = {}): string {
  return renderToStaticMarkup(
    <WorkflowChat messages={messages} draft="" onDraftChange={() => {}} onSend={async () => {}} mentionCandidates={async () => []} mentionSessionKey="s" {...extra} />,
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

describe("a message the agent was not addressed in (operator 2026-11-10)", () => {
  const answered = { message: "m", answered: [{ run_id: "m1", reply: "The bridge holds.", mention_index: 0 }], notes: [], unavailable: false, stopped: null, unsent: [] };

  it("no line above the field says the assistant stays out (operator 2026-11-10 23:02: \"remove that\")", () => {
    const html = render([], { mentionStatus: mentionStatusLine(answered) || null });
    expect(html).not.toContain("stays out of this message");
    expect(html).not.toContain("pc-mention-notice");
  });

  it("a refusal still shows, alone, in the kit's mention status", () => {
    const html = render([], { mentionStatus: mentionStatusLine({ ...answered, notes: ["Pollux is in another conversation."] }) });
    expect(html.match(/pc-mention-notice--status/g)?.length).toBe(1);
    expect(html).toContain("Pollux is in another conversation.");
  });

  it("the kept turn's words show once, then the entity's answer; no reply of the agent, no working dots", () => {
    // The words the workspace shows for the kept turn (`turn_id`), then the mention turn's view (repeat_of it).
    const turn: ChatMessage[] = [
      { id: "kept:turn-7", role: "user", kind: "prompt", content: "Does the bridge hold?" },
      { id: "m:input", runId: "m", role: "user", kind: "prompt", content: "Does the bridge hold?", author: person },
      { id: "m:final", runId: "m", role: "assistant", kind: "final", content: "The bridge holds.", author: castor },
      { id: "n:input", runId: "n", role: "user", kind: "prompt", content: "Does the bridge hold?", author: person },
      { id: "n:final", runId: "n", role: "assistant", kind: "final", content: "It holds for now.", author: { ...castor, name: "Pollux" } },
    ];
    const opts = { repeats: new Map([["m", "turn-7"], ["n", "turn-7"]]), kept: new Map([["kept:turn-7", "turn-7"]]) };
    const shown = conversationPresentation(turn, opts).conversation;
    // The words carry no run (the kit reads a run's input for each user message that has one).
    expect(shown.filter((m) => m.role === "user").map((m) => [m.id, m.runId])).toEqual([["kept:turn-7", undefined]]);
    // Without the kept turn, the first mention's prompt keeps the words and the others fold (operator
    // round 6: never once per mention); the kept words are then a second copy.
    expect(conversationPresentation(turn, { repeats: opts.repeats }).conversation.filter((m) => m.role === "user").map((m) => m.id)).toEqual(["kept:turn-7", "m:input"]);
    const html = render(shown, { busy: false });
    expect(headers(html)).toEqual([["entity", "Castor", "entity"], ["entity", "Pollux", "entity"]]);
    expect(html.match(/pc-chat-item--user/g)?.length).toBe(1);
    expect(html).not.toContain("pc-chat-working");
  });

  it("after a reload the kept turn reads no run's input (its id is a turn's) and shows as it did live", () => {
    // The gateway's view, read back: the kept turn's words (`agent_addressed: false`, its TURN id as
    // run_id), then the entity's turn repeating them.
    const view = {
      version: "replay_view_v1", root_run_id: "m", status: "completed", cursor: { token: "t", records: 3, runs: { m: 2 } }, runs: [], interaction: null,
      messages: [
        { id: "turn-7:p", role: "user", kind: "prompt", text: "Does the bridge hold?", run_id: "turn-7", order: ["2026-11-10T08:00:00Z", 1], agent_addressed: false },
        { id: "m:p", role: "user", kind: "prompt", text: "Does the bridge hold?", run_id: "m", order: ["2026-11-10T08:00:01Z", 2] },
        { id: "m:s2:answer_user", role: "assistant", kind: "answer", text: "The bridge holds.", run_id: "m", order: ["2026-11-10T08:00:05Z", 3], author: castor },
      ],
      activities: [], artifacts: [],
    };
    const repeats = new Map([["m", "turn-7"]]);
    const reloaded = conversationPresentation(projectReplayView(view as Parameters<typeof projectReplayView>[0]).messages as ChatMessage[],
      { repeats, notAddressed: new Set(viewAgentNotAddressed(view)) }).conversation;
    // The kit reads `GET runs/{id}/input_data` for each user message with a `runId` (its
    // attachments): none here, so no request for the turn (the gateway answers 404, it is no run).
    expect(reloaded.filter((m) => m.role === "user" && m.runId)).toEqual([]);
    expect(reloaded.filter((m) => m.role === "user").map((m) => [m.id, m.content])).toEqual([["turn-7:p", "Does the bridge hold?"]]);
    // As live (the words the workspace showed for the kept turn, then the entity's answer); the turn row adds its time.
    const live = conversationPresentation([
      { id: "kept:turn-7", role: "user", kind: "prompt", content: "Does the bridge hold?", ts: "2026-11-10T08:00:00Z" },
      ...(projectReplayView(view as Parameters<typeof projectReplayView>[0]).messages as ChatMessage[]).slice(1),
    ], { repeats, kept: new Map([["kept:turn-7", "turn-7"]]) }).conversation;
    expect(render(reloaded, { busy: false })).toBe(render(live, { busy: false }));
  });
});

describe("what an entity's reply kept, as badges under its words", () => {
  // An entity's answer as the gateway's replay view serves it (AbstractRuntime turn notices).
  const diary = { kind: "diary", record_id: "ex:diary-1", title: "the first durable visit" };
  const lesson = { kind: "lesson", record_id: null, title: "Visits are durable", staged: true };
  const secret = { kind: "diary", record_id: "ex:diary-2", title: "", visibility: "private" };
  const view = (notices: unknown) => ({
    version: "replay_view_v1", root_run_id: "m", status: "completed", cursor: { token: "t", records: 2, runs: { m: 2 } }, runs: [], interaction: null,
    messages: [
      { id: "m:p", role: "user", kind: "prompt", text: "Which plan holds?", run_id: "m", order: ["2026-11-10T08:00:00Z", 1] },
      { id: "m:s2:answer_user", role: "assistant", kind: "answer", text: "The bridge holds.", run_id: "m", order: ["2026-11-10T08:00:05Z", 2], author: castor, notices },
    ],
    activities: [], artifacts: [],
  });
  const shown = (notices: unknown) =>
    render(conversationPresentation(projectReplayView(view(notices) as Parameters<typeof projectReplayView>[0]).messages as ChatMessage[]).conversation);

  it("one badge per notice, under the entity's reply: its title, a private entry without words, a forming one", () => {
    const html = shown([diary, lesson, secret]);
    const [answer] = cards(html, "pc-chat-item--assistant");
    expect(answer.body.match(/class="pc-chat-notice /g)?.length).toBe(3);
    expect(answer.body).toContain("the first durable visit");
    expect(answer.body).toContain("Visits are durable");
    expect(answer.body).toContain("forming…");
    expect(answer.body).toContain("private diary entry");
    expect(answer.body).toContain("The bridge holds.");
  });

  it("a reply that kept nothing (no notices, or the operator's log lines) shows no badge row", () => {
    for (const notices of [undefined, null, [], ["#FALLBACK kept nothing"]]) {
      const html = shown(notices);
      expect(html).toContain("The bridge holds.");
      expect(html).not.toContain("pc-chat-notice");
    }
  });
});

// `@entity` mentions (lib/mentions.ts): the names offered, the order mentions are sent in, and how
// each refusal of the gateway's mention door is handled (contract: abstractgateway
// docs/entities.md "Mentioning an entity from any chat").
import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";

import type { AssistantHost } from "../host";
import { GatewayClient, GatewayHttpError } from "../gateway/client";
import {
  MENTIONS_UNAVAILABLE,
  deliverMentions,
  entityCandidates,
  gatewayLacksTurnAuthors,
  matchCandidates,
  mentionId,
  mentionMessageKey,
  mentionNotice,
  mentionRefusal,
  mintMessageId,
  mentionStatusLine,
  mentionTurn,
  startRunMentions,
  viewRepeatOf,
  type MentionAnswer,
  type MentionRequest,
} from "./mentions";
import { mentionResend } from "../vendor/abstractchat/conversation.js";

const castor = { id: "castor", name: "Castor", kind: "entity" as const, index: 0 };
const pollux = { id: "pollux", name: "Pollux", kind: "entity" as const, index: 1 };
const vega = { id: "vega", name: "Vega", kind: "entity" as const, index: 2 };
const answer = (req: MentionRequest): MentionAnswer => ({ run_id: `turn-${req.entity}`, reply: `${req.entity} here`, mention_index: req.mention_index });
const refused = (status: number, detail: string, code = "") => new GatewayHttpError(`Mention: ${detail}`, status, "", { code, detail });

describe("the names the composer offers", () => {
  const listed = {
    entities: [
      { slug: "castor", name: "Castor", identity: { avatar: { style: "watch-halo", color: "#336699", watch_code: 3 } } },
      { slug: "pollux", name: "Pollux", identity: null, appearance: { color: "#c2410c" } },
      { slug: "stray", error: "moved-home collision: …" },
      { name: "no slug" },
      "garbage",
    ],
    reads: { tile: {} },
  };

  it("lists each entity by its slug (what the door resolves) and display name, with the identity look", () => {
    expect(entityCandidates(listed)).toEqual([
      { id: "castor", name: "Castor", kind: "entity", avatar: { style: "watch-halo", color: "#336699" } },
      { id: "pollux", name: "Pollux", kind: "entity" },
    ]);
    expect(entityCandidates({})).toEqual([]);
    expect(entityCandidates(null)).toEqual([]);
  });

  it("filters by what follows @, on the name or the id, any case", () => {
    const names = entityCandidates(listed);
    expect(matchCandidates(names, "").map((c) => c.id)).toEqual(["castor", "pollux"]);
    expect(matchCandidates(names, "PO").map((c) => c.id)).toEqual(["pollux"]);
    expect(matchCandidates(names, "cas").map((c) => c.id)).toEqual(["castor"]);
    expect(matchCandidates(names, "x")).toEqual([]);
  });

  it("warns, on the first pick, that an entity reads the conversation", () => {
    expect(mentionNotice({ id: "castor", name: "Castor", kind: "entity" })).toBe("Castor will read this conversation's history.");
    expect(mentionNotice({ id: "a", name: "An agent", kind: "agent" })).toBeNull();
  });
});

describe("several mentions in one message", () => {
  it("are sent one after the other, in order, each after the previous one returned and was shown, naming the person's turn", async () => {
    const log: string[] = [];
    let release: (() => void) | null = null;
    const post = vi.fn((req: MentionRequest) => {
      log.push(`start ${req.entity}#${req.mention_index}`);
      return new Promise<MentionAnswer>((resolve) => {
        release = () => { log.push(`end ${req.entity}`); resolve(answer(req)); };
      });
    });
    const done = deliverMentions({
      text: "which plan holds?",
      mentions: [castor, pollux],
      repeatOf: "turn-person",
      post,
      onAnswer: (a) => { log.push(`shown ${a.run_id}`); },
    });
    await vi.waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    await new Promise((r) => setTimeout(r, 10));
    expect(post).toHaveBeenCalledTimes(1); // the second waits for the first
    release!();
    await vi.waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    release!();
    const outcome = await done;
    expect(log).toEqual(["start castor#0", "end castor", "shown turn-castor", "start pollux#1", "end pollux", "shown turn-pollux"]);
    expect(post.mock.calls.map(([req]) => req)).toEqual([
      { entity: "castor", text: "which plan holds?", mention_index: 0, repeat_of: "turn-person", mention_id: "turn-person:castor:0" },
      { entity: "pollux", text: "which plan holds?", mention_index: 1, repeat_of: "turn-person", mention_id: "turn-person:pollux:1" },
    ]);
    expect(outcome).toEqual({ message: "turn-person", answered: [answer({ entity: "castor", text: "", mention_index: 0, mention_id: "" }), answer({ entity: "pollux", text: "", mention_index: 1, mention_id: "" })], notes: [], unavailable: false, stopped: null, unsent: [] });
  });

  it("an entity in another conversation is said once and the next one is still asked", async () => {
    const post = vi.fn(async (req: MentionRequest) => {
      if (req.entity === "castor") throw refused(409, "Castor is in another conversation (session s-2). One conversation at a time: …", "in_another_conversation");
      return answer(req);
    });
    const outcome = await deliverMentions({ text: "hi", mentions: [castor, pollux], post });
    expect(post).toHaveBeenCalledTimes(2);
    expect(outcome.notes).toEqual(["Castor is in another conversation."]);
    expect(outcome.answered.map((a) => a.run_id)).toEqual(["turn-pollux"]);
    expect(mentionStatusLine(outcome)).toBe("Castor is in another conversation.");
  });

  it("the visit door's own 409s are handled the same way", async () => {
    const post = vi.fn(async (req: MentionRequest) => {
      if (req.entity === "castor") throw refused(409, "castor is asleep", "entity_asleep");
      return answer(req);
    });
    const outcome = await deliverMentions({ text: "hi", mentions: [castor, pollux], post });
    expect(outcome.notes).toEqual(["Castor is in another conversation."]);
    expect(post).toHaveBeenCalledTimes(2);
  });

  it("a name this account may not mention (404 entity_not_found, hidden is missing) is skipped with a sentence", async () => {
    const post = vi.fn(async (req: MentionRequest) => {
      if (req.entity === "pollux") throw refused(404, "entity 'pollux' not found under /data/entities", "entity_not_found");
      return answer(req);
    });
    const outcome = await deliverMentions({ text: "hi", mentions: [castor, pollux, vega], post });
    expect(post).toHaveBeenCalledTimes(3);
    expect(outcome.notes).toEqual(["Pollux cannot be mentioned here."]);
    expect(outcome.answered.map((a) => a.run_id)).toEqual(["turn-castor", "turn-vega"]);
  });

  it("an entity that cannot answer (503) stops the rest and gives the gateway's sentence", async () => {
    const post = vi.fn(async (req: MentionRequest) => {
      if (req.entity === "pollux") throw refused(503, "Pollux cannot answer: no model is chosen for this entity", "entity_cannot_answer");
      return answer(req);
    });
    const outcome = await deliverMentions({ text: "hi", mentions: [castor, pollux, vega], post });
    expect(post).toHaveBeenCalledTimes(2);
    expect(outcome.stopped).toBe("Pollux cannot answer: no model is chosen for this entity");
    expect(outcome.answered.map((a) => a.run_id)).toEqual(["turn-castor"]);
    expect(outcome.unsent).toEqual([pollux, vega]);
  });

  it("review 2026-11-09 S1: after a 503 the resend asks only the unsent, same words, same repeat_of, first index", async () => {
    const sent: MentionRequest[] = [];
    let polluxOk = false;
    const post = vi.fn(async (req: MentionRequest) => {
      sent.push(req);
      if (req.entity === "pollux" && !polluxOk) throw refused(503, "Pollux cannot answer right now.", "entity_cannot_answer");
      return answer(req);
    });
    const first = await deliverMentions({ text: "is the plan sound?", mentions: [castor, pollux], post, repeatOf: "turn-a" });
    expect(first.unsent).toEqual([pollux]);
    // The kit keeps only @Pollux and numbers it 0; the resend gives it back its first index.
    const again = mentionResend({ text: "is the plan sound?", repeatOf: "turn-a", unsent: first.unsent }, "is the plan sound?", [{ ...pollux, index: 0 }]);
    polluxOk = true;
    sent.length = 0;
    const second = await deliverMentions({ text: "is the plan sound?", mentions: again!, post, repeatOf: "turn-a", message: first.message });
    expect(sent).toEqual([{ entity: "pollux", text: "is the plan sound?", mention_index: 1, repeat_of: "turn-a", mention_id: "turn-a:pollux:1" }]);
    expect(second.unsent).toEqual([]);
  });

  it("one answer per mention (gateway f0f23bb0): a resend after a lost answer names the same mention_id; a new message another", async () => {
    const sent: MentionRequest[] = [];
    let lost = true;
    const post = vi.fn(async (req: MentionRequest) => {
      sent.push(req);
      if (req.entity === "pollux" && lost) throw new TypeError("Failed to fetch");
      return answer(req);
    });
    for (const repeatOf of ["turn-a", undefined]) {
      sent.length = 0;
      lost = true;
      const first = await deliverMentions({ text: "is the plan sound?", mentions: [castor, pollux], post, ...(repeatOf ? { repeatOf } : {}) });
      expect(first.unsent).toEqual([pollux]);
      lost = false;
      await deliverMentions({ text: "is the plan sound?", mentions: first.unsent, post, ...(repeatOf ? { repeatOf } : {}), message: first.message });
      expect(sent.map((r) => r.mention_id)).toEqual([`${first.message}:castor:0`, `${first.message}:pollux:1`, `${first.message}:pollux:1`]);
      if (repeatOf) expect(first.message).toBe(repeatOf);
    }
    // A new message: another turn, or another minted id.
    const a = await deliverMentions({ text: "hi", mentions: [castor], post, repeatOf: "turn-b" });
    const b = await deliverMentions({ text: "hi", mentions: [castor], post, repeatOf: "turn-c" });
    const c = await deliverMentions({ text: "hi", mentions: [castor], post });
    const d = await deliverMentions({ text: "hi", mentions: [castor], post });
    expect(new Set([a.message, b.message, c.message, d.message]).size).toBe(4);
    expect(mentionMessageKey("turn-a", () => "msg-x")).toBe("turn-a");
    expect(mentionMessageKey(undefined, () => "msg-x")).toBe("msg-x");
    expect(mintMessageId()).not.toBe(mintMessageId());
    expect(() => mentionId("", castor)).toThrow();
  });

  it("an entity named twice is asked once, at its first index", async () => {
    const post = vi.fn(async (req: MentionRequest) => answer(req));
    await deliverMentions({ text: "hi", mentions: [castor, pollux, { ...castor, index: 2 }], post });
    expect(post.mock.calls.map((c) => `${c[0].entity}#${c[0].mention_index}`)).toEqual(["castor#0", "pollux#1"]);
  });

  it("a repeat_of the gateway does not know (422) stops the rest with one sentence", async () => {
    const post = vi.fn(async () => { throw refused(422, "repeat_of 'turn-x' is not a turn of this conversation", "repeat_of_unknown"); });
    const outcome = await deliverMentions({ text: "hi", mentions: [castor, pollux], post, repeatOf: "turn-x" });
    expect(post).toHaveBeenCalledTimes(1);
    expect(outcome.stopped).toBe("Castor was not asked: the gateway did not find your message in this conversation.");
  });

  it("without a repeated turn, no repeat_of is sent (the mention_id names an id minted for the message)", async () => {
    const post = vi.fn(async (req: MentionRequest) => answer(req));
    const out = await deliverMentions({ text: "hi", mentions: [castor], post });
    expect(out.message).toMatch(/^msg-[0-9a-f]{24}$/);
    expect(post.mock.calls[0][0]).toEqual({ entity: "castor", text: "hi", mention_index: 0, mention_id: `${out.message}:castor:0` });
  });

  it("any other failure stops the rest and names the entity", async () => {
    const post = vi.fn(async () => { throw refused(500, "Internal Server Error"); });
    const outcome = await deliverMentions({ text: "hi", mentions: [castor, pollux], post });
    expect(post).toHaveBeenCalledTimes(1);
    expect(outcome.stopped).toBe("Castor did not answer: Internal Server Error");
  });

  it("a gateway without the mention route: one sentence, nothing more is sent", async () => {
    for (const [status, detail] of [[404, "Not Found"], [405, "Method Not Allowed"], [404, "anything"]] as const) {
      const post = vi.fn(async () => { throw refused(status, detail); });
      const outcome = await deliverMentions({ text: "hi", mentions: [castor, pollux], post });
      expect(post).toHaveBeenCalledTimes(1);
      expect(outcome.unavailable).toBe(true);
      expect(outcome.notes).toEqual([]);
      expect(mentionStatusLine(outcome)).toBe(MENTIONS_UNAVAILABLE);
    }
  });

  it("Stop rejects with the abort and sends nothing more", async () => {
    const stop = new AbortController();
    const post = vi.fn(async (_req: MentionRequest, signal?: AbortSignal) => {
      stop.abort();
      throw signal?.reason ?? new Error("aborted");
    });
    await expect(deliverMentions({ text: "hi", mentions: [castor, pollux], post, signal: stop.signal })).rejects.toBeTruthy();
    expect(post).toHaveBeenCalledTimes(1);
  });
});

describe("a mention sent with guidance (docs audit 2026-11-09: it was refused 422 repeat_of_unknown)", () => {
  // The gateway's rule (AbstractGateway entity_mentions `_check_repeat_of`): a `repeat_of` must be
  // the caller's own turn of this session whose prompt, trimmed, IS the text, trimmed.
  const prompts = new Map([["turn-running", "plan the trip to Lyon"]]);
  const door = () => vi.fn(async (req: MentionRequest) => {
    if (req.repeat_of !== undefined && (prompts.get(req.repeat_of) ?? "").trim() !== req.text.trim())
      throw refused(422, "That earlier message is not one of your own turns in this conversation.", "repeat_of_unknown");
    return answer(req);
  });

  it("the door refuses a repeat_of whose turn carries other words (the old guidance wiring)", async () => {
    const post = door();
    const out = await deliverMentions({ text: "and the weather?", mentions: [castor], post, repeatOf: "turn-running" });
    expect(out.stopped).toMatch(/did not find your message/);
  });

  it("guidance starts no turn: its mentions name none, carry the typed words and a key minted per message; shown after the running turn", async () => {
    const turn = mentionTurn({ steered: "turn-running" });
    expect(turn).toEqual({ anchor: "turn-running", repeatOf: "" });
    const post = door();
    const first = await deliverMentions({ text: "and the weather?", mentions: [castor], post, repeatOf: turn.repeatOf });
    expect(first.stopped).toBeNull();
    expect(first.answered.map((a) => a.run_id)).toEqual(["turn-castor"]);
    expect(first.message).toMatch(/^msg-[0-9a-f]{24}$/);
    expect(post.mock.calls[0][0]).toEqual({ entity: "castor", text: "and the weather?", mention_index: 0, mention_id: `${first.message}:castor:0` });
    // A second guidance to the same running turn is a new message: its own ids, its own answer.
    const second = await deliverMentions({ text: "and the trains?", mentions: [castor], post, repeatOf: mentionTurn({ steered: "turn-running" }).repeatOf });
    expect(second.message).not.toBe(first.message);
  });

  it("a message that started a turn names it (that turn's prompt is the words), and the door takes it", async () => {
    prompts.set("turn-new", "and the weather?");
    const turn = mentionTurn({ started: "turn-new" });
    expect(turn).toEqual({ anchor: "turn-new", repeatOf: "turn-new" });
    const post = door();
    const out = await deliverMentions({ text: " and the weather? ", mentions: [castor], post, repeatOf: turn.repeatOf });
    expect(out.stopped).toBeNull();
    expect(post.mock.calls[0][0]).toMatchObject({ repeat_of: "turn-new", mention_id: "turn-new:castor:0" });
  });
});

describe("refusals, as the gateway sends them", () => {
  it("every refusal of the door is coded; an uncoded 404/405 is a gateway without the route", () => {
    expect(mentionRefusal(refused(404, "Not Found"))).toBe("route_missing");
    expect(mentionRefusal(refused(405, "Method Not Allowed"))).toBe("route_missing");
    expect(mentionRefusal(refused(404, "entity 'x' not found under /e", "entity_not_found"))).toBe("not_offered");
    expect(mentionRefusal(refused(409, "busy", "in_another_conversation"))).toBe("elsewhere");
    expect(mentionRefusal(refused(503, "x cannot answer", "entity_cannot_answer"))).toBe("cannot_answer");
    expect(mentionRefusal(refused(422, "repeat_of 'r' is not a turn", "repeat_of_unknown"))).toBe("repeat_unknown");
    expect(mentionRefusal(refused(422, "text is empty"))).toBe("failed");
    expect(mentionRefusal(new TypeError("Failed to fetch"))).toBe("failed");
  });

  it("the client reads the gateway's code from the body or the X-Gateway-Error-Code header", async () => {
    const host: AssistantHost = {
      kind: "browser",
      gatewayUrl: (route) => `api/gateway/${route}`,
      auth: { kind: "app-cookie-session", credentials: "same-origin", headers: (mutating) => (mutating ? { "X-AbstractAssistant-CSRF": "tok" } : {}) },
      signIn: "app-server-modal",
      capabilities: {
        tray: { available: false, reason: "" },
        globalHotkey: { available: false, reason: "" },
        systemNotifications: { available: false, reason: "" },
        autostart: { available: false, reason: "" },
        microphone: { available: true },
        audioPlayback: { available: true },
      },
    };
    const client = new GatewayClient(host);
    const calls: Array<{ url: string; body: unknown }> = [];
    const replies = [
      new Response(JSON.stringify({ detail: "Castor is in another conversation (session s-2).", code: "in_another_conversation", session_id: "s-2" }), { status: 409 }),
      new Response(JSON.stringify({ detail: "Pollux cannot answer: no model" }), { status: 503, headers: { "X-Gateway-Error-Code": "entity_cannot_answer" } }),
      new Response(JSON.stringify({ run_id: "turn-1", turn_id: "t-3", author: { kind: "entity", name: "Castor" }, session_id: "s-1", mention_index: 0, reply: "Yes.", visit: {} }), { status: 200 }),
    ];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
      calls.push({ url, body: JSON.parse(String(init.body)) });
      return replies.shift()!;
    }));
    try {
      const first = await client.mention("s-1", { entity: "castor", text: "hi", mention_index: 0 }).catch((e) => e);
      expect(first).toBeInstanceOf(GatewayHttpError);
      expect([first.status, first.code, mentionRefusal(first)]).toEqual([409, "in_another_conversation", "elsewhere"]);
      const second = await client.mention("s-1", { entity: "pollux", text: "hi", mention_index: 1 }).catch((e) => e);
      expect([second.status, second.code, second.detail, mentionRefusal(second)]).toEqual([503, "entity_cannot_answer", "Pollux cannot answer: no model", "cannot_answer"]);
      expect(await client.mention("s-1", { entity: "castor", text: "hi", mention_index: 0 })).toEqual({ run_id: "turn-1", reply: "Yes.", mention_index: 0 });
      expect(calls[0]).toEqual({ url: "api/gateway/sessions/s-1/mentions", body: { entity: "castor", text: "hi", mention_index: 0 } });
      replies.push(new Response(JSON.stringify({ run_id: "turn-2", reply: "ok", mention_index: 0, repeat_of: "r-1" }), { status: 200 }));
      await client.mention("s-1", { entity: "castor", text: "hi", mention_index: 0, repeat_of: "r-1" });
      expect(calls.at(-1)?.body).toEqual({ entity: "castor", text: "hi", mention_index: 0, repeat_of: "r-1" });
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe("telling an older gateway and a mention turn apart", () => {
  it("a shown user message without `author` means the gateway predates mentions", () => {
    expect(gatewayLacksTurnAuthors([{ id: "r:input", role: "user", content: "hi" }])).toBe(true);
    expect(gatewayLacksTurnAuthors([{ id: "r:input", role: "user", content: "hi", author: null }])).toBe(false);
    expect(gatewayLacksTurnAuthors([{ id: "r:final", role: "assistant", content: "hello" }])).toBe(false);
    expect(gatewayLacksTurnAuthors([])).toBe(false);
  });

  it("a turn repeating another's words says so on its view's input message (repeat_of)", () => {
    const input = (extra: object) => ({ id: "m:input", role: "user", kind: "prompt", text: "hi", run_id: "m", ...extra });
    expect(viewRepeatOf({ root_run_id: "m", workflow: { id: "entity-mention" }, messages: [input({ repeat_of: "r" }), { id: "m:final", role: "assistant", run_id: "m" }] })).toEqual({ runId: "m", repeatOf: "r" });
    // A mention sent on its own (no repeat_of) keeps its prompt: nothing to fold, whatever its workflow.
    expect(viewRepeatOf({ root_run_id: "m", workflow: { id: "entity-mention" }, messages: [input({})] })).toBeNull();
    expect(viewRepeatOf({ root_run_id: "m", messages: [{ ...input({ repeat_of: "r" }), run_id: "child" }] })).toBeNull();
    expect(viewRepeatOf(null)).toBeNull();
  });
});

describe("the workspace keeps a stopped message's mention_id key for its resend", () => {
  const ws = readFileSync(new URL("../ui/Workspace.tsx", import.meta.url), "utf8");
  it("holds the key the first send used and passes it back on the resend (never a new one)", () => {
    expect(ws).toContain("pendingResend.current = { sid, message: outcome.message, turn, resend: { text, repeatOf: turn.repeatOf || null, unsent: outcome.unsent } };");
    expect(ws).toContain("await sendMentions(held.sid, held.turn, held.resend.text, again, ctx?.signal, held.message);");
    expect(ws).toContain("...(message ? { message } : {}), post: (req, s) => client.mention(sid, req, s)");
  });
  it("a started turn names itself; guidance (or an answer) names no repeat_of, its answers still follow the running turn", () => {
    expect(ws).toContain("sendMentions(sid, mentionTurn({ started: run_id }), text, mentions, ctx?.signal)");
    expect(ws).toContain("sendMentions(ensureSession(), mentionTurn({ steered: props.runId }), text, mentions, ctx?.signal)");
    expect(ws).toContain("deliverMentions({ text, mentions, repeatOf: turn.repeatOf,");
    expect(ws).toContain("const anchor = turn.anchor;");
  });
});

describe("the session agent stays silent for what is addressed to entities (AbstractGateway c26d38a2)", () => {
  const ws = readFileSync(new URL("../ui/Workspace.tsx", import.meta.url), "utf8");
  it("the start names the mentioned entities in pick order, each once; no entity, no key", () => {
    expect(startRunMentions([vega, castor, pollux, { ...castor, index: 3 }])).toEqual({ mentions: ["castor", "pollux", "vega"] });
    expect(startRunMentions([pollux, castor])).toEqual({ mentions: ["castor", "pollux"] });
    const none = startRunMentions([]);
    expect(none).toEqual({});
    expect("mentions" in none).toBe(false);
  });
  it("POST runs/start carries them as sent; a message without mentions sends no key", async () => {
    const client = new GatewayClient({
      kind: "browser",
      gatewayUrl: (route) => `api/gateway/${route}`,
      auth: { kind: "app-cookie-session", credentials: "same-origin", headers: () => ({}) },
      signIn: "app-server-modal",
      capabilities: {
        tray: { available: false, reason: "" },
        globalHotkey: { available: false, reason: "" },
        systemNotifications: { available: false, reason: "" },
        autostart: { available: false, reason: "" },
        microphone: { available: true },
        audioPlayback: { available: true },
      },
    } as AssistantHost);
    const bodies: Record<string, unknown>[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init: RequestInit) => {
      bodies.push(JSON.parse(String(init.body)));
      return new Response(JSON.stringify({ run_id: `r-${bodies.length}` }), { status: 200 });
    }));
    try {
      await client.startRun({ flow_id: "@default", interface: "abstractassistant.agent.v1", session_id: "s-1", input_data: { prompt: "hi" }, ...startRunMentions([pollux, castor]) });
      await client.startRun({ flow_id: "@default", interface: "abstractassistant.agent.v1", session_id: "s-1", input_data: { prompt: "hi" }, ...startRunMentions([]) });
      expect(bodies[0].mentions).toEqual(["castor", "pollux"]);
      expect("mentions" in bodies[1]).toBe(false);
    } finally {
      vi.unstubAllGlobals();
    }
  });
  it("the workspace sends them with both workflow choices and remembers the turn they started", () => {
    expect(ws).toContain("const mentioned = startRunMentions(mentions);");
    expect(ws.match(/input_data, \.\.\.\(avatarMode \? \{ conversation: true \} : \{\}\), \.\.\.mentioned \}/g)?.length).toBe(2);
    expect(ws).toContain("if (mentioned.mentions) entitiesAnswer.current.add(run_id);");
    expect(ws).toContain("turnOutcome(props.runId, snapshot.status, snapshot.run, snapshot.messages, { entitiesAnswer: entitiesAnswer.current.has(props.runId) })");
  });
});

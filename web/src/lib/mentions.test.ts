// `@entity` mentions (lib/mentions.ts): the names offered, the order mentions are sent in, and how
// each refusal of the gateway's mention door is handled (contract: abstractgateway
// docs/entities.md "Mentioning an entity from any chat").
import { describe, expect, it, vi } from "vitest";

import type { AssistantHost } from "../host";
import { GatewayClient, GatewayHttpError } from "../gateway/client";
import {
  MENTIONS_UNAVAILABLE,
  deliverMentions,
  entityCandidates,
  gatewayLacksTurnAuthors,
  isMentionTurnView,
  matchCandidates,
  mentionNotice,
  mentionRefusal,
  mentionStatusLine,
  type MentionAnswer,
  type MentionRequest,
} from "./mentions";

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
  it("are sent one after the other, in order, each after the previous one returned and was shown", async () => {
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
      { entity: "castor", text: "which plan holds?", mention_index: 0 },
      { entity: "pollux", text: "which plan holds?", mention_index: 1 },
    ]);
    expect(outcome).toEqual({ answered: [answer({ entity: "castor", text: "", mention_index: 0 }), answer({ entity: "pollux", text: "", mention_index: 1 })], notes: [], unavailable: false, stopped: null });
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

  it("a name this account may not mention (404, hidden is missing) is skipped with a sentence", async () => {
    const post = vi.fn(async (req: MentionRequest) => {
      if (req.entity === "pollux") throw refused(404, "entity 'pollux' not found under /data/entities");
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
  });

  it("any other failure stops the rest and names the entity", async () => {
    const post = vi.fn(async () => { throw refused(500, "Internal Server Error"); });
    const outcome = await deliverMentions({ text: "hi", mentions: [castor, pollux], post });
    expect(post).toHaveBeenCalledTimes(1);
    expect(outcome.stopped).toBe("Castor did not answer: Internal Server Error");
  });

  it("a gateway without the mention route: one sentence, nothing more is sent", async () => {
    for (const [status, detail] of [[404, "Not Found"], [405, "Method Not Allowed"]] as const) {
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

describe("refusals, as the gateway sends them", () => {
  it("only the framework's own unknown-route answer means 'no mention door'", () => {
    expect(mentionRefusal(refused(404, "Not Found"))).toBe("route_missing");
    expect(mentionRefusal(refused(405, "Method Not Allowed"))).toBe("route_missing");
    // A coded 404 or an entity's 404 sentence is about the entity, not the route.
    expect(mentionRefusal(refused(404, "Not Found", "entity_missing"))).toBe("not_offered");
    expect(mentionRefusal(refused(404, "entity 'x' not found under /e"))).toBe("not_offered");
    expect(mentionRefusal(refused(409, "busy", "in_another_conversation"))).toBe("elsewhere");
    expect(mentionRefusal(refused(503, "x cannot answer", "entity_cannot_answer"))).toBe("cannot_answer");
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

  it("a mention turn is known by its view's workflow", () => {
    expect(isMentionTurnView({ root_run_id: "m", workflow: { id: "entity-mention", bundle_id: null, flow_id: "entity-mention" } })).toBe(true);
    expect(isMentionTurnView({ root_run_id: "r", workflow: { id: "assistant@1:main" } })).toBe(false);
    expect(isMentionTurnView({ root_run_id: "r", workflow: null })).toBe(false);
  });
});

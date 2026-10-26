// The follower against a fake gateway (fetch replaced). The first case is the
// adversary's repro (untracked/apple-web-wave/adv/follow/repro_follow.ts): a
// ledger stream closed WITHOUT `event: done` used to end the follow with the
// turn "running" forever and no error.
import { afterEach, describe, expect, it } from "vitest";

import type { AssistantHost } from "../host";
import { createTurnStore } from "../lib/turn_store";
import { GatewayClient } from "./client";
import { followTurn } from "./follow";

const enc = new TextEncoder();
const sse = (frames: string[], withDone: boolean) =>
  new Response(
    new ReadableStream({
      start(c) {
        for (const f of frames) c.enqueue(enc.encode(f));
        if (withDone) c.enqueue(enc.encode("event: done\ndata: {}\n\n"));
        c.close();
      },
    }),
    { status: 200, headers: { "content-type": "text/event-stream" } },
  );
const step = (cursor: number, record: unknown) => `event: step\ndata: ${JSON.stringify({ cursor, record })}\n\n`;
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const host = {
  kind: "browser",
  gatewayUrl: (r: string) => `http://x/api/gateway/${r}`,
  auth: { kind: "app-cookie-session", credentials: "same-origin", headers: () => ({}) },
  signIn: "app-server-modal",
} as unknown as AssistantHost;

type Route = (path: string) => Response | Promise<Response>;
const realFetch = globalThis.fetch;
function fakeGateway(route: Route) {
  const calls: string[] = [];
  globalThis.fetch = (async (url: string) => {
    const path = String(url).replace("http://x/api/gateway/", "");
    calls.push(path);
    return route(path);
  }) as typeof fetch;
  return calls;
}
afterEach(() => {
  globalThis.fetch = realFetch;
});

async function until(pred: () => boolean, ms = 2000) {
  const t0 = Date.now();
  while (!pred() && Date.now() - t0 < ms) await new Promise((r) => setTimeout(r, 5));
}

const FAST = { backoffMs: [1, 1, 1, 1], drainIntervalMs: 1 };
const reason = { step_id: "s1", status: "started", effect: { type: "llm_call" }, node_id: "reason" };
const end = { step_id: "s9", status: "completed", result: { output: { response: "The answer." } } };

describe("followTurn", () => {
  it("a stream closed without `done` while the run still runs is RECONNECTED from its cursor (adversary repro)", async () => {
    let streams = 0;
    const calls = fakeGateway((p) => {
      if (p.includes("/ledger/stream")) {
        streams += 1;
        return streams === 1 ? sse([step(1, reason)], false) : sse([step(2, end)], true);
      }
      if (p.startsWith("runs/root/ledger?")) return json({ items: [], next_after: 2 });
      if (p === "runs/root") return json({ run_id: "root", status: streams >= 2 ? "completed" : "running" });
      return json({}, 404);
    });
    const store = createTurnStore("root");
    const errors: string[] = [];
    const stop = followTurn({ client: new GatewayClient(host), rootRunId: "root", dispatch: store.dispatch, getState: store.getState, onError: (m) => errors.push(m), ...FAST });
    await until(() => store.getState().status === "completed");
    stop();
    expect(calls.filter((c) => c.includes("/ledger/stream"))).toEqual(["runs/root/ledger/stream?after=0", "runs/root/ledger/stream?after=1"]);
    expect(store.getState().status).toBe("completed");
    expect(store.getState().answer).toBe("The answer.");
    expect(errors).toEqual([]);
  });

  it("`done` is not trusted alone: a run still running after `done` is read again", async () => {
    let streams = 0;
    fakeGateway((p) => {
      if (p.includes("/ledger/stream")) return (streams += 1), sse(streams === 1 ? [] : [step(1, end)], true);
      if (p.startsWith("runs/root/ledger?")) return json({ items: [], next_after: 1 });
      if (p === "runs/root") return json({ status: streams >= 2 ? "completed" : "running" });
      return json({}, 404);
    });
    const store = createTurnStore("root");
    const stop = followTurn({ client: new GatewayClient(host), rootRunId: "root", dispatch: store.dispatch, getState: store.getState, onError: () => {}, ...FAST });
    await until(() => store.getState().status === "completed");
    stop();
    expect(streams).toBe(2);
    expect(store.getState().answer).toBe("The answer.");
  });

  it("a terminal run is DRAINED: records written after the stream closed still reach the turn", async () => {
    let pages = 0;
    fakeGateway((p) => {
      if (p.includes("/ledger/stream")) return sse([step(1, reason)], false);
      if (p.startsWith("runs/root/ledger?")) return (pages += 1), pages === 1 ? json({ items: [end], next_after: 2 }) : json({ items: [], next_after: 2 });
      if (p === "runs/root") return json({ status: "completed" });
      return json({}, 404);
    });
    const store = createTurnStore("root");
    const stop = followTurn({ client: new GatewayClient(host), rootRunId: "root", dispatch: store.dispatch, getState: store.getState, onError: () => {}, ...FAST });
    await until(() => store.getState().status === "completed");
    stop();
    expect(store.getState().answer).toBe("The answer.");
    expect(store.getState().cursors.root).toBe(2);
  });

  it("gives up after repeated connection failures, says so, and marks the turn lost", async () => {
    fakeGateway(() => json({ detail: "gateway down" }, 502));
    const store = createTurnStore("root");
    const errors: string[] = [];
    followTurn({ client: new GatewayClient(host), rootRunId: "root", dispatch: store.dispatch, getState: store.getState, onError: (m) => errors.push(m), ...FAST });
    await until(() => errors.length > 0);
    expect(errors[0]).toMatch(/Live updates stopped/);
    expect(store.getState().follow).toBe("lost");
  });
});

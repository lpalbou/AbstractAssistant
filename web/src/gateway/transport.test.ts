import { describe, expect, it, vi } from "vitest";

import type { AssistantHost } from "../host";
import { GatewayClient, GatewayHttpError } from "./client";
import { createAssistantTransport } from "./transport";

function host(csrf = "tok"): AssistantHost {
  return {
    kind: "browser",
    gatewayUrl: (route) => `api/gateway/${route}`,
    auth: {
      kind: "app-cookie-session",
      credentials: "same-origin",
      headers: (mutating) => {
        if (!mutating) return {};
        if (!csrf) throw new Error("You are signed out of the gateway");
        return { "X-AbstractAssistant-CSRF": csrf };
      },
    },
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
}

describe("the workflow transport (panel-chat's controller over this app's gateway calls)", () => {
  it("passes ledger steps as {cursor, record}, valid live frames as deltas, and skips a malformed frame", async () => {
    const client = new GatewayClient(host());
    const errors: string[] = [];
    vi.spyOn(client, "streamLedger").mockImplementation(async (_run, _after, handlers) => {
      handlers.onOpen?.();
      handlers.onStep({ cursor: 3, record: { status: "completed" } });
      handlers.onDelta?.("llm.delta", JSON.stringify({ kind: "llm.delta", run_id: "r", root_run_id: "r", node_id: "n", call_id: "c", seq: 0, text: "Hel", channel: "content", snapshot: false }));
      handlers.onDelta?.("llm.delta", "{not json");
      return { cursor: 3, done: true };
    });
    const t = createAssistantTransport(client, { onDeltaError: (m) => errors.push(m) });
    const steps: unknown[] = [];
    const deltas: unknown[] = [];
    let opened = false;
    await t.streamLedger("r", 0, (s) => steps.push(s), new AbortController().signal, () => (opened = true), (d) => deltas.push(d));
    expect(opened).toBe(true);
    expect(steps).toEqual([{ cursor: 3, record: { status: "completed" } }]);
    expect(deltas).toHaveLength(1);
    expect(errors).toHaveLength(1);
    expect(errors[0]).toMatch(/Malformed llm.delta/);
  });

  it("stamps this app's client id on commands", async () => {
    const client = new GatewayClient(host());
    const sent = vi.spyOn(client, "submitCommand").mockResolvedValue({ accepted: true });
    await createAssistantTransport(client, { onDeltaError: () => {} }).submitCommand({ command_id: "c", run_id: "r", type: "resume", payload: {} });
    expect(sent.mock.calls[0][0]).toMatchObject({ client_id: "abstractassistant-web", type: "resume" });
  });
});

describe("the kit's fetches go through the host", () => {
  it("fetchGateway sends the CSRF twin on a mutation and refuses one when signed out", async () => {
    const calls: Array<[string, RequestInit]> = [];
    vi.stubGlobal("fetch", async (url: string, init: RequestInit) => (calls.push([url, init]), new Response("{}", { status: 200 })));
    await new GatewayClient(host()).fetchGateway("api/gateway/about");
    await new GatewayClient(host()).fetchGateway("api/gateway/runs/start", { method: "POST" });
    expect((calls[0][1].headers as Record<string, string>)["X-AbstractAssistant-CSRF"]).toBeUndefined();
    expect((calls[1][1].headers as Record<string, string>)["X-AbstractAssistant-CSRF"]).toBe("tok");
    expect(calls[1][1].credentials).toBe("same-origin");
    await expect(new GatewayClient(host("")).fetchGateway("api/gateway/runs/start", { method: "POST" })).rejects.toThrow(/signed out/);
    vi.unstubAllGlobals();
  });

  it("policyRequest rejects a non-2xx answer with its status and body (the kit maps a 409)", async () => {
    vi.stubGlobal("fetch", async () => new Response(JSON.stringify({ detail: { reason_code: "revision_conflict" } }), { status: 409 }));
    const err = await new GatewayClient(host()).policyRequest("api/gateway/sessions/s/tool-policy", { method: "POST", body: {} }).catch((e) => e);
    expect(err).toBeInstanceOf(GatewayHttpError);
    expect(err.status).toBe(409);
    expect(err.body).toEqual({ detail: { reason_code: "revision_conflict" } });
    vi.unstubAllGlobals();
  });
});

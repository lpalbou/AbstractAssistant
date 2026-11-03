import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { normalizeToolCatalog, trustAfterApproveAll } from "@abstractframework/ui-kit";

import { allowedByApproveAll, automationToolModes, automationTrust, setAutomationTrust, trustedAutomations } from "./automation_tools";

const catalog = normalizeToolCatalog({
  items: [
    { name: "web_search", toolset: "web", enabled: true, approval_default: "ask", risk_rank: 1 },
    { name: "fetch_url", toolset: "web", enabled: true, approval_default: "ask", risk_rank: 1 },
    { name: "write_file", toolset: "files", enabled: true, approval_default: "ask", risk_rank: 2 },
    { name: "send_email", toolset: "email", enabled: true, approval_default: "ask", risk_rank: 3, risk_tier: "outreach" },
    { name: "read_file", toolset: "files", enabled: true, approval_default: "auto", risk_rank: 1 },
  ],
});

const definition = (runtime: Record<string, unknown>, tools?: string[]) => ({ target: { input_data: { prompt: "x", ...(tools ? { tools } : {}), _runtime: runtime } } });

describe("an automation's tools, from its definition (the watch's mode for an automation)", () => {
  it("its policy says Auto or Ask; a tool not offered is Off; the rest as the gateway asks", () => {
    const modes = automationToolModes(catalog, definition({ allowed_tools: ["web_search", "fetch_url", "read_file"], tool_policy: { auto_approve_tools: ["fetch_url"], require_approval_tools: ["web_search"] } }));
    expect(modes).toEqual({ web_search: "ask", fetch_url: "auto", write_file: "off", send_email: "off", read_file: "auto" });
  });

  it("the definition's policy wins over an older run-input one", () => {
    const modes = automationToolModes(catalog, { policy: { tool_policy: { auto_approve_tools: ["write_file"], require_approval_tools: [] } },
      target: { input_data: { _runtime: { tool_policy: { require_approval_tools: ["write_file"] } } } } });
    expect(modes.write_file).toBe("auto");
  });

  it("no tools written: the workflow's own, as the gateway asks", () => {
    expect(automationToolModes(catalog, { target: { input_data: { prompt: "x" } } }).write_file).toBe("ask");
  });
});

describe("Allowed for its runs", () => {
  const modes = automationToolModes(catalog, definition({ allowed_tools: ["web_search", "fetch_url", "write_file", "send_email", "read_file"] }));

  it("Approve all on one call allows the tools on Ask up to its risk, never a send to other people", () => {
    const trust = trustAfterApproveAll(catalog, modes, ["web_search"]);
    expect(trust).toContain("web_search");
    expect(trust).not.toContain("send_email");
  });

  it("the browser answers a call only when every tool is allowed and still used", () => {
    expect(allowedByApproveAll(modes, ["web_search", "fetch_url"], ["web_search", "fetch_url"])).toBe(true);
    expect(allowedByApproveAll(modes, ["web_search"], ["web_search", "fetch_url"])).toBe(false);
    expect(allowedByApproveAll({ ...modes, web_search: "off" }, ["web_search"], ["web_search"])).toBe(false);
    expect(allowedByApproveAll(modes, ["unknown_tool"], ["unknown_tool"])).toBe(false);
    expect(allowedByApproveAll(modes, ["web_search"], [])).toBe(false);
  });
});

describe("the trust book (this browser, per account)", () => {
  const store = new Map<string, string>();
  beforeEach(() => {
    (globalThis as { localStorage?: unknown }).localStorage = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
    };
  });
  afterEach(() => {
    store.clear();
    delete (globalThis as { localStorage?: unknown }).localStorage;
  });

  it("keeps an automation's allowed tools per account; Ask again empties it", () => {
    setAutomationTrust("me", "a1", ["web_search", "fetch_url"]);
    expect(automationTrust("me", "a1")).toEqual(["fetch_url", "web_search"]);
    expect(automationTrust("someone-else", "a1")).toEqual([]);
    expect(trustedAutomations("me")).toEqual(["a1"]);
    setAutomationTrust("me", "a1", []);
    expect(trustedAutomations("me")).toEqual([]);
  });

  it("a browser that keeps nothing: nothing is allowed", () => {
    delete (globalThis as { localStorage?: unknown }).localStorage;
    expect(automationTrust("me", "a1")).toEqual([]);
    expect(() => setAutomationTrust("me", "a1", ["x"])).not.toThrow();
  });
});

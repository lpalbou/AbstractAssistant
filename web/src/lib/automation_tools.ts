/**
 * An automation's tools and the watch's "Allowed for its runs" (AppModel.trustAll /
 * allowedByApproveAll): what each tool does for its runs, from its definition, and the tools an
 * Approve all on one of its runs allowed, which this browser then approves when it sees them. The
 * Approve all rule itself is the kit's (`trustAfterApproveAll`).
 */
import type { ToolCatalogItem, ToolMode } from "@abstractframework/ui-kit";

import type { JsonObject } from "./automations";

const names = (v: unknown): string[] | null => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : null);
const obj = (v: unknown): JsonObject | null => (v && typeof v === "object" && !Array.isArray(v) ? (v as JsonObject) : null);

/**
 * What each tool does for the automation's runs (the watch's `mode(of:for: .automation)`): on Auto
 * or Ask as its definition says, Off when it is not among the tools offered, else as the gateway asks.
 */
export function automationToolModes(catalog: readonly ToolCatalogItem[], definition: unknown): Record<string, ToolMode> {
  const input = obj(obj(obj(definition)?.target)?.input_data) ?? {};
  const runtime = obj(input._runtime) ?? {};
  // The definition's policy (what the runtime applies); an older definition kept it in its inputs.
  const policy = obj(obj(obj(definition)?.policy)?.tool_policy) ?? obj(runtime.tool_policy) ?? {};
  const auto = new Set(names(policy.auto_approve_tools) ?? []);
  const ask = new Set(names(policy.require_approval_tools) ?? []);
  const offered = names(runtime.allowed_tools) ?? names(input.tools);
  const out: Record<string, ToolMode> = {};
  for (const t of catalog) {
    out[t.name] = auto.has(t.name) ? "auto" : ask.has(t.name) ? "ask" : offered && !offered.includes(t.name) ? "off" : t.gatewayDefault;
  }
  return out;
}

/**
 * The browser may answer this tool approval for the person: every call is a tool an Approve all
 * allowed for the automation and that its runs still use (never Off, never unknown). The
 * automation's own Auto plays no part: only what the person allowed (the watch's poll rule).
 */
export function allowedByApproveAll(modes: Readonly<Record<string, ToolMode>>, trust: readonly string[], calls: readonly string[]): boolean {
  return calls.length > 0 && calls.every((name) => trust.includes(name) && modes[name] !== undefined && modes[name] !== "off");
}

const TRUST_KEY = "abstractassistant.automationTrust";

type TrustBook = Record<string, string[]>;

function readBook(scope: string): TrustBook {
  try {
    const raw = localStorage.getItem(`${TRUST_KEY}:${scope}`);
    const parsed = raw ? (JSON.parse(raw) as unknown) : null;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as TrustBook) : {};
  } catch {
    return {};
  }
}

/** The tools an Approve all allowed for an automation's runs, in this browser for this account. */
export function automationTrust(scope: string, automationId: string): string[] {
  return names(readBook(scope)[automationId]) ?? [];
}

/** Sets them (empty: they ask again, from the next call). */
export function setAutomationTrust(scope: string, automationId: string, tools: readonly string[]): void {
  const book = readBook(scope);
  if (tools.length) book[automationId] = [...tools].sort();
  else delete book[automationId];
  try {
    localStorage.setItem(`${TRUST_KEY}:${scope}`, JSON.stringify(book));
  } catch {
    // A browser that keeps nothing: the person approves each call.
  }
}

/** Every automation with a trust list, in this browser for this account. */
export function trustedAutomations(scope: string): string[] {
  return Object.keys(readBook(scope));
}

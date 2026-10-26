/**
 * The tools a web turn may use and which of them ask first: the desktop's
 * lists with no local per-tool settings (abstractassistant/controller.py
 * `_compute_tool_inventory` :1664-1760, `allowed_tools_for_run` :1784,
 * `tool_policy_for_run` :1818), read from the gateway's `GET
 * /discovery/tools`. Rules:
 * - a tool the gateway disabled (`enabled: false`) is not offered;
 * - `approval_default: "auto"` runs without asking; `"ask"` asks;
 * - a tool with NO `approval_default` asks. (The desktop falls back to its
 *   local ToolApprovalPolicy lists there, for gateways older than the field;
 *   the web has no local list and asks.)
 * - order: by toolset, then name; a name listed twice counts once.
 * The web has no per-tool settings and no "trust this chat" grant (v1): every
 * call the gateway does not mark auto is shown for approval.
 */

type Json = Record<string, unknown>;
const isObj = (v: unknown): v is Json => Boolean(v) && typeof v === "object" && !Array.isArray(v);
const txt = (v: unknown) => (typeof v === "string" ? v.trim() : "");

export type RunTools = {
  allowed_tools: string[];
  tool_policy: { auto_approve_tools: string[]; require_approval_tools: string[] };
};

export function runToolsFromDiscovery(payload: unknown): RunTools {
  if (!isObj(payload) || !Array.isArray(payload.items)) {
    throw new Error("The gateway's tool list (discovery/tools) has no items: the message was not sent.");
  }
  const rows = payload.items
    .filter(isObj)
    .map((r) => ({
      name: txt(r.name),
      toolset: (txt(r.toolset) || txt(r.toolset_id) || txt(r.toolsetId)).toLowerCase(),
      enabled: r.enabled !== false,
      approval: txt(r.approval_default).toLowerCase(),
    }))
    .filter((r) => r.name);
  rows.sort((a, b) => (a.toolset === b.toolset ? (a.name < b.name ? -1 : a.name > b.name ? 1 : 0) : a.toolset < b.toolset ? -1 : 1));
  const seen = new Set<string>();
  const out: RunTools = { allowed_tools: [], tool_policy: { auto_approve_tools: [], require_approval_tools: [] } };
  for (const r of rows) {
    if (seen.has(r.name)) continue;
    seen.add(r.name);
    if (!r.enabled) continue;
    out.allowed_tools.push(r.name);
    (r.approval === "auto" ? out.tool_policy.auto_approve_tools : out.tool_policy.require_approval_tools).push(r.name);
  }
  return out;
}

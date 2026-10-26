/**
 * Which workflow a new turn starts: the SAME decision as the desktop
 * (abstractassistant/controller.py current_workflow + gateway_service.py
 * _catalog_workflows / executable_contract_problem) and the iPhone
 * (phone/iphone/docs/architecture.md: "chooses the explicit catalog workflow
 * when set, otherwise uses @default with abstractassistant.agent.v1").
 *
 * PRESENCE CHECK ONLY. The web client never publishes, promotes or edits a
 * workflow (backlog overview item 0): when nothing runnable is on the
 * gateway it says why and sends nothing.
 */

export const ASSISTANT_INTERFACE = "abstractassistant.agent.v1";
export const MANAGED_BUNDLE_ID = "abstractassistant-orchestrator";

export type WorkflowStart =
  | { flow_id: "@default"; interface: string; label: string; source: "gateway_default" }
  | {
      flow_id: string;
      bundle_id: string;
      bundle_version: string;
      registry_scope: string;
      label: string;
      source: "account_choice" | "built_in";
    };

export class WorkflowUnavailable extends Error {
  constructor(message: string) {
    super(message);
    this.name = "WorkflowUnavailable";
  }
}

type Json = Record<string, unknown>;
const isObj = (v: unknown): v is Json => Boolean(v) && typeof v === "object" && !Array.isArray(v);
const txt = (v: unknown) => (typeof v === "string" ? v.trim() : "");

/** Why `payload` is not a `GET /bundles?executable_for=<iface>` answer ("" when it is). */
export function executableContractProblem(payload: unknown, iface: string): string {
  if (!isObj(payload)) return "The gateway's workflow list was not a JSON object.";
  const echoed = txt(payload.executable_for);
  if (echoed !== iface) {
    return echoed
      ? `The gateway listed workflows for ${echoed}, not ${iface}.`
      : "This gateway does not filter workflows per app (no executable_for in its answer): update the gateway.";
  }
  if (!Array.isArray(payload.items)) return "The gateway's workflow list has no items.";
  for (const record of payload.items) {
    if (!isObj(record) || !txt(record.bundle_id)) return "The gateway listed a workflow without a bundle id.";
    const bid = txt(record.bundle_id);
    const owner = record.owner;
    if (!isObj(owner) || !["gateway", "user"].includes(String(owner.kind))) {
      return `The gateway did not say who owns ${bid} (owner missing): update the gateway.`;
    }
    if (typeof record.shipped !== "boolean") {
      return `The gateway did not say whether ${bid} ships with it (shipped missing): update the gateway.`;
    }
    for (const entry of Array.isArray(record.entrypoints) ? record.entrypoints : []) {
      if (!isObj(entry)) return `The gateway listed an invalid entrypoint for ${bid}.`;
      const ifaces = Array.isArray(entry.interfaces) ? entry.interfaces.map((i) => String(i).trim()) : [];
      if (!ifaces.includes(iface)) {
        return `The gateway offered ${bid}:${txt(entry.flow_id)}, which does not declare ${iface}: update the gateway.`;
      }
    }
  }
  if (!("default_agent_workflows" in payload)) {
    return "This gateway does not report its default agent workflows (contract D): update the gateway.";
  }
  return "";
}

/** preferences.py workflow_choice_from_value: null/blank = the gateway default. */
export function choiceFromValue(value: unknown): "@default" | { bundle_id: string; flow_id: string; registry_scope: string } {
  let t = txt(value);
  if (!t) return "@default";
  let scope = "private";
  if (t.startsWith("catalog:")) {
    scope = "tenant_catalog";
    t = t.slice("catalog:".length);
  } else if (t.startsWith("private:")) {
    t = t.slice("private:".length);
  }
  const i = t.indexOf(":");
  if (i < 0) return "@default";
  const bundle = t.slice(0, i).split("@")[0].trim();
  const flow = t.slice(i + 1).trim();
  if (!bundle || !flow) return "@default";
  return { bundle_id: bundle, flow_id: flow, registry_scope: scope };
}

/** Numeric-aware version order ("0.0.16" > "0.0.9"). */
function versionKey(v: string): number[] {
  return v.split(/[.\-+]/).map((p) => (/^\d+$/.test(p) ? Number(p) : -1));
}
function newer(a: string, b: string): boolean {
  const x = versionKey(a);
  const y = versionKey(b);
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    const d = (x[i] ?? -1) - (y[i] ?? -1);
    if (d) return d > 0;
  }
  return false;
}

type Option = { bundle_id: string; bundle_version: string; flow_id: string; registry_scope: string; label: string };

function options(payload: Json): Option[] {
  const out: Option[] = [];
  for (const record of payload.items as Json[]) {
    const bid = txt(record.bundle_id);
    const ver = txt(record.bundle_version);
    if (!bid || !ver) continue;
    for (const e of (Array.isArray(record.entrypoints) ? record.entrypoints : []) as Json[]) {
      const fid = txt(e.flow_id);
      if (!fid) continue;
      out.push({ bundle_id: bid, bundle_version: ver, flow_id: fid, registry_scope: txt(record.registry_scope) || "private", label: txt(e.name) || fid });
    }
  }
  return out;
}

function latest(opts: Option[]): Option | undefined {
  let best: Option | undefined;
  for (const o of opts) if (!best || newer(o.bundle_version, best.bundle_version)) best = o;
  return best;
}

/**
 * The start of the next turn, from the two gateway answers. Throws
 * WorkflowUnavailable with the sentence to show; never picks "some other"
 * workflow on its own.
 */
export function selectWorkflow(executable: unknown, accountPreferences: unknown, iface = ASSISTANT_INTERFACE): WorkflowStart {
  const problem = executableContractProblem(executable, iface);
  if (problem) throw new WorkflowUnavailable(problem);
  const payload = executable as Json;
  const prefs = isObj(accountPreferences) ? accountPreferences.preferences : undefined;
  const table = isObj(prefs) ? prefs.default_workflow : undefined;
  if (!isObj(table)) {
    throw new WorkflowUnavailable("This gateway does not keep account preferences (preferences.default_workflow): update the gateway.");
  }
  const choice = choiceFromValue(table[iface]);
  const all = options(payload);

  if (choice === "@default") {
    const defaults = payload.default_agent_workflows;
    const entry = isObj(defaults) ? defaults[iface] : undefined;
    if (isObj(entry)) {
      return { flow_id: "@default", interface: iface, label: txt(entry.name) || txt(entry.bundle_id) || "Gateway default", source: "gateway_default" };
    }
    const builtIn = latest(all.filter((o) => o.bundle_id === MANAGED_BUNDLE_ID));
    if (builtIn) return { ...builtIn, source: "built_in" };
    const missing = payload.default_agent_workflows_unavailable;
    const why = isObj(missing) && isObj(missing[iface]) ? txt((missing[iface] as Json).reason) : "";
    throw new WorkflowUnavailable(
      `No Assistant workflow is available on this gateway${why ? `: ${why}` : ""}. Open the desktop Assistant once, or ask the gateway's admin to install it: this page never installs workflows.`,
    );
  }
  const matches = all.filter((o) => o.bundle_id === choice.bundle_id && o.flow_id === choice.flow_id);
  const chosen = latest(matches);
  if (!chosen) {
    throw new WorkflowUnavailable(
      `The workflow chosen for your account (${choice.bundle_id}:${choice.flow_id}) is not available on this gateway any more. Choose another in the Assistant's settings.`,
    );
  }
  return { ...chosen, source: "account_choice" };
}

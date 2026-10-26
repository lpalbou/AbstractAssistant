import { describe, expect, it } from "vitest";

import { ASSISTANT_INTERFACE, choiceFromValue, executableContractProblem, selectWorkflow, WorkflowUnavailable } from "./workflow_selection";

const entry = (flow_id: string) => ({ flow_id, name: "AbstractAssistant Orchestrator", interfaces: [ASSISTANT_INTERFACE] });
const record = (bundle_id: string, bundle_version: string, flow = "c53b1579") => ({
  bundle_id,
  bundle_version,
  registry_scope: "private",
  owner: { kind: "gateway" },
  shipped: false,
  entrypoints: [entry(flow)],
});
// The shape the local gateway answered on 2026-10-26 (untracked/apple-web-wave/w3-web-architecture.md).
const executable = (items: unknown[], defaults: Record<string, unknown> = {}, unavailable: Record<string, unknown> = {}) => ({
  executable_for: ASSISTANT_INTERFACE,
  items,
  default_agent_workflows: defaults,
  default_agent_workflows_unavailable: unavailable,
});
const prefs = (value: string | null) => ({ preferences: { default_workflow: { [ASSISTANT_INTERFACE]: value } } });

describe("selectWorkflow (desktop controller.current_workflow)", () => {
  it("uses @default + interface when the gateway reports a default", () => {
    const sel = selectWorkflow(
      executable([record("abstractassistant-orchestrator", "0.0.16")], { [ASSISTANT_INTERFACE]: { bundle_id: "abstractassistant-orchestrator", name: "AbstractAssistant Orchestrator" } }),
      prefs(null),
    );
    expect(sel).toEqual({ flow_id: "@default", interface: ASSISTANT_INTERFACE, label: "AbstractAssistant Orchestrator", source: "gateway_default" });
  });

  it("falls back to the newest managed orchestrator when no default is reported", () => {
    const sel = selectWorkflow(executable([record("abstractassistant-orchestrator", "0.0.9"), record("abstractassistant-orchestrator", "0.0.16")]), prefs(null));
    expect(sel).toMatchObject({ bundle_id: "abstractassistant-orchestrator", bundle_version: "0.0.16", flow_id: "c53b1579", source: "built_in" });
  });

  it("fails loudly, with the gateway's reason, when nothing runnable is there (never publishes)", () => {
    expect(() => selectWorkflow(executable([], {}, { [ASSISTANT_INTERFACE]: { reason: "no host workflow declares it" } }), prefs(null))).toThrow(
      /No Assistant workflow is available on this gateway: no host workflow declares it/,
    );
  });

  it("runs the account's chosen workflow, latest version; a vanished choice is an error, not a swap", () => {
    const ex = executable([record("my-flow", "1.0.0", "f1"), record("my-flow", "1.2.0", "f1")], { [ASSISTANT_INTERFACE]: { name: "x" } });
    expect(selectWorkflow(ex, prefs("my-flow:f1"))).toMatchObject({ bundle_id: "my-flow", bundle_version: "1.2.0", source: "account_choice" });
    expect(() => selectWorkflow(ex, prefs("gone:f9"))).toThrow(WorkflowUnavailable);
  });

  it("refuses a gateway that ignored executable_for or lacks contract D / account preferences", () => {
    expect(executableContractProblem({ items: [] }, ASSISTANT_INTERFACE)).toMatch(/does not filter workflows/);
    expect(executableContractProblem({ executable_for: ASSISTANT_INTERFACE, items: [] }, ASSISTANT_INTERFACE)).toMatch(/contract D/);
    expect(() => selectWorkflow(executable([]), {})).toThrow(/account preferences/);
    const wrongIface = executable([{ ...record("b", "1"), entrypoints: [{ flow_id: "f", interfaces: ["abstractcode.agent.v1"] }] }]);
    expect(executableContractProblem(wrongIface, ASSISTANT_INTERFACE)).toMatch(/does not declare/);
  });

  it("reads preference values as the desktop does (preferences.py workflow_choice_from_value)", () => {
    expect(choiceFromValue(null)).toBe("@default");
    expect(choiceFromValue("catalog:b@1.0:f")).toEqual({ bundle_id: "b", flow_id: "f", registry_scope: "tenant_catalog" });
    expect(choiceFromValue("private:b:f")).toEqual({ bundle_id: "b", flow_id: "f", registry_scope: "private" });
    expect(choiceFromValue("nonsense")).toBe("@default");
  });
});

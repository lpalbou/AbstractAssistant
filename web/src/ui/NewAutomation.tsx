import {
  AfSwitch,
  AutomationWorkflowPicker,
  ToolModeEditor,
  inheritedToolModes,
  gatewayApiPath,
  planRunTools,
  prepareAutomationTarget,
  type AutomationSummary,
  type AutomationTarget,
  type AutomationWorkflowPickerOptions,
  type ToolCatalogItem,
  type ToolModeLayer,
} from "@abstractframework/ui-kit";
import { useEffect, useMemo, useState } from "react";

import type { GatewayClient } from "../gateway/client";
import { AUTOMATION_INTERFACE, EVERY_PRESETS, clockOf, everyLabel, newAutomationBody, tokensOf, type JsonObject, type NewAutomationWhen } from "../lib/automations";
import { automationErrorText, type Automations } from "./useAutomations";

const DAILY = "daily";

/** The kit's workflow request over this app's gateway fetch: the JSON body, or the reason it failed. */
export function workflowRequest(client: GatewayClient): NonNullable<AutomationWorkflowPickerOptions["request"]> {
  return async (path, init) => {
    const resp = await client.fetchGateway(gatewayApiPath(path), { signal: init.signal, headers: { Accept: "application/json" } });
    if (!resp.ok) throw new Error(`The gateway answered ${resp.status} for the workflows.`);
    return resp.json();
  };
}

/**
 * A new automation, as the watch creates one: the task, the workflow that runs it (the gateway's
 * default first, then the others it offers this account), when it runs (the shared intervals, or
 * every day at a time), the tools its runs may use (each Off, Ask or Auto, from the gateway's
 * defaults: the watch's Tools page for "This automation") and whether each run builds on the
 * earlier ones. Create opens its page.
 */
export function NewAutomation(props: { client: GatewayClient; automations: Automations; onCreated: (s: AutomationSummary) => void; onCancel: () => void }) {
  const { api, refresh } = props.automations;
  const [task, setTask] = useState("");
  const [target, setTarget] = useState<AutomationTarget>({ flow_id: "@default", interface: AUTOMATION_INTERFACE });
  const [choice, setChoice] = useState("24h");
  const [dailyAt, setDailyAt] = useState("08:00");
  const [remembers, setRemembers] = useState(false);
  const [tokensText, setTokensText] = useState("");
  const [defaultTokens, setDefaultTokens] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [catalog, setCatalog] = useState<ToolCatalogItem[] | null>(null);
  const [toolsError, setToolsError] = useState("");
  const [draftTools, setDraftTools] = useState<ToolModeLayer>({});
  const [toolsOpen, setToolsOpen] = useState(false);
  const readCatalog = props.automations.catalog;
  useEffect(() => {
    let cancelled = false;
    readCatalog().then((c) => !cancelled && setCatalog(c), (e) => !cancelled && setToolsError(automationErrorText(e)));
    return () => {
      cancelled = true;
    };
  }, [readCatalog]);
  const options = useMemo<AutomationWorkflowPickerOptions>(() => ({ interfaceId: AUTOMATION_INTERFACE, request: workflowRequest(props.client) }), [props.client]);

  // The gateway's default memory, shown until a number is typed.
  useEffect(() => {
    let cancelled = false;
    props.client.fetchGateway(gatewayApiPath("automations/defaults"), { headers: { Accept: "application/json" } })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        const n = (d as { growing_max_tokens?: unknown } | null)?.growing_max_tokens;
        if (!cancelled && typeof n === "number" && n > 0) setDefaultTokens(n);
      }, () => undefined);
    return () => {
      cancelled = true;
    };
  }, [props.client]);

  const tokens = tokensOf(tokensText);
  const tokensProblem = remembers && tokensText.trim() !== "" && tokens === null ? "Numbers only, more than 0." : "";
  const at = clockOf(dailyAt);
  const when: NewAutomationWhen | null = choice === DAILY ? (at ? { kind: "daily", at } : null) : { kind: "every", every: choice };
  // Without its tools it is not created (the workflow's own and the gateway's grant would ignore
  // what was turned off), as on the watch.
  const ready = task.trim() !== "" && when !== null && !tokensProblem && !creating && catalog !== null;

  const create = async () => {
    if (!when) return;
    setCreating(true);
    setError("");
    try {
      const text = task.trim();
      let workflow: { bundle_ref: string; flow_id: string; input_data: JsonObject } | null = null;
      if ("bundle_ref" in target) {
        const prepared = await prepareAutomationTarget({ ...target, input_data: { ...(target.input_data || {}), prompt: text } }, options);
        workflow = { bundle_ref: (prepared as { bundle_ref: string }).bundle_ref, flow_id: prepared.flow_id, input_data: (prepared.input_data || {}) as JsonObject };
      }
      const tools = planRunTools(catalog ?? [], { session: draftTools });
      const body = newAutomationBody({ requestId: crypto.randomUUID(), task: text, workflow, when, buildsOnEarlierRuns: remembers, growingMaxTokens: remembers ? tokens : null, tools });
      const created = await api.createAutomation(body as unknown as Parameters<typeof api.createAutomation>[0]);
      await refresh();
      props.onCreated(created.summary);
    } catch (e) {
      setError(automationErrorText(e));
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="aa-form-page" data-page="new-automation">
      <form className="aa-form" onSubmit={(e) => { e.preventDefault(); if (ready) void create(); }}>
        <h1>New automation</h1>
        <label className="aa-field"><span>Task</span>
          <textarea rows={5} value={task} placeholder="What should it do?" onChange={(e) => setTask(e.target.value)} autoFocus />
        </label>
        <AutomationWorkflowPicker target={target} options={options} onChange={setTarget} />
        {catalog ? (
          <ToolModeEditor catalog={catalog} layer="session" value={draftTools} inherited={inheritedToolModes(catalog, {}, "session")}
            onChange={setDraftTools} onReset={() => setDraftTools({})} rowLabel="Tools" open={toolsOpen} onToggle={() => setToolsOpen((o) => !o)}
            note="It runs on its own: a tool on Ask waits for you." />
        ) : (
          <p className={`aa-note${toolsError ? " aa-note--error" : ""}`} role={toolsError ? "alert" : "status"}>
            {toolsError ? `Couldn't load your tools. ${toolsError}` : "Loading tools…"}
          </p>
        )}
        <label className="aa-field"><span>When</span>
          <select value={choice} onChange={(e) => setChoice(e.target.value)}>
            {EVERY_PRESETS.map((e) => <option key={e} value={e}>{everyLabel(e)}</option>)}
            <option value={DAILY}>Every day at a time</option>
          </select>
        </label>
        {choice === DAILY && (
          <label className="aa-field"><span>Every day at</span>
            <input type="time" value={dailyAt} onChange={(e) => setDailyAt(e.target.value)} aria-invalid={!at} />
          </label>
        )}
        <fieldset className="aa-fieldset"><legend>Memory</legend>
          <AfSwitch variant="row" label="Builds on earlier runs" checked={remembers} onChange={setRemembers} action="remembers" />
          {remembers && (
            <label className="aa-field"><span>Reads up to (tokens of its earlier runs)</span>
              <input inputMode="numeric" value={tokensText} placeholder={defaultTokens ? defaultTokens.toLocaleString() : "The gateway's default"}
                onChange={(e) => setTokensText(e.target.value)} aria-invalid={Boolean(tokensProblem)} />
              {tokensProblem ? <small className="aa-field__problem">{tokensProblem}</small> : null}
            </label>
          )}
        </fieldset>
        {error ? <p className="aa-note aa-note--error" role="alert">{error}</p> : null}
        <div className="aa-form__actions">
          <button type="button" className="aa-button" onClick={props.onCancel}>Cancel</button>
          <button type="submit" className="aa-button aa-button--primary" disabled={!ready}>{creating ? "Creating…" : "Create"}</button>
        </div>
      </form>
    </div>
  );
}

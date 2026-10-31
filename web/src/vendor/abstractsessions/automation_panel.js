// dist/automations/AutomationPanel.js
import { jsx as _jsx12, jsxs as _jsxs11, Fragment as _Fragment3 } from "react/jsx-runtime";

// dist/tool_call_words_view.js
import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";

// dist/tool_call_words.js
var REGIONS = {
  "us-en": "US English",
  "uk-en": "UK English",
  "wt-wt": "any region",
  "fr-fr": "French (France)",
  "de-de": "German (Germany)",
  "es-es": "Spanish (Spain)",
  "it-it": "Italian (Italy)",
  "ca-en": "Canadian English",
  "au-en": "Australian English",
  "in-en": "Indian English"
};
var TIME_RANGES = { d: "past day", w: "past week", m: "past month", y: "past year" };
function str(v) {
  return typeof v === "string" ? v.trim() : typeof v === "number" || typeof v === "boolean" ? String(v) : "";
}
function prettyQuotes(text2) {
  let open = true;
  return text2.replace(/"/g, () => {
    const q = open ? "\u201C" : "\u201D";
    open = !open;
    return q;
  });
}
function shortUrl(raw) {
  const text2 = str(raw);
  let host = "";
  let path = "";
  try {
    const u = new URL(text2);
    host = u.host.replace(/^www\./, "");
    path = u.pathname.replace(/\/+$/, "");
  } catch {
    return text2;
  }
  const parts = path.split("/").filter(Boolean);
  if (parts.length <= 2)
    return parts.length ? `${host}/${parts.join("/")}` : host;
  return `${host}/${parts[0]}/\u2026/${parts[parts.length - 1]}`;
}
function readableKey(key) {
  const words = key.replace(/[_-]+/g, " ").trim();
  return words ? words[0].toUpperCase() + words.slice(1) : key;
}
function readableValue(v) {
  if (v === true)
    return "yes";
  if (v === false)
    return "no";
  if (v === null || v === void 0)
    return "none";
  if (Array.isArray(v))
    return v.map(readableValue).join(", ");
  if (typeof v === "object") {
    return Object.entries(v).map(([k, x]) => `${readableKey(k).toLowerCase()} ${readableValue(x)}`).join(", ");
  }
  return String(v);
}
function searchDetails(a) {
  const out = [];
  const n = a.num_results ?? a.max_results ?? a.limit;
  if (typeof n === "number")
    out.push(`${n} ${n === 1 ? "result" : "results"}`);
  const region = str(a.region).toLowerCase();
  if (region)
    out.push(REGIONS[region] ?? region);
  const range = str(a.time_range).toLowerCase();
  if (range)
    out.push(TIME_RANGES[range] ?? range);
  const safe = str(a.safe_search).toLowerCase();
  if (safe)
    out.push(safe === "off" ? "safe search off" : `${safe} safe search`);
  return out;
}
function pageDetails(a) {
  const out = [];
  if (a.include_full_content === false)
    out.push("summary only");
  if (a.include_full_content === true)
    out.push("full content");
  if (a.keep_links === false)
    out.push("without links");
  if (a.keep_links === true)
    out.push("with links");
  return out;
}
var TEMPLATES = {
  fetch_url: { verb: "Fetch", lead: "the page", key: (a) => shortUrl(str(a.url)), details: pageDetails, noun: ["page fetch", "page fetches"] },
  skim_url: { verb: "Skim", lead: "the page", key: (a) => shortUrl(str(a.url)), details: pageDetails, noun: ["page skim", "page skims"] },
  web_search: { verb: "Search", lead: "the web for", key: (a) => prettyQuotes(str(a.query)), details: searchDetails, noun: ["web search", "web searches"] },
  skim_websearch: { verb: "Search", lead: "the web for", key: (a) => prettyQuotes(str(a.query)), details: searchDetails, noun: ["web search", "web searches"] },
  read_file: { verb: "Read", lead: "the file", key: (a) => str(a.file_path ?? a.path), details: () => [], noun: ["file read", "file reads"] },
  write_file: { verb: "Write", lead: "the file", key: (a) => str(a.file_path ?? a.path), details: () => [], noun: ["file write", "file writes"] },
  edit_file: { verb: "Edit", lead: "the file", key: (a) => str(a.file_path ?? a.path), details: () => [], noun: ["file edit", "file edits"] },
  list_files: { verb: "List", lead: "the folder", key: (a) => str(a.directory_path ?? a.path) || "the workspace", details: () => [], noun: ["folder listing", "folder listings"] },
  execute_command: { verb: "Run", lead: "the command", key: (a) => str(a.command), details: () => [], noun: ["command", "commands"] },
  send_email: { verb: "Email", lead: "", key: (a) => readableValue(a.to), details: (a) => str(a.subject) ? [`subject \u201C${str(a.subject)}\u201D`] : [], noun: ["email", "emails"] },
  browser_probe: { verb: "Check", lead: "the page renders", key: (a) => shortUrl(str(a.target)) || str(a.target), details: () => [], noun: ["page check", "page checks"] }
};
function describeToolCall(call) {
  const name = str(call.name) || "tool";
  const args = call.arguments && typeof call.arguments === "object" ? call.arguments : {};
  const t = TEMPLATES[name];
  if (!t) {
    const fallback = Object.entries(args).map(([k, v]) => ({ label: readableKey(k), value: readableValue(v) }));
    const verb = readableKey(name.includes("::") ? name.split("::").pop() || name : name);
    return { verb, lead: "", key: "", details: [], sentence: verb, fallback, noun: [verb.toLowerCase(), `${verb.toLowerCase()} calls`] };
  }
  const key = t.key(args);
  const details = t.details(args);
  const head = [t.verb, t.lead, key].filter(Boolean).join(" ");
  return { verb: t.verb, lead: t.lead, key, details, sentence: details.length ? `${head} (${details.join(", ")})` : head, fallback: null, noun: t.noun };
}

// dist/tool_call_words_view.js
function toolCallLine(call) {
  const w = describeToolCall(call);
  if (w.fallback)
    return w.fallback.length ? w.fallback.map((f) => `${f.label}: ${f.value}`).join(" \xB7 ") : "no arguments";
  const head = [w.lead, w.key].filter(Boolean).join(" ");
  return w.details.length ? `${head} (${w.details.join(", ")})` : head;
}
function ToolCallWordsList(props) {
  const calls = props.calls || [];
  return _jsxs("div", { className: `af-toolwords${props.className ? ` ${props.className}` : ""}`, children: [props.heading ? _jsx("p", { className: "af-toolwords__heading", id: props.headingId, children: _jsx("strong", { children: props.heading }) }) : null, _jsx("ul", { className: "af-toolwords__list", "aria-label": props.label ?? "Tool calls", children: calls.map((call, i) => {
    const w = describeToolCall(call);
    const line = toolCallLine(call);
    return _jsxs("li", { className: "af-toolwords__call", "data-tool": call.name, title: `${w.verb} ${line}`, children: [_jsx("span", { className: "af-toolwords__verb", title: call.name, children: w.verb }), " ", _jsx("span", { className: "af-toolwords__text", children: line })] }, `${call.name}:${i}`);
  }) })] });
}

// dist/automations/automation_tools_picker.js
import { jsx as _jsx3, jsxs as _jsxs3 } from "react/jsx-runtime";

// dist/multi_select.js
import { jsxs as _jsxs2, jsx as _jsx2 } from "react/jsx-runtime";
import { useMemo, useState } from "react";
function uniq_sorted(arr) {
  const out = Array.from(new Set(arr.map((x) => String(x || "").trim()).filter(Boolean)));
  out.sort((a, b) => a.localeCompare(b));
  return out;
}
function MultiSelect(props) {
  const disabled = props.disabled === true;
  const options = useMemo(() => uniq_sorted([...props.options || [], ...props.value || []]), [props.options, props.value]);
  const value = useMemo(() => uniq_sorted(props.value || []), [props.value]);
  const [open, set_open] = useState(false);
  const [query, set_query] = useState("");
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q)
      return options;
    return options.filter((x) => x.toLowerCase().includes(q));
  }, [options, query]);
  const selected = useMemo(() => new Set(value), [value]);
  const max_h = typeof props.max_list_height_px === "number" ? props.max_list_height_px : 220;
  return _jsxs2("div", { className: "af_multi_select", children: [_jsxs2("div", { className: "af_multi_select_row", children: [_jsxs2("button", { className: "btn", type: "button", onClick: () => set_open((v) => !v), disabled: disabled || !options.length, "aria-expanded": open, children: [open ? "Hide" : "Select", " \u2022 ", value.length > 0 ? `${value.length} of ${options.length}` : props.placeholder || "(none)"] }), _jsx2("button", { className: "btn", type: "button", onClick: () => props.onChange(options.slice()), disabled: disabled || !options.length || value.length === options.length, title: "Select all", children: "All" }), _jsx2("button", { className: "btn", type: "button", onClick: () => props.onChange([]), disabled: disabled || value.length === 0, title: "Clear selection", children: "Clear" })] }), value.length > 0 ? _jsx2("div", { className: "af_multi_select_chips", children: value.map((v) => _jsxs2("button", { type: "button", disabled, "aria-label": `Remove ${v}`, className: "af_multi_select_chip", title: v, onClick: () => {
    if (disabled)
      return;
    const next = new Set(selected);
    next.delete(v);
    props.onChange(Array.from(next.values()));
  }, children: [v, !disabled ? _jsx2("span", { className: "af_multi_select_chip_x", children: "\xD7" }) : null] }, v)) }) : null, open ? _jsxs2("div", { className: "af_multi_select_panel", children: [_jsx2("input", { className: "mono", value: query, onChange: (e) => set_query(String(e.target.value || "")), placeholder: "filter\u2026", "aria-label": "Filter options", disabled }), _jsxs2("div", { className: "af_multi_select_list", style: { maxHeight: `${max_h}px` }, children: [filtered.map((opt) => {
    const checked = selected.has(opt);
    return _jsxs2("label", { className: `af_multi_select_item mono ${checked ? "checked" : ""}`, children: [_jsx2("input", { type: "checkbox", checked, disabled, onChange: (e) => {
      const next = new Set(selected);
      if (e.target.checked)
        next.add(opt);
      else
        next.delete(opt);
      props.onChange(Array.from(next.values()));
    } }), _jsx2("span", { children: opt })] }, opt);
  }), !filtered.length ? _jsx2("div", { className: "mono muted", children: "(no matches)" }) : null] })] }) : null] });
}

// dist/automations/automation_tools_picker.js
function AutomationToolsPicker(props) {
  return _jsxs3("div", { className: "af-auto__field", "data-field": "tool-selection", children: [_jsxs3("label", { children: [_jsx3("input", { type: "checkbox", checked: props.value === null, disabled: props.disabled, onChange: (e) => props.onChange(e.target.checked ? null : []) }), " Use the flow's default tools"] }), props.value !== null ? _jsx3(MultiSelect, { options: props.availableTools, value: props.value, disabled: props.disabled, placeholder: "No tools enabled", onChange: props.onChange }) : null, _jsx3("p", { className: "af-auto__hint", children: "Choose which tools this automation can use. An empty selection disables tools. Gateway restrictions always apply." })] });
}

// dist/automations/automation_workflow_picker.js
import { jsx as _jsx5, jsxs as _jsxs5 } from "react/jsx-runtime";

// dist/workflow_picker.js
import { jsx as _jsx4, jsxs as _jsxs4 } from "react/jsx-runtime";
import { useCallback, useEffect, useId, useMemo as useMemo2, useRef, useState as useState2 } from "react";

// dist/gateway_paths.js
var GATEWAY_API_PATH = "api/gateway";
function gatewayApiPath(route) {
  const r = String(route || "");
  if (r.startsWith("/"))
    throw new Error(`gatewayApiPath takes a route relative to the gateway API, got ${JSON.stringify(r)}.`);
  return r ? `${GATEWAY_API_PATH}/${r}` : GATEWAY_API_PATH;
}
function joinBaseUrl(baseUrl, path) {
  const p = String(path || "");
  if (p.startsWith("/"))
    throw new Error(`joinBaseUrl takes a relative path, got ${JSON.stringify(p)}.`);
  let b = String(baseUrl ?? "");
  while (b.endsWith("/"))
    b = b.slice(0, -1);
  return b ? `${b}/${p}` : p;
}

// dist/automations/trigger_words.js
var TRIGGER_WORDS_TEXT = {
  manual: "By hand",
  schedule: "On a schedule",
  something: "When something arrives",
  listening: "Listening",
  main_mailbox: "your main mailbox"
};
function connectionKind(sourceId) {
  const s = String(sourceId || "");
  if (s.startsWith("feed"))
    return "feed";
  if (s.startsWith("webhook"))
    return "webhook";
  return "other";
}
function connectionSentence(label, sourceId) {
  const kind = connectionKind(sourceId);
  if (kind === "feed")
    return `When ${label} has a new item`;
  if (kind === "webhook")
    return `When ${label} is called`;
  return `When ${label} sends something`;
}
function triggerConnectionId(trigger) {
  if (!trigger)
    return "";
  const config = trigger.config ?? {};
  const cid = typeof config.connection_id === "string" ? config.connection_id : typeof trigger.connection_id === "string" ? trigger.connection_id : "";
  return cid.trim();
}
function isEventTrigger(trigger) {
  if (!trigger)
    return false;
  const source = String(trigger.source_id || "");
  if (source === "schedule" || source === "manual" || !source)
    return false;
  return true;
}
function mailboxName(account, mailboxes) {
  const raw = typeof account === "string" ? account.trim() : "";
  const id = !raw || raw === "self" ? "default" : raw;
  const box = (mailboxes ?? []).find((m) => m.account_id === id) ?? (id === "default" ? (mailboxes ?? []).find((m) => m.primary) : void 0);
  if (box?.address)
    return box.address;
  return id === "default" ? TRIGGER_WORDS_TEXT.main_mailbox : id;
}
function connectionOf(trigger, connections) {
  const cid = triggerConnectionId(trigger);
  if (!cid)
    return null;
  return (connections ?? []).find((c) => c.connection_id === cid) ?? null;
}
function triggerSourceName(trigger, connections, mailboxes) {
  if (!trigger || !isEventTrigger(trigger))
    return "";
  const source = String(trigger.source_id || "");
  if (source.startsWith("email"))
    return mailboxName(trigger.config?.account, mailboxes);
  const conn = connectionOf(trigger, connections);
  if (conn?.label)
    return conn.label;
  const kind = connectionKind(source);
  return kind === "feed" ? "A feed" : kind === "webhook" ? "A webhook" : "A connection";
}
function triggerWords(trigger, connections, mailboxes, served) {
  const servedText = typeof served?.trigger_text === "string" ? served.trigger_text.trim() : "";
  if (servedText)
    return servedText;
  if (!trigger)
    return "";
  const source = String(trigger.source_id || "");
  if (source === "schedule") {
    const text2 = served?.schedule_rule_text;
    return typeof text2 === "string" && text2.trim() ? text2.trim() : TRIGGER_WORDS_TEXT.schedule;
  }
  if (source === "manual")
    return TRIGGER_WORDS_TEXT.manual;
  if (source.startsWith("email"))
    return `When mail arrives in ${mailboxName(trigger.config?.account, mailboxes)}`;
  const cid = triggerConnectionId(trigger);
  if (cid) {
    const conn = connectionOf(trigger, connections);
    const kind = connectionKind(source);
    const label = conn?.label || (kind === "feed" ? "a feed" : kind === "webhook" ? "a webhook" : "a connection");
    return connectionSentence(label, source);
  }
  return TRIGGER_WORDS_TEXT.something;
}
var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function zoned(ms, timeZone) {
  const d = new Date(ms);
  const day = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
  const clock = new Intl.DateTimeFormat("en-GB", { timeZone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(d);
  const [, mm, dd] = day.split("-");
  const label = `${Number(dd)} ${MONTHS[Number(mm) - 1] ?? mm}`;
  return { day, clock, label };
}
function validZone(timeZone) {
  const z = typeof timeZone === "string" ? timeZone.trim() : "";
  if (!z)
    return null;
  try {
    new Intl.DateTimeFormat("en-GB", { timeZone: z });
    return z;
  } catch {
    return null;
  }
}
function whenWords(iso, opts = {}) {
  if (!iso)
    return "";
  const t = Date.parse(iso);
  if (Number.isNaN(t))
    return "";
  const zone = validZone(opts.timeZone);
  const tz = zone ?? "UTC";
  const suffix = zone ? "" : " UTC";
  const now = opts.nowMs ?? Date.now();
  const at = zoned(t, tz);
  const today = zoned(now, tz).day;
  const yesterday = zoned(now - 864e5, tz).day;
  if (at.day === today)
    return `${opts.style === "day" ? "today " : ""}${at.clock}${suffix}`;
  if (at.day === yesterday)
    return `yesterday ${at.clock}${suffix}`;
  return `${at.label} ${at.clock}${suffix}`;
}
function str2(v) {
  return typeof v === "string" ? v.trim() : "";
}
function quoted(s) {
  return s ? `: \u201C${s}\u201D` : "";
}
function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many}`;
}
function occurrenceEventCard(event, ctx = {}) {
  if (!event || typeof event !== "object" || Array.isArray(event))
    return null;
  const e = event;
  const type = str2(e.type);
  const m = /^abstract\.(.+)\.v(\d+)$/.exec(type);
  const source_id = m ? m[1] : "";
  if (!source_id || source_id === "schedule" || source_id === "manual")
    return null;
  const data = e.data && typeof e.data === "object" && !Array.isArray(e.data) ? e.data : {};
  const at = whenWords(str2(e.time), { timeZone: ctx.timeZone, nowMs: ctx.nowMs });
  let source = "";
  let what = "";
  if (source_id.startsWith("email")) {
    const messages = Array.isArray(data.messages) ? data.messages : [];
    const n = typeof data.count === "number" ? data.count : messages.length;
    if (!n)
      return null;
    source = mailboxName(ctx.trigger?.config?.account, ctx.mailboxes);
    what = `${plural(n, "new message", "new messages")}${quoted(str2(messages[0]?.subject))}`;
  } else {
    const events = Array.isArray(data.events) ? data.events : [];
    const n = typeof data.count === "number" ? data.count : events.length;
    if (!n)
      return null;
    const first = events[0] && typeof events[0] === "object" ? events[0] : {};
    const firstData = first.data && typeof first.data === "object" && !Array.isArray(first.data) ? first.data : {};
    const cid = str2(data.connection_id) || str2(e.connectionid);
    const binding = { source_id, config: { connection_id: cid } };
    const conn = connectionOf(cid ? binding : ctx.trigger, ctx.connections);
    const kind = connectionKind(source_id);
    source = conn?.label || triggerSourceName(cid ? binding : ctx.trigger ?? binding, ctx.connections, ctx.mailboxes);
    const isTest = (ev) => !!ev && typeof ev === "object" && ev.data?.test === true;
    if (events.length && events.every(isTest))
      what = n === 1 ? "Test event" : `${n} test events`;
    else if (kind === "webhook")
      what = `${plural(n, "call", "calls")}${quoted(str2(first.subject))}`;
    else if (kind === "feed")
      what = `${plural(n, "new item", "new items")}${quoted(str2(firstData.title) || str2(first.subject))}`;
    else
      what = `${plural(n, "new event", "new events")}${quoted(str2(first.subject))}`;
  }
  return { source, what, at, text: [source, what, at].filter(Boolean).join(" \xB7 ") };
}

// dist/workflow_picker_core.js
var WORKFLOW_PICKER_DEFAULT = "@default";
var WORKFLOW_PICKER_EMPTY = "No workflows available for this app \u2014 ask your admin.";
var WORKFLOW_PICKER_GROUP_LABELS = {
  shared: "Shared",
  mine: "Mine"
};
var WorkflowPickerContractError = class extends Error {
  constructor(message) {
    super(message);
    this.name = "WorkflowPickerContractError";
  }
};
function executableWorkflowsPath(interfaceId, options = {}) {
  const id = String(interfaceId || "").trim();
  if (!id)
    throw new Error("executableWorkflowsPath needs the interface the app runs (e.g. abstractcode.agent.v1).");
  return `bundles?executable_for=${encodeURIComponent(id)}${options.allVersions ? "&all_versions=true" : ""}`;
}
function allWorkflowsPath(options = {}) {
  return options.allVersions ? "bundles?all_versions=true" : "bundles";
}
function workflowPickerPath(interfaceId, options = {}) {
  return interfaceId === null ? allWorkflowsPath(options) : executableWorkflowsPath(interfaceId, options);
}
function record(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value : void 0;
}
function text(value) {
  return typeof value === "string" ? value.trim() : "";
}
var UPDATE = "update the gateway";
function defaultFrom(body, interfaceId) {
  const defaults = record(body.default_agent_workflows);
  if (!defaults)
    return { status: "unavailable", reason: "the gateway does not report a default workflow" };
  const row = record(defaults[interfaceId]);
  if (!row) {
    const why = text(record(record(body.default_agent_workflows_unavailable)?.[interfaceId])?.reason);
    return { status: "unavailable", reason: why || `no default workflow for ${interfaceId}` };
  }
  const bundleId = text(row.bundle_id);
  const flowId = text(row.flow_id);
  if (!bundleId || !flowId)
    return { status: "unavailable", reason: "the gateway's default workflow is missing its bundle or flow" };
  const bundleVersion = text(row.bundle_version);
  return {
    status: "ok",
    name: text(row.name) || flowId,
    bundleId,
    bundleVersion,
    flowId,
    workflowId: text(row.workflow_id) || `${bundleId}${bundleVersion ? `@${bundleVersion}` : ""}:${flowId}`
  };
}
function parseWorkflowListing(envelope, interfaceId, options = {}) {
  const body = record(envelope);
  if (!body)
    throw new WorkflowPickerContractError("The gateway's workflow list is not a JSON object.");
  const echoed = text(body.executable_for);
  if (interfaceId === null) {
    if (echoed)
      throw new WorkflowPickerContractError(`Asked for every workflow, the gateway listed only ${echoed}.`);
  } else if (echoed !== interfaceId)
    throw new WorkflowPickerContractError(echoed ? `The gateway listed workflows for ${echoed}, not ${interfaceId}.` : `This gateway does not filter workflows per app (no executable_for in its answer): ${UPDATE}.`);
  if (!Array.isArray(body.items))
    throw new WorkflowPickerContractError("The gateway's workflow list has no items.");
  const entries = [];
  for (const raw of body.items) {
    const item = record(raw);
    const bundleId = text(item?.bundle_id);
    if (!item || !bundleId)
      throw new WorkflowPickerContractError("The gateway listed a workflow without a bundle id.");
    const owner = record(item.owner);
    const kind = text(owner?.kind);
    if (kind !== "gateway" && kind !== "user")
      throw new WorkflowPickerContractError(`The gateway did not say who owns ${bundleId} (owner missing): ${UPDATE}.`);
    if (typeof item.shipped !== "boolean")
      throw new WorkflowPickerContractError(`The gateway did not say whether ${bundleId} ships with it (shipped missing): ${UPDATE}.`);
    const bundleVersion = text(item.bundle_version);
    const entrypoints = Array.isArray(item.entrypoints) ? item.entrypoints : [];
    for (const rawEp of entrypoints) {
      const ep = record(rawEp);
      const flowId = text(ep?.flow_id);
      if (!ep || !flowId)
        continue;
      const interfaces = Array.isArray(ep.interfaces) ? ep.interfaces.map(text).filter(Boolean) : [];
      const automationTrigger = triggerOf(record(item.automation_defaults)?.[flowId]);
      const triggerable = ep.triggerable === true || !!automationTrigger;
      if (interfaceId === null) {
        if (!interfaces.length && !triggerable)
          continue;
      } else if (!interfaces.includes(interfaceId))
        throw new WorkflowPickerContractError(`The gateway offered ${bundleId}:${flowId}, which does not declare ${interfaceId}: ${UPDATE}.`);
      entries.push({
        value: text(ep.workflow_id) || `${bundleId}${bundleVersion ? `@${bundleVersion}` : ""}:${flowId}`,
        bundleId,
        bundleVersion,
        flowId,
        name: text(ep.name) || text(record(item.metadata)?.name) || bundleId,
        description: text(ep.description) || text(item.description),
        registryScope: text(item.registry_scope) || "private",
        group: kind === "user" ? "mine" : "shared",
        shipped: item.shipped,
        interfaces,
        ...interfaceId === null ? { showInterfaces: true } : {},
        ...automationTrigger ? { automationTrigger } : {},
        ...triggerable ? { triggerable: true } : {}
      });
    }
  }
  const defaultInterface = options.defaultInterface ?? interfaceId;
  return {
    interfaceId,
    entries,
    gatewayDefault: defaultInterface ? defaultFrom(body, defaultInterface) : { status: "unavailable", reason: "no interface named for the gateway default" }
  };
}
function workflowPickerGroups(entries) {
  const order = (a, b) => a.name.localeCompare(b.name) || b.bundleVersion.localeCompare(a.bundleVersion, void 0, { numeric: true }) || a.value.localeCompare(b.value);
  return ["shared", "mine"].map((id) => ({ id, label: WORKFLOW_PICKER_GROUP_LABELS[id], entries: entries.filter((e) => e.group === id).sort(order) })).filter((g) => g.entries.length > 0);
}
var WORKFLOW_INTERFACE_LABELS = {
  "abstractcode.agent.v1": "Code agent",
  "abstractassistant.agent.v1": "Assistant",
  "abstractcode.coding.v1": "Coding",
  tools: "tools",
  event: "event",
  chat: "chat"
};
function workflowInterfaceLabel(interfaceId) {
  return WORKFLOW_INTERFACE_LABELS[interfaceId] ?? interfaceId;
}
function workflowEntryDetail(entry, _all = []) {
  const version = entry.bundleVersion ? `@${entry.bundleVersion}` : "";
  if (!entry.showInterfaces)
    return version;
  if (!entry.interfaces.length && entry.automationTrigger)
    return [triggerWords(entry.automationTrigger), version].filter(Boolean).join(" \xB7 ");
  const labels = [...new Set(entry.interfaces.map(workflowInterfaceLabel))].join(", ");
  return [labels, version].filter(Boolean).join(" \xB7 ");
}
function triggerOf(raw) {
  const t = record(record(raw)?.trigger);
  const source_id = text(t?.source_id);
  if (!t || !source_id || typeof t.source_version !== "number")
    return void 0;
  const config = record(t.config) ?? {};
  const cid = text(t.connection_id);
  return { source_id, source_version: t.source_version, config, ...cid ? { connection_id: cid } : {} };
}
function workflowEntryTitle(entry) {
  return entry.value;
}
function gatewayDefaultDetail(state) {
  if (!state)
    return "";
  if (state.status === "unavailable")
    return state.reason;
  return `${state.name}${state.bundleVersion ? ` @${state.bundleVersion}` : ""}`;
}
function workflowPickerNextIndex(key, current, count) {
  if (count <= 0)
    return null;
  if (key === "ArrowDown")
    return current < 0 ? 0 : Math.min(count - 1, current + 1);
  if (key === "ArrowUp")
    return current < 0 ? count - 1 : Math.max(0, current - 1);
  if (key === "Home")
    return 0;
  if (key === "End")
    return count - 1;
  return null;
}
function workflowPickerRows(data, showDefault = true) {
  const entries = data?.entries ?? [];
  const out = [];
  if (showDefault)
    out.push({ key: "default", value: WORKFLOW_PICKER_DEFAULT, name: "Gateway default", detail: gatewayDefaultDetail(data?.gatewayDefault ?? null), group: null, entry: null });
  for (const g of workflowPickerGroups(entries))
    for (const e of g.entries)
      out.push({ key: e.value, value: e.value, name: e.name, detail: workflowEntryDetail(e, entries), title: workflowEntryTitle(e), group: g.id, entry: e });
  return out;
}

// dist/workflow_picker.js
async function defaultRequest(baseUrl, path, signal) {
  const res = await fetch(joinBaseUrl(baseUrl, gatewayApiPath(path)), {
    credentials: "include",
    headers: { Accept: "application/json" },
    signal
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const message = body?.detail?.message || body?.message || (typeof body?.detail === "string" ? body.detail : "");
    throw new Error(message || `The gateway answered ${res.status}.`);
  }
  return body;
}
function errorText(reason) {
  const r = reason;
  return String(r?.detail?.message || r?.message || r || "The workflow list could not be loaded.");
}
function useExecutableWorkflows(options) {
  const { interfaceId, defaultInterface, allVersions = false, enabled = true, gatewayBaseUrl, reloadKey } = options;
  const requestRef = useRef(options.request);
  requestRef.current = options.request;
  const [tick, setTick] = useState2(0);
  const [state, setState] = useState2({ status: "idle", data: null, error: "" });
  useEffect(() => {
    if (!enabled) {
      setState({ status: "idle", data: null, error: "" });
      return;
    }
    const abort = new AbortController();
    setState((s) => ({ ...s, status: "loading", error: "" }));
    const path = workflowPickerPath(interfaceId, { allVersions });
    const run = requestRef.current ? requestRef.current(path, { signal: abort.signal }) : defaultRequest(gatewayBaseUrl, path, abort.signal);
    run.then((body) => {
      if (abort.signal.aborted)
        return;
      setState({ status: "ready", data: parseWorkflowListing(body, interfaceId, { defaultInterface }), error: "" });
    }).catch((reason) => {
      if (abort.signal.aborted)
        return;
      setState({ status: "error", data: null, error: errorText(reason) });
    });
    return () => abort.abort();
  }, [interfaceId, defaultInterface, allVersions, enabled, gatewayBaseUrl, reloadKey, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload };
}
function placement(trigger) {
  if (!trigger || typeof window === "undefined")
    return {};
  const r = trigger.getBoundingClientRect();
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const width = Math.min(Math.max(r.width, 300), 440, vw - 32);
  const left = Math.max(16, Math.min(r.left, vw - 16 - width));
  const below = vh - r.bottom - 16;
  if (below >= 220 || below >= r.top)
    return { position: "fixed", left, width, top: r.bottom + 4, maxHeight: Math.max(160, below) };
  return { position: "fixed", left, width, bottom: vh - r.top + 4, maxHeight: Math.max(160, r.top - 16) };
}
function cx(...parts) {
  return parts.filter(Boolean).join(" ");
}
function WorkflowPicker(props) {
  const own = useExecutableWorkflows({
    interfaceId: props.interfaceId,
    defaultInterface: props.defaultInterface,
    request: props.request,
    gatewayBaseUrl: props.gatewayBaseUrl,
    allVersions: props.allVersions,
    enabled: props.workflows ? false : props.enabled !== false
  });
  const list = props.workflows ?? own;
  const showDefault = props.showDefault !== false && (props.interfaceId !== null || Boolean(props.defaultInterface));
  const baseId = useId().replace(/:/g, "");
  const listId = `${baseId}-list`;
  const [open, setOpen] = useState2(false);
  const [highlight, setHighlight] = useState2(-1);
  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const [place, setPlace] = useState2({});
  const entryDetail = props.entryDetail;
  const rows = useMemo2(() => workflowPickerRows(list.data, showDefault).map((r) => {
    const d = r.entry && entryDetail ? entryDetail(r.entry) : null;
    return d ? { ...r, detail: d } : r;
  }), [list.data, showDefault, entryDetail]);
  const current = rows.find((r) => r.value === props.value);
  const shown = current ? { name: current.name, detail: current.detail } : props.currentLabel ? { name: props.currentLabel.name, detail: props.currentLabel.detail || "" } : list.status === "loading" ? { name: "Loading flows\u2026", detail: "" } : { name: props.value === WORKFLOW_PICKER_DEFAULT ? "Gateway default" : "Choose a flow", detail: "" };
  const reason = String(props.unavailableReason || "").trim();
  const actionable = !reason && list.status === "ready";
  const close = useCallback(() => {
    setOpen(false);
    setHighlight(-1);
  }, []);
  const openList = useCallback(() => {
    if (!actionable)
      return;
    setPlace(placement(triggerRef.current));
    setOpen(true);
    const i = rows.findIndex((r) => r.value === props.value);
    setHighlight(i >= 0 ? i : 0);
  }, [actionable, rows, props.value]);
  const choose = useCallback((row) => {
    close();
    if (row.value !== props.value)
      props.onChange(row.value, row.entry);
    triggerRef.current?.focus();
  }, [close, props]);
  useEffect(() => {
    if (!open)
      return;
    const onDown = (ev) => {
      if (rootRef.current && !rootRef.current.contains(ev.target))
        close();
    };
    const onResize = () => close();
    document.addEventListener("mousedown", onDown);
    document.addEventListener("touchstart", onDown);
    window.addEventListener("resize", onResize);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("touchstart", onDown);
      window.removeEventListener("resize", onResize);
    };
  }, [open, close]);
  useEffect(() => {
    if (!open || highlight < 0)
      return;
    const el = typeof document !== "undefined" ? document.getElementById(`${baseId}-opt-${highlight}`) : null;
    el?.scrollIntoView?.({ block: "nearest" });
  }, [open, highlight, baseId]);
  const onKeyDown = (ev) => {
    if (!open) {
      if (["Enter", " ", "ArrowDown", "ArrowUp"].includes(ev.key)) {
        ev.preventDefault();
        openList();
      }
      return;
    }
    if (ev.key === "Escape") {
      ev.preventDefault();
      close();
      return;
    }
    if (ev.key === "Tab") {
      close();
      return;
    }
    if (ev.key === "Enter" || ev.key === " ") {
      ev.preventDefault();
      if (highlight >= 0 && rows[highlight])
        choose(rows[highlight]);
      return;
    }
    const next = workflowPickerNextIndex(ev.key, highlight, rows.length);
    if (next !== null) {
      ev.preventDefault();
      setHighlight(next);
    }
  };
  return _jsxs4("div", { ref: rootRef, className: cx("af-workflow-picker", props.className), "data-interface": props.interfaceId ?? "any", children: [_jsxs4("button", { ref: triggerRef, id: props.id, type: "button", role: "combobox", className: "af-workflow-picker__trigger", "aria-label": props.ariaLabel || "Workflow", "aria-describedby": `${baseId}-value`, "aria-haspopup": "listbox", "aria-expanded": open, "aria-controls": listId, "aria-activedescendant": open && highlight >= 0 ? `${baseId}-opt-${highlight}` : void 0, "aria-disabled": actionable ? void 0 : true, title: reason || void 0, onClick: () => open ? close() : openList(), onKeyDown, children: [_jsxs4("span", { className: "af-workflow-picker__value", id: `${baseId}-value`, children: [_jsx4("span", { className: "af-workflow-picker__name", children: shown.name }), shown.detail ? _jsx4("span", { className: "af-workflow-picker__detail", children: shown.detail }) : null] }), _jsx4("span", { className: "af-workflow-picker__caret", "aria-hidden": "true" })] }), open ? _jsx4(WorkflowPickerListbox, { id: listId, idBase: baseId, rows, value: props.value, highlight, ariaLabel: props.ariaLabel || "Workflow", style: place, onHighlight: setHighlight, onChoose: choose }) : null, list.status === "error" ? _jsx4("span", { className: "af-workflow-picker__error", role: "alert", children: list.error }) : list.status === "ready" && rows.every((r) => !r.entry) && !showDefault ? _jsx4("span", { className: "af-workflow-picker__empty", role: "status", children: WORKFLOW_PICKER_EMPTY }) : null] });
}
function WorkflowPickerListbox(props) {
  const option = (row, index) => _jsxs4("div", { id: `${props.idBase}-opt-${index}`, role: "option", "aria-selected": row.value === props.value, "data-value": row.value, title: row.title, className: cx("af-workflow-picker__option", index === props.highlight && "af-workflow-picker__option--highlighted", row.value === props.value && "af-workflow-picker__option--selected"), onMouseEnter: () => props.onHighlight(index), onMouseDown: (ev) => ev.preventDefault(), onClick: () => props.onChoose(row), children: [_jsx4("span", { className: "af-workflow-picker__name", children: row.name }), row.detail ? _jsx4("span", { className: "af-workflow-picker__detail", children: row.detail }) : null] }, row.key);
  const indexed = props.rows.map((row, index) => ({ row, index }));
  const defaults = indexed.filter((x) => x.row.group === null);
  const groups = ["shared", "mine"].map((g) => ({ g, items: indexed.filter((x) => x.row.group === g) })).filter((x) => x.items.length > 0);
  return _jsxs4("div", { id: props.id, role: "listbox", "aria-label": props.ariaLabel, className: "af-workflow-picker__list", style: props.style, children: [defaults.map((x) => option(x.row, x.index)), groups.map(({ g, items }) => _jsxs4("div", { role: "group", "aria-labelledby": `${props.idBase}-g-${g}`, "data-group": g, children: [_jsx4("div", { id: `${props.idBase}-g-${g}`, className: "af-workflow-picker__group", role: "presentation", children: WORKFLOW_PICKER_GROUP_LABELS[g] }), items.map((x) => option(x.row, x.index))] }, g)), groups.length === 0 ? _jsx4("p", { className: "af-workflow-picker__empty", children: WORKFLOW_PICKER_EMPTY }) : null] });
}

// dist/automations/target_selection.js
function retargetAutomationInput(input) {
  const keys = ["prompt", "tools", "provider", "model", "temperature", "seed", "max_iterations", "max_in_tokens", "system", "_limits"];
  const out = {};
  for (const key of keys)
    if (key in input)
      out[key] = input[key];
  const runtime = input._runtime;
  if (runtime && typeof runtime === "object") {
    const next = {};
    for (const key of ["allowed_tools", "provider", "model", "thinking", "speculation", "stream"])
      if (key in runtime)
        next[key] = runtime[key];
    if (Object.keys(next).length)
      out._runtime = next;
  }
  return out;
}
function automationTargetValue(target) {
  return target.flow_id === "@default" ? "@default" : `${"bundle_ref" in target ? target.bundle_ref : ""}:${target.flow_id}`;
}

// dist/automations/automation_workflow_picker.js
function AutomationWorkflowPicker(props) {
  const value = automationTargetValue(props.target);
  return _jsxs5("div", { className: "af-auto__field", children: [_jsx5("span", { children: "Flow" }), _jsx5(WorkflowPicker, { ...props.options, ariaLabel: "Automation flow", value, currentLabel: { name: flowNameOf(value, props.options) }, onChange: (next, entry) => props.onChange(next === "@default" ? { flow_id: "@default", interface: props.options.interfaceId || props.options.defaultInterface || "abstractcode.agent.v1" } : { bundle_ref: `${entry.bundleId}@${entry.bundleVersion}`, flow_id: entry.flowId }) })] });
}
function flowNameOf(value, options) {
  const entries = options.workflows?.data?.entries ?? [];
  const exact = entries.find((e) => e.value === value);
  if (exact)
    return exact.name;
  const at = value.indexOf("@");
  const colon = value.lastIndexOf(":");
  const bundle = at > 0 ? value.slice(0, at) : colon > 0 ? value.slice(0, colon) : value;
  const flow = colon > 0 ? value.slice(colon + 1) : "";
  return entries.find((e) => e.bundleId === bundle && (!flow || e.flowId === flow))?.name || bundle || value;
}

// dist/automations/prepare_target.js
async function prepareAutomationTarget(target, options) {
  const entry = target.flow_id === "@default" ? options.workflows?.data?.gatewayDefault : null;
  const ref = "bundle_ref" in target ? target.bundle_ref : entry?.status === "ok" ? `${entry.bundleId}@${entry.bundleVersion}` : "";
  const flow = target.flow_id !== "@default" ? target.flow_id : entry?.status === "ok" ? entry.flowId : "";
  if (!ref || !flow || !options.request)
    throw new Error("Workflow inputs could not be checked. Refresh the workflow list and try again.");
  const at = ref.lastIndexOf("@");
  const bundle = at < 0 ? ref : ref.slice(0, at), version = at < 0 ? "" : ref.slice(at + 1);
  const raw = await options.request(`bundles/${encodeURIComponent(bundle)}/flows/${encodeURIComponent(flow)}/input_schema${version ? `?bundle_version=${encodeURIComponent(version)}` : ""}`, { signal: new AbortController().signal });
  const schema = raw?.input_data_schema || raw;
  if (!schema || typeof schema !== "object" || !schema.properties)
    throw new Error("This workflow does not report its input requirements. Choose another workflow.");
  const input = { ...raw.defaults || {} };
  for (const [key, field] of Object.entries(schema.properties))
    if (field && "default" in field)
      input[key] = field.default;
  Object.assign(input, target.input_data || {});
  const missing = (Array.isArray(schema.required) ? schema.required : []).filter((key) => input[key] === void 0);
  if (missing.length)
    throw new Error(`This workflow needs additional inputs: ${missing.join(", ")}. Configure a new automation from that workflow's input form, or choose a compatible workflow.`);
  return { ...target, input_data: input };
}

// dist/automations/AutomationPanel.js
import React2, { useEffect as useEffect5, useId as useId2, useRef as useRef4, useState as useState4 } from "react";

// dist/visible_content.js
import { jsx as _jsx6 } from "react/jsx-runtime";
import { useEffect as useEffect2, useRef as useRef2 } from "react";
function VisibleContentMarker(p) {
  const ref = useRef2(null), callback = useRef2(p.onConsume);
  callback.current = p.onConsume;
  useEffect2(() => {
    const el = ref.current;
    if (!el || !p.enabled)
      return;
    const notify = callback.current;
    let timer, done = false;
    const visible = () => {
      if (document.hidden || !document.hasFocus() || !el.isConnected)
        return false;
      const b = el.getBoundingClientRect();
      if (b.width <= 0 || b.height <= 0 || b.top < 0 || b.bottom > window.innerHeight)
        return false;
      const hit = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
      return hit === el || Boolean(hit && el.contains(hit));
    };
    const check = () => {
      if (done)
        return;
      clearTimeout(timer);
      if (visible())
        timer = setTimeout(() => {
          if (visible()) {
            done = true;
            notify();
          }
        }, 250);
    };
    const observer = new IntersectionObserver(check, { threshold: 1 });
    observer.observe(el);
    for (const event of ["focus", "blur", "resize", "pointerup", "keyup", "scroll"])
      window.addEventListener(event, check, true);
    document.addEventListener("visibilitychange", check);
    check();
    return () => {
      clearTimeout(timer);
      observer.disconnect();
      for (const event of ["focus", "blur", "resize", "pointerup", "keyup", "scroll"])
        window.removeEventListener(event, check, true);
      document.removeEventListener("visibilitychange", check);
    };
  }, [p.enabled, p.ownerKey, p.contentKey]);
  return _jsx6("span", { ref, "aria-hidden": "true", className: "af-session-read-marker", style: { display: "block", width: "100%", height: 1 } });
}

// dist/icon.js
import { jsx as _jsx7, Fragment as _Fragment, jsxs as _jsxs6 } from "react/jsx-runtime";
var GRID_16 = /* @__PURE__ */ new Set(["board", "inbox", "server", "agent", "playCircle", "list", "gear"]);
function paths(name) {
  switch (name) {
    case "chat":
      return _jsx7("path", { d: "M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" });
    case "plus":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M12 5v14" }), _jsx7("path", { d: "M5 12h14" })] });
    case "history":
      return _jsxs6(_Fragment, { children: [_jsx7("circle", { cx: "12", cy: "12", r: "9" }), _jsx7("path", { d: "M12 7v5l3 3" })] });
    case "refresh":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M21 12a9 9 0 0 0-15.5-6.4L3 8" }), _jsx7("path", { d: "M3 3v5h5" }), _jsx7("path", { d: "M3 12a9 9 0 0 0 15.5 6.4L21 16" }), _jsx7("path", { d: "M21 21v-5h-5" })] });
    case "cog":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" }), _jsx7("circle", { cx: "12", cy: "12", r: "3" })] });
    case "activity":
      return _jsx7("path", { d: "M22 12h-4l-3 9L9 3l-3 9H2" });
    case "settings":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M4 6h16" }), _jsx7("circle", { cx: "8", cy: "6", r: "2" }), _jsx7("path", { d: "M4 12h16" }), _jsx7("circle", { cx: "16", cy: "12", r: "2" }), _jsx7("path", { d: "M4 18h16" }), _jsx7("circle", { cx: "10", cy: "18", r: "2" })] });
    case "user":
      return _jsxs6(_Fragment, { children: [_jsx7("circle", { cx: "12", cy: "8", r: "4" }), _jsx7("path", { d: "M4 21a8 8 0 0 1 16 0" })] });
    case "bot":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M12 2v3" }), _jsx7("rect", { x: "5", y: "6", width: "14", height: "14", rx: "3" }), _jsx7("circle", { cx: "9", cy: "13", r: "1", fill: "currentColor", stroke: "none" }), _jsx7("circle", { cx: "15", cy: "13", r: "1", fill: "currentColor", stroke: "none" }), _jsx7("path", { d: "M9 17h6" })] });
    case "paperclip":
      return _jsx7("path", { d: "M21.44 11.05l-9.19 9.19a5.5 5.5 0 0 1-7.78-7.78l9.19-9.19a3.5 3.5 0 0 1 4.95 4.95l-9.2 9.19a1.5 1.5 0 0 1-2.12-2.12l8.49-8.48" });
    case "mic":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3z" }), _jsx7("path", { d: "M19 11a7 7 0 0 1-14 0" }), _jsx7("path", { d: "M12 18v4" }), _jsx7("path", { d: "M8 22h8" })] });
    case "speaker":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M11 5L6 9H2v6h4l5 4V5z" }), _jsx7("path", { d: "M15.5 8.5a5 5 0 0 1 0 7" }), _jsx7("path", { d: "M18 6a9 9 0 0 1 0 12" })] });
    case "pause":
      return _jsxs6(_Fragment, { children: [_jsx7("rect", { x: "6", y: "4", width: "4", height: "16", rx: "1", fill: "currentColor", stroke: "none" }), _jsx7("rect", { x: "14", y: "4", width: "4", height: "16", rx: "1", fill: "currentColor", stroke: "none" })] });
    case "terminal":
      return _jsxs6(_Fragment, { children: [_jsx7("rect", { x: "3", y: "4", width: "18", height: "16", rx: "2", ry: "2" }), _jsx7("path", { d: "M7 9l3 3-3 3" }), _jsx7("path", { d: "M12 15h5" })] });
    case "edit":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M12 20h9" }), _jsx7("path", { d: "M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" })] });
    case "download":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" }), _jsx7("path", { d: "M7 10l5 5 5-5" }), _jsx7("path", { d: "M12 15V3" })] });
    case "loader":
      return _jsx7("path", { d: "M21 12a9 9 0 1 1-3.3-6.9" });
    case "info":
      return _jsxs6(_Fragment, { children: [_jsx7("circle", { cx: "12", cy: "12", r: "10" }), _jsx7("path", { d: "M12 16v-4" }), _jsx7("circle", { cx: "12", cy: "8", r: "0.75", fill: "currentColor", stroke: "none" })] });
    case "about":
      return _jsxs6(_Fragment, { children: [_jsx7("circle", { cx: "12", cy: "12", r: "9" }), _jsx7("circle", { cx: "12", cy: "7.5", r: "1.5", fill: "currentColor", stroke: "none" }), _jsx7("path", { d: "M12 11v6" })] });
    case "warning":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M12 3l10 18H2L12 3z" }), _jsx7("path", { d: "M12 9v4" }), _jsx7("circle", { cx: "12", cy: "17", r: "0.75", fill: "currentColor", stroke: "none" })] });
    case "error":
      return _jsxs6(_Fragment, { children: [_jsx7("circle", { cx: "12", cy: "12", r: "10" }), _jsx7("path", { d: "M15 9l-6 6" }), _jsx7("path", { d: "M9 9l6 6" })] });
    case "copy":
      return _jsxs6(_Fragment, { children: [_jsx7("rect", { x: "9", y: "9", width: "13", height: "13", rx: "2" }), _jsx7("path", { d: "M5 15V5a2 2 0 0 1 2-2h10" })] });
    case "check":
      return _jsx7("path", { d: "M20 6L9 17l-5-5" });
    case "x":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M18 6L6 18" }), _jsx7("path", { d: "M6 6l12 12" })] });
    case "chevronDown":
      return _jsx7("path", { d: "M6 9l6 6 6-6" });
    case "chevronRight":
      return _jsx7("path", { d: "M9 18l6-6-6-6" });
    case "trash":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M3 6h18" }), _jsx7("path", { d: "M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" }), _jsx7("path", { d: "M6 6l1 16h10l1-16" }), _jsx7("path", { d: "M10 11v6" }), _jsx7("path", { d: "M14 11v6" })] });
    case "send":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M22 2L11 13" }), _jsx7("path", { d: "M22 2L15 22l-4-9-9-4 20-7z" })] });
    case "thumbsUp":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M7 10v11" }), _jsx7("path", { d: "M7 10l4.5-8a2 2 0 0 1 3.6 1.5L14 8h5.2a2 2 0 0 1 2 2.4l-1.6 8a2 2 0 0 1-2 1.6H7" })] });
    case "thumbsDown":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M17 14V3" }), _jsx7("path", { d: "M17 14l-4.5 8a2 2 0 0 1-3.6-1.5L10 16H4.8a2 2 0 0 1-2-2.4l1.6-8a2 2 0 0 1 2-1.6H17" })] });
    // The filled twins reuse the stroke twins' exact coordinates — the mitt
    // outline is CLOSED (z) and filled per-path, the stem stays a stroked
    // line — so toggling stroke↔filled never shifts a pixel.
    case "thumbsUpFilled":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M7 10v11" }), _jsx7("path", { d: "M7 10l4.5-8a2 2 0 0 1 3.6 1.5L14 8h5.2a2 2 0 0 1 2 2.4l-1.6 8a2 2 0 0 1-2 1.6H7z", fill: "currentColor", stroke: "none" })] });
    case "thumbsDownFilled":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M17 14V3" }), _jsx7("path", { d: "M17 14l-4.5 8a2 2 0 0 1-3.6-1.5L10 16H4.8a2 2 0 0 1-2-2.4l1.6-8a2 2 0 0 1 2-1.6H17z", fill: "currentColor", stroke: "none" })] });
    case "board":
      return _jsxs6(_Fragment, { children: [_jsx7("rect", { x: "1.5", y: "2", width: "3.6", height: "12", rx: "1" }), _jsx7("rect", { x: "6.2", y: "2", width: "3.6", height: "8.5", rx: "1" }), _jsx7("rect", { x: "10.9", y: "2", width: "3.6", height: "5.5", rx: "1" })] });
    case "inbox":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M2 9.5 L4 3.5 h8 l2 6" }), _jsx7("path", { d: "M2 9.5 v3 h12 v-3" }), _jsx7("path", { d: "M2 9.5 h3.4 l1 1.6 h3.2 l1-1.6 H14" })] });
    case "server":
      return _jsxs6(_Fragment, { children: [_jsx7("rect", { x: "2", y: "2.5", width: "12", height: "4.6", rx: "1.2" }), _jsx7("rect", { x: "2", y: "8.9", width: "12", height: "4.6", rx: "1.2" }), _jsx7("circle", { cx: "4.6", cy: "4.8", r: "0.8", fill: "currentColor", stroke: "none" }), _jsx7("circle", { cx: "4.6", cy: "11.2", r: "0.8", fill: "currentColor", stroke: "none" })] });
    case "agent":
      return _jsxs6(_Fragment, { children: [_jsx7("rect", { x: "3", y: "4.5", width: "10", height: "8", rx: "2" }), _jsx7("path", { d: "M8 4.5V2.2" }), _jsx7("circle", { cx: "8", cy: "1.8", r: "0.9", fill: "currentColor", stroke: "none" }), _jsx7("circle", { cx: "5.8", cy: "8.4", r: "0.9", fill: "currentColor", stroke: "none" }), _jsx7("circle", { cx: "10.2", cy: "8.4", r: "0.9", fill: "currentColor", stroke: "none" })] });
    case "playCircle":
      return _jsxs6(_Fragment, { children: [_jsx7("circle", { cx: "8", cy: "8", r: "6.2" }), _jsx7("path", { d: "M6.5 5.6 L11 8 L6.5 10.4 Z", fill: "currentColor", stroke: "none" })] });
    case "list":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M2.5 4h11" }), _jsx7("path", { d: "M2.5 8h11" }), _jsx7("path", { d: "M2.5 12h7" })] });
    case "gear":
      return _jsxs6(_Fragment, { children: [_jsx7("circle", { cx: "8", cy: "8", r: "2.2" }), _jsx7("path", { d: "M8 1.6v2" }), _jsx7("path", { d: "M8 12.4v2" }), _jsx7("path", { d: "M1.6 8h2" }), _jsx7("path", { d: "M12.4 8h2" }), _jsx7("path", { d: "M3.5 3.5l1.4 1.4" }), _jsx7("path", { d: "M11.1 11.1l1.4 1.4" }), _jsx7("path", { d: "M12.5 3.5l-1.4 1.4" }), _jsx7("path", { d: "M4.9 11.1l-1.4 1.4" })] });
    case "sparkle":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" }), _jsx7("path", { d: "M18.5 15.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z" })] });
    case "contrast":
      return _jsxs6(_Fragment, { children: [_jsx7("circle", { cx: "12", cy: "12", r: "9" }), _jsx7("path", { d: "M12 3a9 9 0 0 1 0 18z", fill: "currentColor", stroke: "none" })] });
    case "logout":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" }), _jsx7("path", { d: "M16 17l5-5-5-5" }), _jsx7("path", { d: "M21 12H9" })] });
    case "play":
      return _jsx7("path", { d: "M7 4.5v15a1 1 0 0 0 1.5.86l12-7.5a1 1 0 0 0 0-1.72l-12-7.5A1 1 0 0 0 7 4.5z", fill: "currentColor", stroke: "none" });
    case "stop":
      return _jsx7("rect", { x: "5", y: "5", width: "14", height: "14", rx: "2", fill: "currentColor", stroke: "none" });
    case "folder":
      return _jsx7("path", { d: "M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" });
    case "file":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" }), _jsx7("path", { d: "M14 2v6h6" })] });
    case "archive":
      return _jsxs6(_Fragment, { children: [_jsx7("rect", { x: "2", y: "3", width: "20", height: "5", rx: "1" }), _jsx7("path", { d: "M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8" }), _jsx7("path", { d: "M10 12h4" })] });
    case "unarchive":
      return _jsxs6(_Fragment, { children: [_jsx7("rect", { x: "2", y: "3", width: "20", height: "5", rx: "1" }), _jsx7("path", { d: "M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8" }), _jsx7("path", { d: "M12 18v-6" }), _jsx7("path", { d: "m9 14 3-3 3 3" })] });
    case "wrench":
      return _jsx7("path", { d: "M14.5 6.5 18 3a6 6 0 0 0-7.6 7.6L3 18a2.1 2.1 0 0 0 3 3l7.4-7.4A6 6 0 0 0 21 6l-3.5 3.5-3-3Z" });
    case "clock":
      return _jsxs6(_Fragment, { children: [_jsx7("circle", { cx: "12", cy: "12", r: "10" }), _jsx7("path", { d: "M12 6v6h4" })] });
    case "book":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M2 4h6a4 4 0 0 1 4 4v13a3 3 0 0 0-3-3H2z" }), _jsx7("path", { d: "M22 4h-6a4 4 0 0 0-4 4v13a3 3 0 0 1 3-3h7z" })] });
    case "compose":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M12 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" }), _jsx7("path", { d: "M18.4 2.6a2.1 2.1 0 0 1 3 3L12 15l-4 1 1-4z" })] });
    case "image":
      return _jsxs6(_Fragment, { children: [_jsx7("rect", { x: "3", y: "3", width: "18", height: "18", rx: "2" }), _jsx7("circle", { cx: "9", cy: "9", r: "2" }), _jsx7("path", { d: "M21 15l-3.1-3.1a2 2 0 0 0-2.8 0L6 21" })] });
    case "video":
      return _jsxs6(_Fragment, { children: [_jsx7("rect", { x: "2", y: "6", width: "14", height: "12", rx: "2" }), _jsx7("path", { d: "M16 10.5l5.2-3.1a.5.5 0 0 1 .8.4v8.4a.5.5 0 0 1-.8.4L16 13.5" })] });
    case "camera":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3z" }), _jsx7("circle", { cx: "12", cy: "13", r: "3" })] });
    case "music":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M9 18V5l12-2v13" }), _jsx7("circle", { cx: "6", cy: "18", r: "3" }), _jsx7("circle", { cx: "18", cy: "16", r: "3" })] });
    case "database":
      return _jsxs6(_Fragment, { children: [_jsx7("ellipse", { cx: "12", cy: "5", rx: "9", ry: "3" }), _jsx7("path", { d: "M3 5v14a9 3 0 0 0 18 0V5" }), _jsx7("path", { d: "M3 12a9 3 0 0 0 18 0" })] });
    case "branch":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M6 3v12" }), _jsx7("circle", { cx: "18", cy: "6", r: "3" }), _jsx7("circle", { cx: "6", cy: "18", r: "3" }), _jsx7("path", { d: "M18 9a9 9 0 0 1-9 9" })] });
    case "loop":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M17 2l4 4-4 4" }), _jsx7("path", { d: "M3 11v-1a4 4 0 0 1 4-4h14" }), _jsx7("path", { d: "M7 22l-4-4 4-4" }), _jsx7("path", { d: "M21 13v1a4 4 0 0 1-4 4H3" })] });
    case "variable":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M8 21s-4-3-4-9 4-9 4-9" }), _jsx7("path", { d: "M16 3s4 3 4 9-4 9-4 9" }), _jsx7("path", { d: "M15 9l-6 6" }), _jsx7("path", { d: "M9 9l6 6" })] });
    case "minus":
      return _jsx7("path", { d: "M5 12h14" });
    case "divide":
      return _jsxs6(_Fragment, { children: [_jsx7("circle", { cx: "12", cy: "6", r: "1.25", fill: "currentColor", stroke: "none" }), _jsx7("path", { d: "M5 12h14" }), _jsx7("circle", { cx: "12", cy: "18", r: "1.25", fill: "currentColor", stroke: "none" })] });
    case "function":
      return _jsxs6(_Fragment, { children: [_jsx7("rect", { x: "3", y: "3", width: "18", height: "18", rx: "2" }), _jsx7("path", { d: "M9 17c2 0 2.8-1 2.8-2.8V10c0-2 1-3.3 3.2-3" }), _jsx7("path", { d: "M9 11.2h5.7" })] });
    case "zoomIn":
      return _jsxs6(_Fragment, { children: [_jsx7("circle", { cx: "11", cy: "11", r: "8" }), _jsx7("path", { d: "M21 21l-4.35-4.35" }), _jsx7("path", { d: "M11 8v6" }), _jsx7("path", { d: "M8 11h6" })] });
    case "zoomOut":
      return _jsxs6(_Fragment, { children: [_jsx7("circle", { cx: "11", cy: "11", r: "8" }), _jsx7("path", { d: "M21 21l-4.35-4.35" }), _jsx7("path", { d: "M8 11h6" })] });
    case "fitView":
      return _jsxs6(_Fragment, { children: [_jsx7("path", { d: "M8 3H5a2 2 0 0 0-2 2v3" }), _jsx7("path", { d: "M21 8V5a2 2 0 0 0-2-2h-3" }), _jsx7("path", { d: "M3 16v3a2 2 0 0 0 2 2h3" }), _jsx7("path", { d: "M16 21h3a2 2 0 0 0 2-2v-3" })] });
    case "lock":
      return _jsxs6(_Fragment, { children: [_jsx7("rect", { x: "4", y: "11", width: "16", height: "10", rx: "2" }), _jsx7("path", { d: "M8 11V7a4 4 0 0 1 8 0v4" })] });
    default:
      return null;
  }
}
function Icon({ name, size = 16, className, title, ...props }) {
  const aria_hidden = title ? void 0 : true;
  const is16 = GRID_16.has(name);
  return _jsxs6("svg", { width: size, height: size, viewBox: is16 ? "0 0 16 16" : "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: is16 ? 1.4 : 2, strokeLinecap: "round", strokeLinejoin: "round", className, "aria-hidden": aria_hidden, role: title ? "img" : "presentation", ...props, children: [title ? _jsx7("title", { children: title }) : null, paths(name)] });
}

// dist/af_switch.js
import { jsx as _jsx8, jsxs as _jsxs7 } from "react/jsx-runtime";
function afSwitchIsActionable(props) {
  return !String(props.unavailableReason || "").trim() && !props.busy;
}
function afSwitchNextState(props) {
  return afSwitchIsActionable(props) ? !props.checked : null;
}
var reasonSeq = 0;
function AfSwitch(props) {
  const { label, checked, onChange, description, reasonVisible = true, describedBy, hint, busy = false, variant = "inline", ariaLabel, className, id, action } = props;
  const reason = String(props.unavailableReason || "").trim();
  const unavailable = Boolean(reason);
  const reasonId = describedBy || (id ? `${id}-reason` : unavailable ? `af-switch-reason-${++reasonSeq}` : void 0);
  const cls = [
    "af-switch",
    variant === "row" ? "af-switch--row" : variant === "sm" ? "af-switch--sm" : "",
    unavailable ? "af-switch--unavailable" : "",
    className || ""
  ].filter(Boolean).join(" ");
  const onClick = (e) => {
    const next = afSwitchNextState({ checked, unavailableReason: reason, busy });
    if (next === null) {
      e.preventDefault();
      return;
    }
    onChange?.(next);
  };
  const button = _jsxs7("button", { type: "button", role: "switch", id, className: cls, "data-action": action, "aria-checked": checked ? "true" : "false", "aria-disabled": unavailable ? "true" : void 0, "aria-describedby": unavailable ? reasonId : void 0, "aria-busy": busy ? "true" : void 0, "aria-label": ariaLabel, "aria-description": description ? void 0 : hint, title: unavailable ? hint ? `${reason}
${hint}` : reason : hint, onClick, children: [_jsx8("span", { className: "af-switch__track", "aria-hidden": "true", children: _jsx8("span", { className: "af-switch__thumb" }) }), _jsxs7("span", { className: "af-switch__text", children: [_jsx8("span", { className: "af-switch__label", children: label }), description ? _jsx8("span", { className: "af-switch__desc", children: description }) : null] })] });
  if (!unavailable || describedBy)
    return button;
  return _jsxs7("span", { className: variant === "row" ? "af-switch-wrap af-switch-wrap--row" : "af-switch-wrap", children: [button, _jsx8("span", { id: reasonId, className: reasonVisible ? "af-switch__reason" : "af-switch__reason af-switch__reason--hidden", children: reason })] });
}
function AfSwitchInput(props) {
  const reason = String(props.unavailableReason || "").trim();
  const cls = ["af-switch", "af-switch--native", props.variant === "row" ? "af-switch--row" : "", reason ? "af-switch--unavailable" : ""].filter(Boolean).join(" ");
  const reasonId = reason ? `${props.id || props.name}-reason` : void 0;
  const control = _jsxs7("label", { className: cls, title: reason || void 0, "data-action": props.action, children: [_jsx8("input", { type: "checkbox", role: "switch", className: "af-switch__input", id: props.id, name: props.name, defaultChecked: props.defaultChecked, onChange: (e) => props.onChange?.(e.target.checked), disabled: Boolean(reason), "aria-describedby": reasonId }), _jsx8("span", { className: "af-switch__track", "aria-hidden": "true", children: _jsx8("span", { className: "af-switch__thumb" }) }), _jsx8("span", { className: "af-switch__text", children: _jsx8("span", { className: "af-switch__label", children: props.label }) })] });
  if (!reason)
    return control;
  return _jsxs7("span", { className: props.variant === "row" ? "af-switch-wrap af-switch-wrap--row" : "af-switch-wrap", children: [control, _jsx8("span", { id: reasonId, className: "af-switch__reason", children: reason })] });
}

// dist/automations/email_fields.js
import { jsx as _jsx9, jsxs as _jsxs8 } from "react/jsx-runtime";

// dist/automations/tool_selection.js
function automationToolSelection(input) {
  const runtime = input?._runtime;
  const ceiling = Array.isArray(runtime?.allowed_tools) ? runtime.allowed_tools : null;
  const tools = Array.isArray(input?.tools) ? input.tools : ceiling;
  return Array.isArray(tools) ? tools.filter((t) => typeof t === "string" && (!ceiling || ceiling.includes(t))) : null;
}
function withAutomationTools(input, tools) {
  const next = { ...input };
  const runtime = input._runtime && typeof input._runtime === "object" ? { ...input._runtime } : {};
  if (tools === null) {
    delete next.tools;
    delete runtime.allowed_tools;
  } else {
    next.tools = [...tools];
    runtime.allowed_tools = [...tools];
  }
  if (Object.keys(runtime).length)
    next._runtime = runtime;
  else
    delete next._runtime;
  return next;
}

// dist/automations/automation_controls.json
var automation_controls_default = {
  schema: "abstractframework.automation_controls/1",
  canonical: "abstractuic ui-kit/src/automations/automation_controls.json; clients that cannot import the kit vendor a byte-identical copy (root scripts/check_identity_sync.py fails on drift)",
  labels: {
    active: "Active",
    pause: "Pause",
    resume: "Resume",
    run_now: "Run now",
    stop_current: "Stop current",
    revise: "Edit",
    archive: "Archive",
    unarchive: "Unarchive",
    discuss: "Discuss"
  },
  hints: {
    active: "On: it runs on its schedule. Off: paused, scheduled runs are skipped.\nPausing lets a run in progress finish, without further retries; Run now still works and keeps it paused.\nMaking it active again restarts the schedule at its next time after now; times missed while paused are skipped.",
    pause: "Stop scheduled runs until you resume.\nA run in progress finishes; a pending retry is cancelled. Run now still works.",
    resume: "Restart the schedule at its next time after now.\nTimes missed while paused are skipped; resuming does not run it now.",
    run_now: "Run it once now, without waiting for the schedule.\nThe schedule does not move: the next scheduled run keeps its time, or starts right after this run if its time comes first.\nDoes not count toward a run limit. Works while paused; it stays paused.\nNot available while a run is in progress.",
    stop_current: "Cancel the run in progress, or its pending retry.\nIt ends as cancelled, with no failure notice. The schedule continues.",
    revise: "Change the task, schedule or settings.\nChanges apply from the next run; a run in progress keeps its inputs. A changed schedule restarts from now, so no past time runs.",
    archive: "Stop it for good: it will not run again.\nA run in progress finishes; the history stays readable.",
    unarchive: "Bring it back from the archive, paused: nothing runs until you make it active.\nAn automation that had already finished or failed keeps that status; its history is unchanged.",
    discuss: "Talk about the results in a separate conversation, seeded with the runs up to this one.\nIt has its own workspace (the automation's files are read-only) and never changes the automation."
  },
  run_now_next_run_line: "Next scheduled run: {time}.",
  run_now_growing_line: "Growing context: later runs see this run in their history.",
  run_now_one_line: "Run it once now, without waiting for the schedule; the next scheduled run keeps its time.",
  icons: {
    run_now: {
      name: "playCircle",
      view_box: "0 0 16 16",
      stroke_width: 1.4,
      svg: '<circle cx="8" cy="8" r="6.2"></circle><path d="M6.5 5.6 L11 8 L6.5 10.4 Z" fill="currentColor" stroke="none"></path>'
    },
    attention: {
      name: "inbox",
      view_box: "0 0 16 16",
      stroke_width: 1.4,
      svg: '<path d="M2 9.5 L4 3.5 h8 l2 6"></path><path d="M2 9.5 v3 h12 v-3"></path><path d="M2 9.5 h3.4 l1 1.6 h3.2 l1-1.6 H14"></path>'
    }
  },
  email: {
    trigger_source: "email.received@1",
    trigger_label: "When an email arrives",
    not_set_up: "Connect a mailbox first \u2014 open My email",
    open_my_email: "open My email",
    filters_legend: "Only mail that matches (all optional)",
    from_in: "From these addresses",
    from_domain_in: "From these domains",
    to_in: "Sent to these addresses",
    subject_contains: "Subject contains",
    has_attachment: "Attachments",
    has_attachment_any: "any",
    has_attachment_yes: "only with attachments",
    has_attachment_no: "only without attachments",
    list_hint: "Separate entries with commas or new lines. Exact addresses and domains only (no patterns).",
    every_label: "Check for new mail every",
    interval_rule: "An automation that runs a model on new mail checks once an hour by default; one that needs no model checks every 60 s. The shortest interval is 60 s.",
    max_batch_label: "At most this many emails per run",
    max_batch_hint: "The rest wait for the next run. Each email is read once by this automation; mail that arrived before it was created, or while it is paused, is not processed.",
    untrusted_hint: "Incoming mail is data, never instructions: the automation acts only on its task. Link-opening tools (fetch_url, browser_probe) always ask for your approval.",
    notify_label: "Email result",
    notify_hint: "Email each completed run\u2019s result to the selected recipients.",
    recipients_legend: "Recipients",
    recipients_self: "Only me (default)",
    recipients_list: "Me and these addresses",
    recipients_hint: "Separate multiple addresses with commas."
  },
  schedule: {
    legend: "When",
    kind_every: "Repeat",
    kind_daily: "Daily",
    kind_weekly: "Weekly",
    kind_monthly: "Monthly",
    kind_once: "Once at\u2026",
    every_label: "Every",
    at_label: "at",
    time_label: "Time of day",
    days_legend: "On",
    days: {
      mon: "Mon",
      tue: "Tue",
      wed: "Wed",
      thu: "Thu",
      fri: "Fri",
      sat: "Sat",
      sun: "Sun"
    },
    day_label: "on day",
    last_day: "last",
    once_label: "Run once at",
    time_zone_line: "in {time_zone} (your account's time zone)",
    time_zone_line_automation: "in {time_zone} (this automation's time zone)",
    time_zone_hint: "Daily, weekly, monthly and one-time runs keep this wall-clock time when daylight saving time changes. A day the month does not have (31 in April) runs on its last day. Repeat runs at a fixed interval in UTC.",
    time_zone_change: "Change in preferences",
    time_zone_change_hint: "Your account's time zone is set in your preferences; new automations use it.",
    time_zone_default: "Gateway default ({time_zone})",
    time_zone_search: "Search time zones",
    describing: "Checking the schedule\u2026",
    incomplete: "Incomplete schedule.",
    error_at: "Pick the time of day (HH:MM).",
    error_days: "Pick at least one day.",
    error_day: "Pick a day of the month: 1 to 31, or last.",
    error_once: "Pick the date and time to run once."
  },
  attention: {
    doc: "The attention badge on a client's sessions control: the icon (icons.attention) and the count of what waits for the person elsewhere; the tooltip is these lines, one per non-zero count, then open_hint. A click opens exactly the first of them; opening a conversation acknowledges what it shows.",
    waiting_one: "1 conversation is waiting for you",
    waiting_many: "{n} conversations are waiting for you",
    result_one: "1 new result from your automations",
    result_many: "{n} new results from your automations",
    open_hint: "Click to open it.",
    label: "{n} waiting for you"
  }
};

// dist/random_id.js
function currentCrypto() {
  return globalThis.crypto;
}
function uuidV4FromBytes(bytes) {
  if (bytes.length < 16)
    throw new Error("uuidV4FromBytes: needs 16 bytes");
  const b = Array.from(bytes.subarray(0, 16));
  b[6] = b[6] & 15 | 64;
  b[8] = b[8] & 63 | 128;
  const hex = b.map((x) => x.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
function randomId() {
  const c = currentCrypto();
  if (c && typeof c.randomUUID === "function") {
    try {
      return c.randomUUID();
    } catch {
    }
  }
  if (c && typeof c.getRandomValues === "function") {
    return uuidV4FromBytes(c.getRandomValues(new Uint8Array(16)));
  }
  throw new Error("randomId: Web Crypto (crypto.getRandomValues) is unavailable");
}

// dist/automations/panel_core.js
var DURATION_RE = /^([1-9][0-9]*)([smhd])$/;
var UNIT_WORDS = {
  s: ["second", "seconds"],
  m: ["minute", "minutes"],
  h: ["hour", "hours"],
  d: ["day", "days"]
};
function parseDuration(value) {
  if (typeof value !== "string")
    return null;
  const m = DURATION_RE.exec(value);
  return m ? { amount: Number(m[1]), unit: m[2] } : null;
}
function intervalLabel(every) {
  const d = parseDuration(every);
  if (!d)
    return `every ${every}`;
  const [one, many] = UNIT_WORDS[d.unit];
  return d.amount === 1 ? `every ${one}` : `every ${d.amount} ${many}`;
}
function triggerSummary(trigger, served, vocab) {
  return triggerWords(trigger, vocab?.connections, vocab?.mailboxes, served);
}
function contextLabel(mode) {
  return mode === "growing" ? "Growing \u2014 each run sees the previous runs" : "Independent \u2014 each run starts fresh";
}
var STATUS_LABELS = {
  active: "Active",
  paused: "Paused",
  completed: "Completed",
  failed: "Failed",
  archived: "Archived"
};
var EMAIL_TEXT = automation_controls_default.email;
var EMAIL_TRIGGER_SOURCE_ID = "email.received";
var EMAIL_TRIGGER_SOURCE_VERSION = 1;
var EMAIL_DEFAULT_EVERY_MODEL = "1h";
var EMAIL_DEFAULT_EVERY_NO_MODEL = "60s";
var EMAIL_MIN_EVERY_SECONDS = 60;
var EMAIL_DEFAULT_MAX_BATCH = 100;
var EMAIL_MAX_ALLOWED_RECIPIENTS = 50;
function isEmailTrigger(trigger) {
  return !!trigger && trigger.source_id === EMAIL_TRIGGER_SOURCE_ID && trigger.source_version === EMAIL_TRIGGER_SOURCE_VERSION;
}
function emailUsable(status) {
  return !!status && status.effective_enabled === true;
}
function parseEntryList(text2) {
  const out = [];
  for (const raw of String(text2 ?? "").split(/[\s,;]+/)) {
    const e = raw.trim().toLowerCase();
    if (e && !out.includes(e))
      out.push(e);
  }
  return out;
}
var ADDRESS_FORBIDDEN = /[\s<>,;:"()[\]]/;
function isPlainAddress(value) {
  const a = value.trim().toLowerCase();
  const at = a.indexOf("@");
  if (at <= 0 || at === a.length - 1)
    return false;
  const domain = a.slice(at + 1);
  return !domain.includes("@") && !ADDRESS_FORBIDDEN.test(a);
}
function emailDefaultEvery(usesModel) {
  return usesModel ? EMAIL_DEFAULT_EVERY_MODEL : EMAIL_DEFAULT_EVERY_NO_MODEL;
}
function durationSeconds(every) {
  const d = parseDuration(every);
  if (!d)
    return null;
  return d.amount * { s: 1, m: 60, h: 3600, d: 86400 }[d.unit];
}
function emailTriggerLabel(config) {
  const c = config;
  const f = c.filter ?? {};
  const parts = ["when an email arrives"];
  const from = [...f.from_in ?? [], ...f.from_domain_in ?? []];
  if (from.length)
    parts.push(`from ${from.join(", ")}`);
  if (f.to_in && f.to_in.length)
    parts.push(`to ${f.to_in.join(", ")}`);
  if (typeof f.subject_contains === "string" && f.subject_contains)
    parts.push(`subject contains \u201C${f.subject_contains}\u201D`);
  if (f.has_attachment === true)
    parts.push("with attachments");
  if (f.has_attachment === false)
    parts.push("without attachments");
  const every = typeof c.every === "string" ? c.every : emailDefaultEvery(c.uses_model !== false);
  parts.push(`checked ${intervalLabel(every)}`);
  const batch = typeof c.max_batch === "number" ? c.max_batch : EMAIL_DEFAULT_MAX_BATCH;
  parts.push(`up to ${batch} per run`);
  return parts.join(" \xB7 ");
}
var DEFAULT_EMAIL_RECIPIENTS = { mode: "self", addresses: "" };
function emailAllowedRecipientsFrom(form) {
  if (form.mode === "self")
    return { recipients: ["self"], errors: [] };
  const errors = [];
  const items = parseEntryList(form.addresses).filter((a) => a !== "self");
  if (!items.length)
    errors.push("Name at least one address the automation may email, or choose Only me.");
  const bad = items.filter((a) => !isPlainAddress(a));
  if (bad.length)
    errors.push(`${EMAIL_TEXT.recipients_list}: ${bad.join(", ")} ${bad.length === 1 ? "is not an email address" : "are not email addresses"}.`);
  if (items.length + 1 > EMAIL_MAX_ALLOWED_RECIPIENTS)
    errors.push(`At most ${EMAIL_MAX_ALLOWED_RECIPIENTS - 1} addresses.`);
  return { recipients: ["self", ...items], errors };
}
function emailRecipientsFormFrom(list) {
  const extra = (list ?? []).filter((a) => a !== "self");
  return extra.length ? { mode: "list", addresses: extra.join(", ") } : { mode: "self", addresses: "" };
}
function emailRecipientsLabel(list) {
  const extra = (list ?? ["self"]).filter((a) => a !== "self");
  return extra.length ? `Me and ${extra.join(", ")}` : "Only me";
}
function notifyFor(emailMe, recipients = ["self"]) {
  return { channels: emailMe ? ["console", "email"] : ["console"], ...recipients.some((r) => r !== "self") ? { recipients } : {} };
}
function notifyEmails(notify) {
  return !!notify && Array.isArray(notify.channels) && notify.channels.includes("email");
}
function notifyLabel(notify) {
  return notifyEmails(notify) ? "In the console and by email" : "In the console";
}
var CONTROL_COMMANDS = {
  pause: "automation.pause",
  resume: "automation.resume",
  run_now: "automation.run_now",
  stop_current: "automation.stop_current",
  archive: "automation.archive",
  unarchive: "automation.unarchive"
};
var IN_PROGRESS = /* @__PURE__ */ new Set(["running", "waiting", "backoff"]);
function occurrenceInProgress(summary, _occurrences = []) {
  return summary.current_occurrence != null;
}
function currentOccurrenceLabel(summary) {
  const c = summary.current_occurrence;
  if (!c)
    return null;
  const attempt = c.attempt > 1 ? ` (attempt ${c.attempt})` : "";
  if (c.status === "backoff")
    return `Run #${c.index} waiting to retry (attempt ${c.attempt + 1})`;
  if (c.status === "admitted")
    return `Run #${c.index} starting${attempt}`;
  return `Run #${c.index} running${attempt}`;
}
function nextRunLabel(s, nowMs) {
  if (s.next_run_at && s.next_run_local)
    return `${formatServedLocal(s.next_run_local, s.time_zone)} (${relativeIn(s.next_run_at, nowMs)})`;
  if (s.status === "paused")
    return "none while paused";
  if (s.status === "active" && s.trigger && isEventTrigger(s.trigger))
    return NEXT_RUN_WORDS.event;
  if (s.status === "active" && s.trigger?.source_id === "manual")
    return NEXT_RUN_WORDS.manual;
  return "none scheduled";
}
var NEXT_RUN_WORDS = {
  event: "when something new arrives",
  manual: "when someone presses Run now"
};
function relativeIn(ts, nowMs) {
  const t = Date.parse(ts);
  if (Number.isNaN(t))
    return "";
  const min = Math.round((t - nowMs) / 6e4);
  if (min <= 0)
    return "due now";
  if (min < 60)
    return `in ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24)
    return `in ${h} h${min % 60 ? ` ${min % 60} min` : ""}`;
  const d = Math.floor(h / 24);
  return `in ${d} d${h % 24 ? ` ${h % 24} h` : ""}`;
}
function automationControls(summary, occurrences = [], busy = false) {
  const caps = new Set(summary.capabilities);
  const st = summary.status;
  const running = occurrenceInProgress(summary, occurrences);
  const gate = (id, ok, reason) => {
    if (busy)
      return { enabled: false, reason: "Working\u2026" };
    if (summary.legacy)
      return { enabled: false, reason: "Legacy schedule: managed with its existing controls." };
    if (!caps.has(id))
      return { enabled: false, reason: "Not permitted for this automation." };
    if (st === "archived")
      return { enabled: false, reason: "Archived: history is kept, nothing runs." };
    return ok ? { enabled: true } : { enabled: false, reason };
  };
  const live = st === "active" || st === "paused";
  const toggleCap = st === "active" ? "pause" : "resume";
  const active = busy ? { enabled: false, reason: "Working\u2026" } : summary.legacy ? { enabled: false, reason: "Legacy schedule: managed with its existing controls." } : st === "archived" ? { enabled: false, reason: "Archived: history is kept, nothing runs." } : !live ? { enabled: false, reason: "The automation has ended." } : caps.has(toggleCap) ? { enabled: true } : { enabled: false, reason: "Not permitted for this automation." };
  return {
    active,
    pause: gate("pause", st === "active", st === "paused" ? "Already paused." : "The automation has ended."),
    resume: gate("resume", st === "paused", st === "active" ? "Already running on schedule." : "The automation has ended."),
    run_now: gate("run_now", live && !running, running ? "An occurrence is in progress." : "The automation has ended."),
    stop_current: gate("stop_current", running, "Nothing is running."),
    revise: gate("revise", true, ""),
    archive: gate("archive", true, ""),
    unarchive: busy ? { enabled: false, reason: "Working\u2026" } : summary.legacy ? { enabled: false, reason: "Legacy schedule: managed with its existing controls." } : st !== "archived" ? { enabled: false, reason: "Not archived." } : caps.has("unarchive") ? { enabled: true } : { enabled: false, reason: "Not permitted for this automation." },
    discuss: busy ? { enabled: false, reason: "Working\u2026" } : summary.legacy ? { enabled: false, reason: "Legacy schedule: discussion is not available." } : caps.has("discuss") ? { enabled: true } : { enabled: false, reason: "Discussion is not permitted for this automation." }
  };
}
function activeToggleCommand(summary) {
  return summary.status === "active" ? CONTROL_COMMANDS.pause : CONTROL_COMMANDS.resume;
}
function occurrenceTone(row) {
  if (row.status === "failed")
    return "failed";
  if (row.waits.length > 0 || row.status === "waiting")
    return "waiting";
  if (row.notify !== null)
    return "notified";
  if (row.status === "running" || row.status === "backoff")
    return "running";
  return "quiet";
}
function occurrenceViews(rows) {
  return [...rows].sort((a, b) => a.index - b.index).map((row) => {
    const tone = occurrenceTone(row);
    const attempts = `${row.attempts} ${row.attempts === 1 ? "attempt" : "attempts"}`;
    const badge = tone === "failed" ? `Failed after ${attempts}` : tone === "waiting" ? "Waiting for you" : tone === "notified" ? "Notified" : tone === "running" ? "Running" : null;
    const statusText = row.status === "completed" && row.attempts > 1 ? `completed after ${attempts}` : row.status;
    return { row, tone, notable: tone === "failed" || tone === "waiting" || tone === "notified", badge, statusText, canDiscuss: !IN_PROGRESS.has(row.status) };
  });
}
function consumedAttentionCursor(summary, consumed) {
  let cursor = null;
  for (const item of summary.attention.items) {
    if (!consumed.has(item.cursor))
      break;
    cursor = item.cursor;
  }
  return cursor;
}
function attentionLabel(summary) {
  const a = summary.attention;
  const parts = [];
  if (a.unseen_count > 0)
    parts.push(`${a.unseen_count} unseen`);
  if (a.pending_waits > 0)
    parts.push(`${a.pending_waits} waiting for you`);
  return parts.length ? parts.join(" \xB7 ") : "nothing new";
}
var API_ERROR_TEXT = {
  unauthorized: "Sign in to the gateway to manage automations.",
  forbidden: "You are not allowed to do this with automations.",
  automation_not_found: "This automation does not exist (or is not yours).",
  occurrence_not_found: "That occurrence does not exist.",
  revision_conflict: "The automation changed since this view loaded. Reload it, then try again.",
  automation_busy: "An occurrence is already running or queued. Wait for it to finish.",
  invalid_state: "The automation's current state does not allow this.",
  identity_conflict: "This request id was already used for a different request.",
  invalid_request: "The gateway rejected the request as malformed.",
  invalid_definition: "The automation definition is not valid.",
  unsupported_feature: "The gateway does not support this yet.",
  unknown_trigger_source: "The gateway does not know this trigger source.",
  invalid_response: "The gateway gave an unexpected answer.",
  invalid_payload: "That answer could not be sent."
};
function apiErrorText(error) {
  return { title: API_ERROR_TEXT[error.code] ?? `The gateway refused the request (${error.code}).`, detail: error.message };
}
function isApiError(value) {
  if (!value || typeof value !== "object")
    return false;
  const v = value;
  return typeof v.status === "number" && typeof v.code === "string" && typeof v.message === "string";
}
function reviseFormFrom(summary, definition) {
  const t = summary.trigger;
  const every = t.source_id === "schedule" || isEmailTrigger(t) ? t.config.every : void 0;
  const prompt = definition ? definition.target.input_data.prompt : void 0;
  return {
    title: summary.title,
    every: typeof every === "string" ? every : null,
    calendar: isScheduleV2(t) ? calendarWhenFrom(t.config) : null,
    context: summary.context_mode,
    growingMaxTokens: Number(definition?.context?.growing?.max_tokens ?? summary.growing_max_tokens ?? DEFAULT_GROWING_MAX_TOKENS),
    prompt: typeof prompt === "string" ? prompt : null,
    toolApproval: definition ? definition.policy.tool_approval : null,
    tools: automationToolSelection(definition?.target.input_data),
    notifyEmail: definition ? notifyEmails(definition.notify) : null,
    emailRecipients: definition ? emailRecipientsFormFrom(definition.notify?.recipients) : null
  };
}
function reviseChanges(summary, form, definition) {
  const errors = [];
  const changes = {};
  const title = form.title.trim();
  if (!title)
    errors.push("Title is required.");
  else if (title.length > 120)
    errors.push("Title is at most 120 characters.");
  else if (title !== summary.title)
    changes.title = title;
  const before = reviseFormFrom(summary, definition);
  if (form.every !== before.every && form.every !== null) {
    const email = isEmailTrigger(summary.trigger);
    if (!parseDuration(form.every))
      errors.push("Interval must be a whole number of minutes, hours or days.");
    else if (email && (durationSeconds(form.every) ?? 0) < EMAIL_MIN_EVERY_SECONDS)
      errors.push("The check interval is at least 60 seconds.");
    else {
      const config = { ...summary.trigger.config, every: form.every };
      if (email)
        delete config.start_at;
      changes.trigger = { source_id: summary.trigger.source_id, source_version: summary.trigger.source_version, config };
    }
  }
  if (form.calendar && before.calendar && JSON.stringify(form.calendar) !== JSON.stringify(before.calendar)) {
    const built = calendarConfigFrom(form.calendar);
    if (!built.config)
      errors.push(...built.errors);
    else {
      const prev = summary.trigger.config;
      const config = {
        ...built.config,
        ...typeof prev.time_zone === "string" ? { time_zone: prev.time_zone } : {},
        ...typeof prev.count === "number" ? { count: prev.count } : {},
        ...typeof prev.until === "string" ? { until: prev.until } : {}
      };
      changes.trigger = { source_id: summary.trigger.source_id, source_version: summary.trigger.source_version, config };
    }
  }
  const maxTokens = form.context === "growing" ? form.growingMaxTokens ?? before.growingMaxTokens : before.growingMaxTokens;
  if (!validGrowingMaxTokens(maxTokens))
    errors.push(GROWING_MAX_TOKENS_ERROR);
  if (form.context !== summary.context_mode || maxTokens !== before.growingMaxTokens) {
    changes.context = automationContext(form.context, maxTokens);
  }
  if (definition && typeof before.prompt === "string" && typeof form.prompt === "string" && form.prompt.trim() !== before.prompt.trim()) {
    const prompt = form.prompt.trim();
    if (!prompt)
      errors.push("Task is required.");
    else
      changes.target = { bundle_ref: definition.target.bundle_ref, flow_id: definition.target.flow_id, input_data: { ...definition.target.input_data, prompt } };
  }
  if (definition && form.tools !== void 0 && JSON.stringify(form.tools) !== JSON.stringify(before.tools)) {
    const target = changes.target || { bundle_ref: definition.target.bundle_ref, flow_id: definition.target.flow_id, input_data: definition.target.input_data };
    changes.target = { ...target, input_data: withAutomationTools(target.input_data || {}, form.tools) };
  }
  if (definition && form.toolApproval && form.toolApproval !== before.toolApproval)
    changes.policy = { tool_approval: form.toolApproval };
  if (definition && typeof form.notifyEmail === "boolean") {
    const next = emailAllowedRecipientsFrom(form.notifyEmail ? form.emailRecipients ?? DEFAULT_EMAIL_RECIPIENTS : before.emailRecipients ?? DEFAULT_EMAIL_RECIPIENTS);
    const prev = emailAllowedRecipientsFrom(before.emailRecipients ?? DEFAULT_EMAIL_RECIPIENTS).recipients;
    if (next.errors.length)
      errors.push(...next.errors);
    else if (form.notifyEmail !== before.notifyEmail || JSON.stringify(next.recipients) !== JSON.stringify(prev))
      changes.notify = notifyFor(form.notifyEmail, next.recipients);
  }
  if (errors.length)
    return { errors };
  if (definition && form.target && automationTargetValue(form.target) !== automationTargetValue(definition.target)) {
    const currentInput = changes.target?.input_data || definition.target.input_data;
    changes.target = { ...form.target, input_data: retargetAutomationInput(currentInput) };
  }
  return Object.keys(changes).length ? changes : null;
}
var DEFAULT_GROWING_MAX_TOKENS = 5e4;
var GROWING_CONTEXT_HELP = "Limits history carried into the next run, keeping recent whole turns. The newest turn is kept even if oversized. New messages and tool results can grow context beyond this budget.";
var GROWING_MAX_TOKENS_ERROR = "Max growing context must be a positive whole number of tokens.";
function validGrowingMaxTokens(value) {
  return Number.isSafeInteger(value) && value > 0;
}
function automationContext(mode, maxTokens) {
  return { mode, ...maxTokens !== DEFAULT_GROWING_MAX_TOKENS ? { growing: { max_tokens: maxTokens } } : {} };
}
var SCHEDULE_TEXT = automation_controls_default.schedule;
var CALENDAR_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
var CALENDAR_KINDS = ["daily", "weekly", "monthly"];
var SCHEDULE_VERSION = 2;
function isScheduleV2(trigger) {
  return trigger.source_id === "schedule" && trigger.source_version === SCHEDULE_VERSION;
}
var SERVED_LOCAL_RE = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/;
function formatServedLocal(nextRunLocal, timeZone) {
  if (!nextRunLocal)
    return "";
  const m = SERVED_LOCAL_RE.exec(nextRunLocal);
  if (!m)
    return nextRunLocal;
  return `${m[1]} ${m[2]}${timeZone ? ` ${timeZone}` : ""}`;
}
function timeZoneLine(timeZone, whose = "account") {
  return (whose === "account" ? SCHEDULE_TEXT.time_zone_line : SCHEDULE_TEXT.time_zone_line_automation).replace("{time_zone}", timeZone);
}
var WALL_TIME_RE = /^([01][0-9]|2[0-3]):[0-5][0-9]$/;
function calendarConfigFrom(when) {
  const errors = [];
  if (!WALL_TIME_RE.test(when.at))
    errors.push(SCHEDULE_TEXT.error_at);
  if (when.kind === "weekly") {
    const days = CALENDAR_DAYS.filter((d) => when.days.includes(d));
    if (!days.length)
      errors.push(SCHEDULE_TEXT.error_days);
    return errors.length ? { config: null, errors } : { config: { kind: "weekly", days, at: when.at }, errors };
  }
  if (when.kind === "monthly") {
    const ok = when.day === "last" || Number.isInteger(when.day) && when.day >= 1 && when.day <= 31;
    if (!ok)
      errors.push(SCHEDULE_TEXT.error_day);
    return errors.length ? { config: null, errors } : { config: { kind: "monthly", day: when.day, at: when.at }, errors };
  }
  return errors.length ? { config: null, errors } : { config: { kind: "daily", at: when.at }, errors };
}
function calendarWhenFrom(config) {
  const c = config;
  const at = typeof c.at === "string" ? c.at : "";
  if (c.kind === "daily")
    return { kind: "daily", at };
  if (c.kind === "weekly")
    return { kind: "weekly", at, days: Array.isArray(c.days) ? CALENDAR_DAYS.filter((d) => c.days.includes(d)) : [] };
  if (c.kind === "monthly")
    return { kind: "monthly", at, day: c.day === "last" ? "last" : Number(c.day) };
  return null;
}
function waitToolCalls(wait) {
  if (wait.kind !== "tool_approval" || !Array.isArray(wait.details))
    return null;
  const out = [];
  for (const c of wait.details) {
    if (!c || typeof c !== "object" || Array.isArray(c))
      return null;
    const call = c;
    if (typeof call.name !== "string" || !call.arguments || typeof call.arguments !== "object" || Array.isArray(call.arguments))
      return null;
    if (call.call_id !== void 0 && typeof call.call_id !== "string")
      return null;
    out.push({ name: call.name, arguments: call.arguments, ...typeof call.call_id === "string" ? { call_id: call.call_id } : {} });
  }
  return out;
}
function eventPayloadFromWords(text2) {
  const t = text2.trim();
  if (!t)
    return { ok: false, error: "Say what happened, in a few words." };
  if (t.startsWith("{") || t.startsWith("[")) {
    try {
      return { ok: true, payload: JSON.parse(t) };
    } catch (e) {
      return { ok: false, error: `That starts like event data (JSON) but is not valid: ${e instanceof Error ? e.message : String(e)}. Write it in words instead, or fix the data.` };
    }
  }
  return { ok: true, payload: { text: t } };
}
var FAILURE_WORDS = {
  occurrence_failed: "The run failed",
  run_failed: "The run failed",
  timeout: "The run timed out",
  timed_out: "The run timed out",
  run_timeout: "The run timed out",
  cancelled: "The run was cancelled",
  occurrence_cancelled: "The run was cancelled",
  tool_denied: "A tool call was denied",
  tool_failed: "A tool failed",
  model_unavailable: "The model was not available",
  provider_error: "The model provider answered with an error",
  rate_limited: "The model provider limited the requests"
};
function failureReasonWords(code) {
  const c = String(code || "").trim().toLowerCase();
  if (!c)
    return "The run failed";
  if (FAILURE_WORDS[c])
    return FAILURE_WORDS[c];
  const words = c.replace(/[_-]+/g, " ").trim();
  return words ? words[0].toUpperCase() + words.slice(1) : "The run failed";
}
var WAIT_KIND_LABELS = {
  ask_user: "Question for you",
  tool_approval: "Approval needed",
  event: "Waiting for an event"
};
var ActionIds = class {
  constructor(mint) {
    this.mint = mint;
    this.open = /* @__PURE__ */ new Map();
  }
  idFor(signature) {
    let id = this.open.get(signature);
    if (id === void 0) {
      id = this.mint();
      this.open.set(signature, id);
    }
    return id;
  }
  /** `outcome` = the resolved value or the thrown error of the request. */
  settle(signature, outcome) {
    if (outcome.ok || isDefinitiveError(outcome.error))
      this.open.delete(signature);
  }
};
function isDefinitiveError(error) {
  return isApiError(error) && error.status > 0 && error.code !== "invalid_response";
}
function mintUuid() {
  return randomId();
}
var SeenAckTracker = class {
  constructor() {
    this.acked = null;
    this.inflight = null;
    this.failedKey = null;
    this.failedToken = void 0;
  }
  /** The key to send now, or null. Marks it in flight. */
  next(key, token) {
    if (!key || key === this.acked || key === this.inflight)
      return null;
    if (key === this.failedKey && token === this.failedToken)
      return null;
    this.inflight = key;
    return key;
  }
  succeeded(key) {
    if (this.inflight === key)
      this.inflight = null;
    this.acked = key;
    this.failedKey = null;
  }
  failed(key, token) {
    if (this.inflight === key)
      this.inflight = null;
    this.failedKey = key;
    this.failedToken = token;
  }
  get acknowledged() {
    return this.acked;
  }
};
function pickFocusTarget(root, selectors) {
  if (!root)
    return null;
  for (const sel of selectors) {
    const el = root.querySelector(sel);
    if (el && el.disabled !== true && typeof el.focus === "function")
      return el;
  }
  return null;
}

// dist/automations/email_fields.js
function AfEmailSetupNotice(p) {
  if (emailUsable(p.status))
    return null;
  const full = EMAIL_TEXT.not_set_up;
  const link = EMAIL_TEXT.open_my_email;
  const lead = full.endsWith(link) ? full.slice(0, full.length - link.length) : `${full} `;
  const cause = p.status && p.status.admin_disabled && typeof p.status.admin_disabled.cause === "string" ? p.status.admin_disabled.cause : "";
  return _jsxs8("p", { className: "af-auto__hint af-email__notice", role: "note", "data-email-setup": "missing", children: [lead, p.onOpenMyEmail ? _jsx9("button", { type: "button", className: "af-auto__linkbtn", "data-action": "open-my-email", onClick: p.onOpenMyEmail, children: link }) : link, cause ? _jsxs8("span", { className: "af-email__cause", children: [" (", cause, ")"] }) : null] });
}

// dist/automations/schedule_when.js
import { jsx as _jsx11, jsxs as _jsxs10, Fragment as _Fragment2 } from "react/jsx-runtime";
import { useEffect as useEffect4, useRef as useRef3, useState as useState3 } from "react";

// dist/af_chip.js
import { jsx as _jsx10, jsxs as _jsxs9 } from "react/jsx-runtime";
var TONE_HUES = {
  neutral: "var(--text-secondary)",
  muted: "var(--text-muted)",
  accent: "var(--accent)",
  info: "var(--info)",
  success: "var(--success)",
  warning: "var(--warning)",
  error: "var(--error)"
};
var VAR_REF = /^var\(--[a-z0-9-]+\)$/i;
function afChipHue(tone, hue) {
  const t = tone || "neutral";
  if (t === "custom") {
    const raw = String(hue || "").trim();
    if (VAR_REF.test(raw))
      return raw;
    return TONE_HUES.neutral;
  }
  return TONE_HUES[t] || TONE_HUES.neutral;
}
function chipClass(base, props, extra) {
  return [
    base,
    `${base}--${props.tone || "neutral"}`,
    props.size === "sm" ? `${base}--sm` : "",
    extra || "",
    props.className || ""
  ].filter(Boolean).join(" ");
}
function chipStyle(props) {
  return { ["--af-chip-hue"]: afChipHue(props.tone, props.hue) };
}
function AfChipButton(props) {
  return _jsx10("button", { type: "button", className: chipClass("af-chip", props, "af-chip--button"), style: chipStyle(props), title: props.title, onClick: props.onClick, "aria-pressed": typeof props.pressed === "boolean" ? props.pressed : void 0, "aria-expanded": typeof props.expanded === "boolean" ? props.expanded : void 0, "aria-label": props.ariaLabel, disabled: props.disabled, tabIndex: props.tabIndex, children: _jsx10("span", { className: "af-chip__label", children: props.children }) });
}

// dist/af_tooltip.js
import React, { useEffect as useEffect3 } from "react";

// dist/af_tooltip_core.js
var AF_TOOLTIP_DELAY_MS = 200;
var AF_TOOLTIP_ATTR = "data-af-tip";
var AF_TOOLTIP_CONTENT_ATTR = "data-af-tip-content";
function afTooltipText(content) {
  if (typeof content === "string")
    return content.trim();
  return [
    content.title,
    content.description,
    ...(content.facts || []).map((f) => `${f.label}: ${f.value}`),
    ...(content.sections || []).flatMap((s) => [s.label, ...s.items]),
    content.note
  ].filter(Boolean).join("\n");
}
function afTooltipAttributes(content) {
  const attrs = { [AF_TOOLTIP_ATTR]: afTooltipText(content) };
  if (typeof content !== "string")
    attrs[AF_TOOLTIP_CONTENT_ATTR] = JSON.stringify(content);
  return attrs;
}
function structured(value) {
  if (!value || typeof value !== "object")
    return false;
  const v = value;
  return typeof v.title === "string" && !!v.title.trim() && [v.description, v.note].every((x) => x === void 0 || typeof x === "string") && (v.facts === void 0 || Array.isArray(v.facts) && v.facts.every((f) => f && typeof f.label === "string" && typeof f.value === "string")) && (v.sections === void 0 || Array.isArray(v.sections) && v.sections.every((s) => s && typeof s.label === "string" && Array.isArray(s.items) && s.items.every((x) => typeof x === "string")));
}
function renderContent(doc, tip, content) {
  tip.textContent = "";
  tip.removeAttribute("data-structured");
  const add = (parent, tag, cls, text2) => {
    const node = doc.createElement(tag);
    node.className = cls;
    if (text2 !== void 0)
      node.textContent = text2;
    parent.appendChild(node);
    return node;
  };
  if (typeof content === "string") {
    const paragraphs = content.split(/\n+/).map((s) => s.trim()).filter(Boolean);
    if (paragraphs.length <= 1)
      tip.textContent = content;
    else
      for (const text2 of paragraphs)
        add(tip, "p", "af-tooltip__paragraph", text2);
    return;
  }
  tip.setAttribute("data-structured", "true");
  add(tip, "div", "af-tooltip__title", content.title);
  if (content.description)
    add(tip, "p", "af-tooltip__description", content.description);
  if (content.facts?.length) {
    const facts = add(tip, "dl", "af-tooltip__facts");
    for (const fact of content.facts) {
      const row = add(facts, "div", "af-tooltip__fact");
      add(row, "dt", "af-tooltip__label", fact.label);
      const val = add(row, "dd", "af-tooltip__value", fact.value);
      if (fact.tone && ["muted", "success", "warning", "danger"].includes(fact.tone))
        val.setAttribute("data-tone", fact.tone);
    }
  }
  for (const section of content.sections || []) {
    if (!section.items.length)
      continue;
    const group = add(tip, "div", "af-tooltip__section");
    if (section.label)
      add(group, "div", "af-tooltip__section-title", section.label);
    const list = add(group, "ul", "af-tooltip__list");
    for (const item of section.items)
      add(list, "li", "af-tooltip__item", item);
  }
  if (content.note)
    add(tip, "p", "af-tooltip__note", content.note);
}
function afTooltipPlacement(anchor, size, viewport, gap = 6, margin = 8) {
  let side = "top";
  let top = anchor.top - gap - size.height;
  if (top < margin) {
    const below = anchor.bottom + gap;
    if (below + size.height <= viewport.height - margin || viewport.height - anchor.bottom > anchor.top) {
      top = below;
      side = "bottom";
    }
  }
  const centre = (anchor.left + anchor.right) / 2;
  let left = centre - size.width / 2;
  left = Math.max(margin, Math.min(left, viewport.width - margin - size.width));
  top = Math.max(margin, Math.min(top, viewport.height - margin - size.height));
  return { top: Math.round(top), left: Math.round(left), side };
}
var tooltipSeq = 0;
function tipOf(el) {
  if (!el)
    return "";
  const raw = el.getAttribute(AF_TOOLTIP_CONTENT_ATTR);
  if (raw) {
    try {
      const value = JSON.parse(raw);
      if (structured(value))
        return value;
    } catch {
    }
    console.warn("#FALLBACK: invalid structured tooltip; using its plain-text fallback");
  }
  return String(el.getAttribute(AF_TOOLTIP_ATTR) || "").trim();
}
function anchorFrom(target, root) {
  const el = target;
  if (!el || typeof el.closest !== "function")
    return null;
  const a = el.closest(`[${AF_TOOLTIP_ATTR}]`);
  if (!a || !root.contains(a) || !afTooltipText(tipOf(a)))
    return null;
  return a;
}
function bindAfTooltips(root, options = {}) {
  if (!root)
    throw new Error("bindAfTooltips: a root (document or element) is required");
  const doc = root.nodeType === 9 ? root : root.ownerDocument;
  const win = doc.defaultView || globalThis;
  const delay = typeof options.delayMs === "number" && options.delayMs >= 0 ? options.delayMs : AF_TOOLTIP_DELAY_MS;
  tooltipSeq += 1;
  const tip = doc.createElement("div");
  tip.className = "af-tooltip";
  tip.setAttribute("role", "tooltip");
  const tipId = `af-tooltip-${tooltipSeq}`;
  tip.setAttribute("id", tipId);
  tip.hidden = true;
  (doc.body || doc.documentElement).appendChild(tip);
  let anchor = null;
  let pending = null;
  let showTimer = null;
  let hideTimer = null;
  let keyboard = false;
  let describedBefore = null;
  const clearShow = () => {
    if (showTimer)
      clearTimeout(showTimer);
    showTimer = null;
    pending = null;
  };
  const clearHide = () => {
    if (hideTimer)
      clearTimeout(hideTimer);
    hideTimer = null;
  };
  const place = () => {
    if (!anchor)
      return;
    const r2 = anchor.getBoundingClientRect();
    const m = tip.getBoundingClientRect();
    const p = afTooltipPlacement(r2, { width: m.width, height: m.height }, { width: win.innerWidth, height: win.innerHeight });
    tip.style.top = `${p.top}px`;
    tip.style.left = `${p.left}px`;
    tip.setAttribute("data-side", p.side);
  };
  const hide = () => {
    clearShow();
    clearHide();
    if (!anchor)
      return;
    const described = String(anchor.getAttribute("aria-describedby") || "").split(/\s+/);
    if (described.includes(tipId)) {
      if (describedBefore)
        anchor.setAttribute("aria-describedby", describedBefore);
      else
        anchor.removeAttribute("aria-describedby");
    }
    describedBefore = null;
    anchor = null;
    tip.hidden = true;
    tip.textContent = "";
  };
  const show = (el) => {
    clearShow();
    clearHide();
    if (anchor && anchor !== el)
      hide();
    const content = tipOf(el);
    const text2 = afTooltipText(content);
    if (!text2 || el.isConnected === false)
      return;
    anchor = el;
    renderContent(doc, tip, content);
    tip.hidden = false;
    const aria = String(el.getAttribute("aria-label") || "").trim();
    if (aria !== text2) {
      const prev = el.getAttribute("aria-describedby");
      describedBefore = prev && prev !== tipId ? prev : null;
      el.setAttribute("aria-describedby", describedBefore ? `${describedBefore} ${tipId}` : tipId);
    }
    place();
  };
  const schedule = (el) => {
    clearHide();
    if (anchor === el)
      return;
    if (pending === el)
      return;
    clearShow();
    pending = el;
    showTimer = setTimeout(() => {
      const target = pending;
      showTimer = null;
      pending = null;
      if (target)
        show(target);
    }, delay);
  };
  const scheduleHide = () => {
    clearShow();
    if (!anchor)
      return;
    clearHide();
    hideTimer = setTimeout(hide, 100);
  };
  const isKeyboardFocus = (el) => {
    try {
      if (typeof el.matches === "function")
        return el.matches(":focus-visible");
    } catch {
    }
    return keyboard;
  };
  const onOver = (e) => {
    const pe = e;
    if (pe.pointerType === "touch")
      return;
    if (tip.contains(e.target)) {
      clearHide();
      return;
    }
    const a = anchorFrom(e.target, root);
    if (a)
      schedule(a);
  };
  const onOut = (e) => {
    const pe = e;
    const to = pe.relatedTarget || null;
    if (to && (tip.contains(to) || anchor && anchor.contains(to) || pending && pending.contains(to)))
      return;
    if (pending && !anchor) {
      clearShow();
      return;
    }
    if (anchor)
      scheduleHide();
  };
  const onTipOut = (e) => {
    const to = e.relatedTarget || null;
    if (to && (tip.contains(to) || anchor && anchor.contains(to)))
      return;
    scheduleHide();
  };
  const onFocusIn = (e) => {
    const a = anchorFrom(e.target, root);
    if (!a)
      return;
    if (isKeyboardFocus(a))
      schedule(a);
  };
  const onFocusOut = (e) => {
    const a = anchorFrom(e.target, root);
    if (a && (a === anchor || a === pending))
      hide();
  };
  const onPress = () => {
    keyboard = false;
    hide();
  };
  const onKey = (e) => {
    if (e.key === "Escape" || e.key === "Esc") {
      if (anchor) {
        e.preventDefault();
        hide();
      } else {
        clearShow();
      }
      return;
    }
    if (!e.metaKey && !e.ctrlKey && !e.altKey)
      keyboard = true;
  };
  const onScrollOrResize = (e) => {
    if (e.type === "scroll" && tip.contains(e.target))
      return;
    hide();
  };
  const r = root;
  r.addEventListener("pointerover", onOver);
  r.addEventListener("pointerout", onOut);
  r.addEventListener("focusin", onFocusIn);
  r.addEventListener("focusout", onFocusOut);
  tip.addEventListener("pointerover", onOver);
  tip.addEventListener("pointerout", onTipOut);
  doc.addEventListener("pointerdown", onPress, true);
  win.addEventListener("keydown", onKey, true);
  win.addEventListener("scroll", onScrollOrResize, true);
  win.addEventListener("resize", onScrollOrResize);
  let released = false;
  return () => {
    if (released)
      return;
    released = true;
    hide();
    r.removeEventListener("pointerover", onOver);
    r.removeEventListener("pointerout", onOut);
    r.removeEventListener("focusin", onFocusIn);
    r.removeEventListener("focusout", onFocusOut);
    tip.removeEventListener("pointerover", onOver);
    tip.removeEventListener("pointerout", onTipOut);
    doc.removeEventListener("pointerdown", onPress, true);
    win.removeEventListener("keydown", onKey, true);
    win.removeEventListener("scroll", onScrollOrResize, true);
    win.removeEventListener("resize", onScrollOrResize);
    if (tip.parentNode)
      tip.parentNode.removeChild(tip);
  };
}
var shared = /* @__PURE__ */ new WeakMap();
function acquireAfTooltips(doc) {
  let entry = shared.get(doc);
  if (!entry) {
    entry = { count: 0, release: bindAfTooltips(doc) };
    shared.set(doc, entry);
  }
  entry.count += 1;
  let done = false;
  return () => {
    if (done)
      return;
    done = true;
    const e = shared.get(doc);
    if (!e)
      return;
    e.count -= 1;
    if (e.count <= 0) {
      e.release();
      shared.delete(doc);
    }
  };
}

// dist/af_tooltip.js
function useAfTooltips() {
  useEffect3(() => {
    if (typeof document === "undefined")
      return;
    return acquireAfTooltips(document);
  }, []);
}
function AfTooltip(props) {
  useAfTooltips();
  const child = React.Children.only(props.children);
  const text2 = afTooltipText(props.content);
  if (!text2)
    return child;
  return React.cloneElement(child, afTooltipAttributes(props.content));
}

// dist/automations/schedule_when.js
var DEFAULT_CALENDAR_AT = "08:00";
var DEFAULT_CALENDAR_DAYS = ["mon"];
var DEFAULT_CALENDAR_STATE = { at: DEFAULT_CALENDAR_AT, days: [...DEFAULT_CALENDAR_DAYS], day: 1 };
function calendarRuleOf(kind, state) {
  if (kind === "weekly")
    return { kind, at: state.at, days: [...state.days] };
  if (kind === "monthly")
    return { kind, at: state.at, day: state.day };
  return { kind, at: state.at };
}
function withCalendarRule(state, rule) {
  return { ...state, at: rule.at, ...rule.kind === "weekly" ? { days: [...rule.days] } : {}, ...rule.kind === "monthly" ? { day: rule.day } : {} };
}
function calendarStateOf(rule) {
  return withCalendarRule(DEFAULT_CALENDAR_STATE, rule);
}
var MONTH_DAYS = [...Array.from({ length: 31 }, (_, i) => String(i + 1)), "last"];
function AfCalendarRuleFields(props) {
  const v = props.value;
  const toggleDay = (d) => {
    if (v.kind !== "weekly")
      return;
    const has = v.days.includes(d);
    props.onChange({ ...v, days: CALENDAR_DAYS.filter((x) => x === d ? !has : v.days.includes(x)) });
  };
  return _jsxs10("div", { className: "af-schedule__calendar", "data-calendar-kind": v.kind, children: [v.kind === "weekly" ? _jsxs10("div", { className: "af-auto__row af-schedule__days", role: "group", "aria-label": SCHEDULE_TEXT.days_legend, children: [_jsx11("span", { children: SCHEDULE_TEXT.days_legend }), CALENDAR_DAYS.map((d) => _jsx11(AfChipButton, { className: "af-schedule__day", pressed: v.days.includes(d), disabled: props.disabled, onClick: () => toggleDay(d), tone: "accent", children: _jsx11("span", { "data-day": d, children: SCHEDULE_TEXT.days[d] }) }, d))] }) : null, _jsxs10("div", { className: "af-auto__row", children: [v.kind === "monthly" ? _jsxs10(_Fragment2, { children: [_jsx11("label", { htmlFor: `${props.idBase}-month-day`, children: SCHEDULE_TEXT.day_label }), _jsx11("select", { id: `${props.idBase}-month-day`, name: "calendar_day", value: String(v.day), disabled: props.disabled, onChange: (e) => props.onChange({ ...v, day: e.target.value === "last" ? "last" : Number(e.target.value) }), children: MONTH_DAYS.map((d) => _jsx11("option", { value: d, children: d === "last" ? SCHEDULE_TEXT.last_day : d }, d)) })] }) : null, _jsx11("label", { htmlFor: `${props.idBase}-at`, children: SCHEDULE_TEXT.at_label }), _jsx11("input", { id: `${props.idBase}-at`, name: "calendar_at", type: "time", step: 60, required: true, value: v.at, disabled: props.disabled, "aria-label": SCHEDULE_TEXT.time_label, onChange: (e) => props.onChange({ ...v, at: e.target.value.slice(0, 5) }) })] })] });
}
function AfTimeZoneLine(props) {
  return _jsxs10("p", { className: "af-schedule__tz", "data-time-zone": props.timeZone, children: [_jsx11(AfTooltip, { content: SCHEDULE_TEXT.time_zone_hint, children: _jsx11("span", { tabIndex: 0, className: "af-schedule__tz-text", children: timeZoneLine(props.timeZone, props.whose ?? "account") }) }), props.onOpenPreferences && (props.whose ?? "account") === "account" ? _jsxs10(_Fragment2, { children: [" \xB7 ", _jsx11(AfTooltip, { content: SCHEDULE_TEXT.time_zone_change_hint, children: _jsx11("button", { type: "button", className: "af-auto__link af-schedule__tz-change", onClick: props.onOpenPreferences, children: SCHEDULE_TEXT.time_zone_change }) })] }) : null] });
}
function errorMessage(e) {
  const err = e;
  return typeof err?.message === "string" && err.message ? err.message : String(e);
}
function useSchedulePreview(trigger, describe, delayMs = 250) {
  const key = trigger ? JSON.stringify(trigger) : "";
  const [state, setState] = useState3({ phase: "idle" });
  const seq = useRef3(0);
  const describeRef = useRef3(describe);
  describeRef.current = describe;
  useEffect4(() => {
    const mine = ++seq.current;
    if (!key) {
      setState({ phase: "idle" });
      return;
    }
    setState({ phase: "loading" });
    const timer = setTimeout(() => {
      describeRef.current(JSON.parse(key)).then((description) => {
        if (seq.current === mine)
          setState({ phase: "ok", description });
      }, (e) => {
        if (seq.current === mine)
          setState({ phase: "error", message: errorMessage(e) });
      });
    }, delayMs);
    return () => clearTimeout(timer);
  }, [key, delayMs]);
  return state;
}
function AfServedSchedule(props) {
  const st = props.state;
  if (st.phase === "ok") {
    return _jsxs10(_Fragment2, { children: [props.showZone === false ? null : _jsx11(AfTimeZoneLine, { timeZone: st.description.time_zone, whose: props.whose, onOpenPreferences: props.onOpenPreferences }), _jsx11("p", { className: "af-schedule__preview", "aria-live": "polite", "data-preview": "served", children: st.description.first_run_sentence })] });
  }
  if (st.phase === "error")
    return _jsx11("p", { className: "af-schedule__preview af-auto__warn", role: "alert", "data-preview": "error", children: st.message });
  return _jsx11("p", { className: "af-schedule__preview", "aria-live": "polite", "data-preview": st.phase, children: st.phase === "loading" ? SCHEDULE_TEXT.describing : props.incompleteText ?? SCHEDULE_TEXT.incomplete });
}

// dist/automations/AutomationPanel.js
var STATUS_ICONS = {
  active: "play",
  paused: "pause",
  completed: "check",
  failed: "error",
  archived: "archive"
};
function AutomationStateLabel(props) {
  const status = String(props.status);
  const icon = STATUS_ICONS[status];
  return _jsxs11("span", { className: `af-auto__status af-auto__status--${status}${props.className ? ` ${props.className}` : ""}`, "data-state": status, children: [_jsx12("span", { className: "af-auto__status-word", children: STATUS_LABELS[status] ?? status }), icon ? _jsx12(Icon, { name: icon, size: props.iconSize ?? 11, className: "af-auto__status-icon" }) : null] });
}
var DISCUSS_LABEL = "Discuss this run";
var plainTextRenderer = (text2) => _jsx12("div", { className: "af-auto-text", "data-unformatted": "true", children: text2 });
function toApiError(e) {
  if (isApiError(e))
    return e;
  const message = e && typeof e === "object" && "message" in e ? String(e.message) : String(e);
  return { status: 0, code: "client_error", message };
}
function WrappingPath(props) {
  const parts = props.path.split(/(?<=[/\\_-])/);
  return _jsx12("code", { className: "af-auto__path-text", children: parts.map((part, i) => _jsxs11(React2.Fragment, { children: [part, i < parts.length - 1 ? _jsx12("wbr", {}) : null] }, i)) });
}
function triggerSourceProblem(summary, sources) {
  const t = summary.trigger;
  const src = sources.find((x) => x.id === t.source_id && x.version === t.source_version);
  if (!src)
    return `This gateway does not list the trigger source ${t.source_id}@${t.source_version}.`;
  if ("available" in src && src.available === false)
    return `Trigger source ${t.source_id}@${t.source_version} is unavailable${src.unavailable_reason ? `: ${src.unavailable_reason}` : "."}`;
  return null;
}
function AutomationHeader(props) {
  const s = props.summary;
  const current = currentOccurrenceLabel(s);
  const problem = triggerSourceProblem(s, props.triggerSources);
  const next = nextRunLabel(s, props.nowMs ?? Date.now());
  return _jsxs11("header", { className: "af-auto__head", children: [_jsxs11("div", { className: "af-auto__titlebar", children: [_jsx12("h2", { className: "af-auto__title", id: props.titleId, tabIndex: -1, children: s.title }), _jsx12(AutomationStateLabel, { status: s.status }), s.legacy ? _jsx12("span", { className: "af-auto__legacy", children: "Legacy schedule" }) : null] }), _jsxs11("dl", { className: "af-auto__facts", children: [props.workflowLabel ? _jsxs11(_Fragment3, { children: [_jsx12("dt", { children: "Flow" }), _jsx12("dd", { "data-fact": "workflow", children: props.workflowLabel })] }) : null, _jsx12("dt", { children: "When" }), _jsxs11("dd", { "data-fact": "trigger", children: [triggerSummary(s.trigger, s, { connections: props.triggerConnections, mailboxes: props.mailboxes }), problem ? _jsxs11("span", { className: "af-auto__warn", role: "note", children: [" ", problem] }) : null] }), _jsx12("dt", { children: "Context" }), _jsx12("dd", { "data-fact": "context", children: contextLabel(s.context_mode) }), current ? _jsxs11(_Fragment3, { children: [_jsx12("dt", { children: "Now" }), _jsx12("dd", { "data-fact": "current", className: "is-notable", children: current })] }) : null, _jsx12("dt", { children: "Next run" }), _jsx12("dd", { "data-fact": "next", children: next }), _jsx12("dt", { children: "Runs" }), _jsx12("dd", { "data-fact": "count", children: s.occurrence_count }), s.workspace_root && props.onOpenWorkspace ? _jsxs11(_Fragment3, { children: [_jsx12("dt", { children: "Files" }), _jsx12("dd", { "data-fact": "workspace", className: "af-auto__workspace", children: _jsxs11("button", { type: "button", className: "af-auto__path", "data-action": "open-workspace", title: `Browse the automation's folder
${s.workspace_root}`, "aria-label": "Browse the automation's files", onClick: () => props.onOpenWorkspace?.(s.automation_id), children: [_jsx12(Icon, { name: "folder", size: 14, className: "af-auto__path-icon" }), _jsx12("span", { children: "Browse its files" })] }) })] }) : null, _jsx12("dt", { children: "Attention" }), _jsx12("dd", { "data-fact": "attention", className: s.attention.unread || s.attention.pending_waits ? "is-notable" : void 0, children: attentionLabel(s) })] })] });
}
function AutomationDefinitionBlock(props) {
  const d = props.definition;
  const render = props.renderText ?? plainTextRenderer;
  const task = d.target.input_data.prompt;
  const retry = d.policy.retry;
  const approval = d.policy.tool_approval;
  return _jsxs11("details", { className: "af-auto__definition", "data-definition-revision": d.revision, open: props.open, children: [_jsxs11("summary", { children: [_jsx12(Icon, { name: "chevronRight", size: 14, className: "af-auto__definition-chevron" }), _jsx12(Icon, { name: "file", size: 14 }), _jsx12("span", { className: "af-auto__definition-title", children: "Details" })] }), _jsxs11("dl", { className: "af-auto__facts", children: [_jsx12("dt", { children: "Target" }), _jsx12("dd", { "data-def": "target", children: _jsx12("code", { children: d.target.workflow_id }) }), typeof task === "string" && task ? _jsxs11(_Fragment3, { children: [_jsx12("dt", { children: "Task" }), _jsx12("dd", { "data-def": "prompt", children: render(task) })] }) : null, _jsx12("dt", { children: "Trigger" }), _jsxs11("dd", { "data-def": "trigger", children: [triggerSummary(d.trigger, props.served, { connections: props.triggerConnections, mailboxes: props.mailboxes }), isEmailTrigger(d.trigger) ? _jsx12("div", { className: "af-auto__hint", "data-def": "email_rule", children: emailTriggerLabel(d.trigger.config) }) : null, _jsxs11("details", { className: "af-auto__exact", "data-def": "trigger_config", children: [_jsx12("summary", { children: "Exact configuration" }), _jsx12("pre", { className: "af-auto__json", children: JSON.stringify(d.trigger.config, null, 2) })] })] }), _jsx12("dt", { children: "Context" }), _jsxs11("dd", { "data-def": "context", children: [contextLabel(d.context.mode), d.context.mode === "growing" ? ` \xB7 ${Number(d.context.growing?.max_tokens ?? 5e4).toLocaleString()} tokens` : ""] }), _jsx12("dt", { children: "Tools" }), _jsx12("dd", { "data-def": "tool_approval", children: approval === "ask" ? "Ask before each tool call" : approval === "auto" ? "Run without asking" : String(approval) }), _jsx12("dt", { children: "Notify" }), _jsx12("dd", { "data-def": "notify", children: notifyLabel(d.notify) }), d.notify?.channels.includes("email") ? _jsxs11(_Fragment3, { children: [_jsx12("dt", { children: "Recipients" }), _jsx12("dd", { "data-def": "email_recipients", children: emailRecipientsLabel(d.notify.recipients) })] }) : null, _jsx12("dt", { children: "Retries" }), _jsxs11("dd", { "data-def": "retry", children: [retry.max_attempts, " ", retry.max_attempts === 1 ? "attempt" : "attempts", ", backoff ", retry.backoff.initial, " \xD7", retry.backoff.factor, " up to ", retry.backoff.max] }), d.workspace_root ? _jsxs11(_Fragment3, { children: [_jsx12("dt", { children: "Folder" }), _jsx12("dd", { "data-def": "workspace", children: _jsx12(WrappingPath, { path: d.workspace_root }) })] }) : null, _jsx12("dt", { children: "Revision" }), _jsx12("dd", { "data-def": "revision", children: d.revision })] })] });
}
var SPEC = automation_controls_default;
var CONTROL_LABELS = SPEC.labels;
var CONTROL_ICONS = {
  active: "play",
  pause: "pause",
  resume: "play",
  run_now: SPEC.icons.run_now.name,
  stop_current: "stop",
  revise: "edit",
  archive: "archive",
  unarchive: "unarchive",
  discuss: "chat"
};
var CONTROL_HINTS = SPEC.hints;
var RUN_NOW_ONE_LINE = SPEC.run_now_one_line;
var RUN_NOW_GLYPH = SPEC.icons.run_now;
var ATTENTION_GLYPH = SPEC.icons.attention;
var ATTENTION_TEXT = SPEC.attention;
function attentionBadgeTooltip(waiting, results) {
  const t = SPEC.attention;
  const lines = [];
  if (waiting === 1)
    lines.push(t.waiting_one);
  else if (waiting > 1)
    lines.push(t.waiting_many.replace("{n}", String(waiting)));
  if (results === 1)
    lines.push(t.result_one);
  else if (results > 1)
    lines.push(t.result_many.replace("{n}", String(results)));
  return lines.length ? [...lines, t.open_hint].join("\n") : "";
}
function attentionBadgeLabel(total) {
  return total > 0 ? SPEC.attention.label.replace("{n}", String(total)) : "";
}
var RUN_NOW_NEXT_RUN_LINE = SPEC.run_now_next_run_line;
var RUN_NOW_GROWING_LINE = SPEC.run_now_growing_line;
function controlHint(id, summary) {
  const lines = [CONTROL_HINTS[id]];
  if (id === "run_now" && summary) {
    if (summary.next_run_local)
      lines.push(RUN_NOW_NEXT_RUN_LINE.replace("{time}", formatServedLocal(summary.next_run_local, summary.time_zone)));
    if (summary.context_mode === "growing")
      lines.push(RUN_NOW_GROWING_LINE);
  }
  return lines.join("\n");
}
function disabledReasons(controls, shown, idBase) {
  const byReason = /* @__PURE__ */ new Map();
  for (const id of shown) {
    const st = controls[id];
    if (st.enabled)
      continue;
    const reason = st.reason ?? "Not available now.";
    byReason.set(reason, [...byReason.get(reason) ?? [], id]);
  }
  const lines = [];
  const describedBy = {};
  [...byReason.entries()].forEach(([reason, ids], i) => {
    const id = `${idBase}-why-${i}`;
    lines.push({ id, text: `${ids.map((c) => CONTROL_LABELS[c]).join(", ")}: ${reason}` });
    for (const c of ids)
      describedBy[c] = id;
  });
  return { lines, describedBy };
}
function IconLabel(props) {
  return _jsxs11(_Fragment3, { children: [_jsx12(Icon, { name: props.icon, size: 14, className: "af-auto__btn-icon" }), _jsx12("span", { children: props.label })] });
}
function AutomationControlsBar(p) {
  const c = automationControls(p.summary, p.occurrences, p.busy);
  const archived = p.summary.status === "archived";
  const shown = ["active", "run_now", "stop_current", "revise", archived ? "unarchive" : "archive"];
  const why = disabledReasons(c, shown, p.idBase ?? `af-auto-${p.summary.automation_id}`);
  const btn = (id, onClick, extra) => {
    const hint = controlHint(id, p.summary);
    return _jsx12("button", { type: "button", className: `af-auto__btn${extra?.danger ? " af-auto__btn--danger" : ""}`, "data-action": extra?.action ?? id, disabled: !c[id].enabled, title: c[id].enabled ? hint : `${c[id].reason}
${hint}`, "aria-description": hint, "aria-describedby": why.describedBy[id], "aria-pressed": extra?.pressed, onClick, children: _jsx12(IconLabel, { icon: CONTROL_ICONS[id], label: extra?.label ?? CONTROL_LABELS[id] }) }, id);
  };
  return _jsxs11("div", { className: "af-auto__controls-wrap", children: [_jsxs11("div", { className: "af-auto__actionbar", children: [_jsxs11("div", { className: "af-auto__controls", role: "toolbar", "aria-label": "Automation controls", children: [_jsx12(AfSwitch, { className: "af-auto__switch", action: "active", label: CONTROL_LABELS.active, checked: p.summary.status === "active", unavailableReason: c.active.enabled ? null : c.active.reason ?? "Not available now.", describedBy: why.describedBy.active, busy: p.busy, hint: controlHint("active", p.summary), onChange: () => p.onCommand(activeToggleCommand(p.summary)) }, "active"), btn("run_now", () => p.onCommand(CONTROL_COMMANDS.run_now)), btn("stop_current", () => p.onCommand(CONTROL_COMMANDS.stop_current)), btn("revise", p.onToggleRevise, { pressed: p.reviseOpen, action: "edit" }), archived ? btn("unarchive", () => p.onCommand(CONTROL_COMMANDS.unarchive)) : btn("archive", p.onAskArchive, { danger: true, label: "Archive\u2026" })] }), _jsx12("span", { className: `af-auto__notice${p.notice ? " af-auto__notice--on" : ""}`, role: "status", tabIndex: -1, children: p.notice ? _jsxs11(_Fragment3, { children: [_jsx12(Icon, { name: "check", size: 13 }), _jsx12("span", { className: "af-auto__notice-text", children: p.notice }), p.onDismissNotice ? _jsx12("button", { type: "button", className: "af-auto__icon-btn af-auto__icon-btn--bare", "data-action": "dismiss-notice", "aria-label": "Dismiss", title: "Dismiss", onClick: p.onDismissNotice, children: _jsx12(Icon, { name: "x", size: 12 }) }) : null] }) : null })] }), why.lines.length ? _jsxs11("p", { className: "af-auto__reasons", children: [_jsx12(Icon, { name: "info", size: 12, className: "af-auto__reasons-icon" }), why.lines.map((l) => _jsx12("span", { id: l.id, children: l.text }, l.id))] }) : null, p.summary.status === "paused" && c.run_now.enabled ? _jsx12("p", { className: "af-auto__hint", children: "Paused: scheduled runs are skipped. Run now works and keeps it paused." }) : null, p.confirmingArchive && !archived ? _jsxs11("div", { className: "af-auto__confirm", role: "group", "aria-label": "Confirm archive", children: [_jsxs11("p", { children: ["Archive \u201C", p.summary.title, "\u201D? Its history stays readable; it will not run again. The current run, if any, finishes."] }), _jsxs11("div", { className: "af-auto__row", children: [_jsx12("button", { type: "button", className: "af-auto__btn af-auto__btn--danger", "data-action": "archive-confirm", disabled: !c.archive.enabled, onClick: () => p.onCommand(CONTROL_COMMANDS.archive), children: _jsx12(IconLabel, { icon: "archive", label: "Archive" }) }), _jsx12("button", { type: "button", className: "af-auto__btn", "data-action": "archive-cancel", onClick: p.onCancelArchive, children: _jsx12(IconLabel, { icon: "x", label: "Keep it" }) })] })] }) : null] });
}
var UNIT_OPTIONS = [
  ["m", "minutes"],
  ["h", "hours"],
  ["d", "days"]
];
function readReviseForm(form, fallback) {
  const val = (name) => {
    const el = form.elements.namedItem(name);
    return el && typeof el.value === "string" ? el.value : null;
  };
  const amount = val("every_amount");
  const unit = val("every_unit");
  const every = amount !== null && unit !== null ? `${amount.trim()}${unit}` : fallback.every;
  const ctx = form.elements.namedItem("context");
  const context = ctx && (ctx.value === "growing" || ctx.value === "independent") ? ctx.value : fallback.context;
  const prompt = val("prompt");
  const tools = form.elements.namedItem("tool_approval");
  const toolApproval = tools && (tools.value === "auto" || tools.value === "ask") ? tools.value : fallback.toolApproval ?? null;
  const notifyEl = form.elements.namedItem("notify_email");
  const notifyEmail = notifyEl && typeof notifyEl.checked === "boolean" ? notifyEl.checked : fallback.notifyEmail ?? null;
  const rcpt = form.elements.namedItem("email_recipients");
  const list = val("email_recipient_list");
  const emailRecipients = rcpt && (rcpt.value === "self" || rcpt.value === "list") ? { mode: rcpt.value, addresses: list ?? "" } : fallback.emailRecipients ?? null;
  return { title: val("title") ?? fallback.title, every, context, growingMaxTokens: val("growing_max_tokens") === null ? fallback.growingMaxTokens : Number(val("growing_max_tokens")), prompt: prompt ?? fallback.prompt ?? null, toolApproval, notifyEmail, emailRecipients };
}
function AutomationReviseForm(p) {
  const initial = reviseFormFrom(p.summary, p.definition);
  const [target, setTarget] = useState4();
  const [selectedTools, setSelectedTools] = useState4(initial.tools ?? null);
  const [contextMode, setContextMode] = useState4(initial.context);
  const [emailResult, setEmailResult] = useState4(Boolean(initial.notifyEmail));
  const [calKind, setCalKind] = useState4(initial.calendar?.kind ?? null);
  const [calState, setCalState] = useState4(initial.calendar ? calendarStateOf(initial.calendar) : null);
  const calendar = calKind && calState ? calendarRuleOf(calKind, calState) : null;
  const calendarTrigger = (() => {
    if (!calendar)
      return null;
    const built = calendarConfigFrom(calendar);
    if (!built.config)
      return null;
    const zone = p.summary.trigger.config.time_zone;
    return { source_id: p.summary.trigger.source_id, source_version: p.summary.trigger.source_version, config: { ...built.config, ...typeof zone === "string" ? { time_zone: zone } : {} } };
  })();
  const described = useSchedulePreview(calendarTrigger, p.previewSchedule);
  const d = initial.every ? parseDuration(initial.every) : null;
  const units = d && d.unit === "s" ? [["s", "seconds"], ...UNIT_OPTIONS] : UNIT_OPTIONS;
  const base = `af-auto-revise-${p.summary.automation_id}`;
  const usable = emailUsable(p.emailStatus);
  const emailTrigger = isEmailTrigger(p.summary.trigger);
  return _jsxs11("form", { className: "af-auto__revise", "aria-labelledby": `${base}-heading`, onSubmit: (e) => {
    e.preventDefault();
    p.onSubmit({ ...readReviseForm(e.currentTarget, initial), ...calendar ? { calendar } : {}, ...target ? { target } : {}, ...p.availableTools !== void 0 ? { tools: selectedTools } : {} });
  }, onKeyDown: (e) => {
    if (e.key === "Escape" && p.onCancel) {
      e.preventDefault();
      p.onCancel();
    }
  }, children: [p.heading === null ? _jsx12("span", { id: `${base}-heading`, hidden: true, children: "Edit automation" }) : _jsxs11("h3", { className: "af-auto__form-title", id: `${base}-heading`, children: [_jsx12(Icon, { name: "edit", size: 14 }), " ", p.heading ?? "Edit automation"] }), p.definition && p.workflowPickerOptions ? _jsx12(AutomationWorkflowPicker, { target: target || p.definition.target, options: p.workflowPickerOptions, onChange: setTarget }) : null, _jsxs11("label", { className: "af-auto__field", htmlFor: `${base}-title`, children: [_jsx12("span", { children: "Title" }), _jsx12("input", { id: `${base}-title`, name: "title", defaultValue: initial.title, maxLength: 120, required: true })] }), initial.prompt !== null && initial.prompt !== void 0 ? _jsxs11("label", { className: "af-auto__field", htmlFor: `${base}-prompt`, children: [_jsx12("span", { children: "Task" }), _jsx12("textarea", { id: `${base}-prompt`, name: "prompt", defaultValue: initial.prompt, rows: Math.min(10, Math.max(3, initial.prompt.split("\n").length + 1)), required: true })] }) : null, d ? _jsxs11("fieldset", { className: "af-auto__field", children: [_jsx12("legend", { children: emailTrigger ? EMAIL_TEXT.every_label : "Repeat every (UTC)" }), _jsxs11("div", { className: "af-auto__row", children: [_jsx12("input", { name: "every_amount", type: "number", min: 1, step: 1, defaultValue: d.amount, "aria-label": "Interval amount" }), _jsx12("select", { name: "every_unit", defaultValue: d.unit, "aria-label": "Interval unit", children: units.map(([v, l]) => _jsx12("option", { value: v, children: l }, v)) })] }), emailTrigger ? _jsx12("p", { className: "af-auto__hint", "data-email-rule": "interval", children: EMAIL_TEXT.interval_rule }) : null] }) : calendar ? _jsxs11("fieldset", { className: "af-auto__field", "data-field": "calendar", children: [_jsx12("legend", { children: SCHEDULE_TEXT.legend }), _jsx12("div", { className: "af-auto__row", role: "radiogroup", "aria-label": "Schedule kind", children: CALENDAR_KINDS.map((k) => _jsxs11("label", { children: [_jsx12("input", { type: "radio", name: `${base}-calendar-kind`, value: k, checked: calendar.kind === k, disabled: p.busy, onChange: () => setCalKind(k) }), " ", SCHEDULE_TEXT[`kind_${k}`]] }, k)) }), _jsx12(AfCalendarRuleFields, { value: calendar, onChange: (next) => setCalState((prev) => withCalendarRule(prev ?? calendarStateOf(next), next)), idBase: base, disabled: p.busy }), _jsx12(AfServedSchedule, { state: described, whose: "automation" })] }) : _jsx12("p", { className: "af-auto__hint", children: "This trigger has no interval to change." }), _jsxs11("fieldset", { className: "af-auto__field", children: [_jsx12("legend", { children: "Context" }), _jsxs11("label", { children: [_jsx12("input", { type: "radio", name: "context", value: "independent", defaultChecked: initial.context === "independent", onChange: () => setContextMode("independent") }), " Independent \u2014 each run starts fresh"] }), _jsxs11("label", { children: [_jsx12("input", { type: "radio", name: "context", value: "growing", defaultChecked: initial.context === "growing", onChange: () => setContextMode("growing") }), " Growing \u2014 each run sees the previous runs"] }), _jsx12("div", { hidden: contextMode !== "growing", children: _jsxs11("label", { className: "af-auto__field", children: [_jsx12("span", { children: "Max growing context (tokens)" }), _jsx12("input", { name: "growing_max_tokens", type: "number", min: 1, step: 1, disabled: p.busy || contextMode !== "growing", defaultValue: initial.growingMaxTokens }), _jsx12("span", { className: "af-auto__hint", children: GROWING_CONTEXT_HELP })] }) })] }), initial.toolApproval ? _jsxs11("fieldset", { className: "af-auto__field", children: [_jsx12("legend", { children: "Tools" }), p.availableTools !== void 0 ? _jsx12(AutomationToolsPicker, { availableTools: p.availableTools, value: selectedTools, onChange: setSelectedTools, disabled: p.busy }) : null, _jsxs11("label", { children: [_jsx12("input", { type: "radio", name: "tool_approval", value: "auto", defaultChecked: initial.toolApproval === "auto" }), " Run without asking"] }), _jsxs11("label", { children: [_jsx12("input", { type: "radio", name: "tool_approval", value: "ask", defaultChecked: initial.toolApproval === "ask" }), " Ask before each tool call"] })] }) : null, initial.notifyEmail !== null && initial.notifyEmail !== void 0 && initial.emailRecipients ? _jsxs11("fieldset", { className: "af-auto__field", "data-field": "email", children: [_jsx12("legend", { children: "Mailbox" }), !usable ? _jsx12(AfEmailSetupNotice, { status: p.emailStatus, onOpenMyEmail: p.onOpenMyEmail }) : null, _jsx12(AfSwitchInput, { variant: "row", action: "notify-email", name: "notify_email", label: EMAIL_TEXT.notify_label, defaultChecked: Boolean(initial.notifyEmail), onChange: setEmailResult, unavailableReason: !usable && !initial.notifyEmail ? "Connect a mailbox first." : null }), _jsxs11("p", { className: "af-auto__hint", children: [EMAIL_TEXT.notify_hint, " Turn on Email result to choose yourself or other email addresses."] }), _jsx12("div", { hidden: !emailResult, children: _jsxs11("fieldset", { className: "af-auto__field", disabled: !emailResult, "data-field": "email-recipients", children: [_jsx12("legend", { children: EMAIL_TEXT.recipients_legend }), _jsxs11("label", { children: [_jsx12("input", { type: "radio", name: "email_recipients", value: "self", defaultChecked: initial.emailRecipients.mode === "self" }), " ", EMAIL_TEXT.recipients_self] }), _jsxs11("label", { children: [_jsx12("input", { type: "radio", name: "email_recipients", value: "list", defaultChecked: initial.emailRecipients.mode === "list", disabled: !usable && initial.emailRecipients.mode !== "list" }), " ", EMAIL_TEXT.recipients_list] }), _jsx12("textarea", { name: "email_recipient_list", "aria-label": EMAIL_TEXT.recipients_list, rows: 2, spellCheck: false, defaultValue: initial.emailRecipients.addresses, disabled: !usable && initial.emailRecipients.mode !== "list" }), _jsx12("p", { className: "af-auto__hint", children: EMAIL_TEXT.recipients_hint })] }) })] }) : null, _jsx12("p", { className: "af-auto__hint", children: "Changes apply from the next run; runs that a new schedule would have had in the past are not made up." }), p.errors.length ? _jsx12("ul", { className: "af-auto__form-errors", role: "alert", children: p.errors.map((e) => _jsx12("li", { children: e }, e)) }) : null, _jsxs11("div", { className: "af-auto__row", children: [_jsx12("button", { type: "submit", className: "af-auto__btn af-auto__btn--primary", "data-action": "edit-save", disabled: p.busy, children: _jsx12(IconLabel, { icon: "check", label: p.submitLabel ?? "Save changes" }) }), p.onCancel ? _jsx12("button", { type: "button", className: "af-auto__btn", "data-action": "edit-cancel", onClick: p.onCancel, children: _jsx12(IconLabel, { icon: "x", label: "Cancel" }) }) : null] })] });
}
function taskOfTurn(userTurn, task) {
  const t = typeof task === "string" ? task.trim() : "";
  const turn = typeof userTurn === "string" ? userTurn : "";
  const nl = turn.indexOf("\n");
  if (!t || nl < 0 || !turn.startsWith("["))
    return null;
  const rest = turn.slice(nl + 1);
  return rest === t || rest.startsWith(`${t}
`) ? t : null;
}
function occurrenceStartWords(row) {
  const source = String(row.trigger?.source_id || "");
  if (source === "schedule")
    return "on schedule";
  if (source === "manual")
    return "run by hand";
  if (source.startsWith("email"))
    return "new mail";
  return source ? "something arrived" : "";
}
var RECEIVED_LABEL = "What the agent received";
function fieldValue(form, name) {
  const el = form.elements.namedItem(name);
  return el && typeof el.value === "string" ? el.value.trim() : "";
}
var TOOL_APPROVAL_HEADING = "The automation wants to use these tools:";
function WaitAnswerForm(p) {
  const w = p.wait;
  const promptId = `${p.idBase}-${w.run_id}-${w.wait_key}-prompt`;
  const answer = (payload) => p.onAnswerWait(w.run_id, w.wait_key, payload);
  const render = p.renderText ?? plainTextRenderer;
  const head = (fallback) => _jsxs11("div", { className: "af-auto-wait__prompt", id: promptId, children: [_jsx12("span", { className: "af-auto-wait__kind", children: WAIT_KIND_LABELS[w.kind] ?? "Waiting" }), w.prompt ? render(w.prompt) : _jsxs11("span", { children: [" ", fallback] })] });
  if (w.kind === "tool_approval") {
    const calls = waitToolCalls(w);
    return _jsxs11("div", { className: "af-auto-wait af-auto-wait--tool_approval", role: "group", "data-wait-key": w.wait_key, "data-wait-kind": w.kind, "aria-labelledby": promptId, children: [calls && calls.length ? _jsx12(ToolCallWordsList, { calls, heading: TOOL_APPROVAL_HEADING, headingId: promptId, label: "Tool calls to approve", className: "af-auto-wait__calls" }) : _jsxs11(_Fragment3, { children: [_jsx12("p", { className: "af-toolwords__heading", id: promptId, children: _jsx12("strong", { children: TOOL_APPROVAL_HEADING }) }), _jsx12("p", { className: "af-auto__hint", children: "The gateway did not list the tool calls; open the run to see them before approving." })] }), _jsxs11("div", { className: "af-auto__row", children: [_jsx12("button", { type: "button", className: "af-auto__btn af-auto__btn--primary", "data-action": "wait-approve", disabled: p.busy, onClick: () => answer({ approved: true }), children: _jsx12(IconLabel, { icon: "check", label: "Approve" }) }), _jsx12("button", { type: "button", className: "af-auto__btn af-auto__btn--danger", "data-action": "wait-deny", disabled: p.busy, onClick: () => answer({ approved: false }), children: _jsx12(IconLabel, { icon: "x", label: "Deny" }) })] })] });
  }
  if (w.kind === "event") {
    return _jsxs11("form", { className: "af-auto-wait af-auto-wait--event", "data-wait-key": w.wait_key, "data-wait-kind": w.kind, "aria-labelledby": promptId, onSubmit: (e) => {
      e.preventDefault();
      const parsed = eventPayloadFromWords(fieldValue(e.currentTarget, "payload"));
      if (parsed.ok)
        answer({ payload: parsed.payload });
      else
        p.onWaitError?.(parsed.error);
    }, children: [head("The run waits for an event."), _jsx12("textarea", { name: "payload", rows: 3, "aria-label": "What happened", placeholder: "What happened, in a few words (for example: the signed contract arrived)", disabled: p.busy }), _jsx12("p", { className: "af-auto__hint", children: "Your words are sent as the event's text." }), _jsx12("div", { className: "af-auto__row", children: _jsx12("button", { type: "submit", className: "af-auto__btn af-auto__btn--primary", "data-action": "wait-send-event", disabled: p.busy, children: _jsx12(IconLabel, { icon: "send", label: "Send event" }) }) })] });
  }
  if (w.kind === "ask_user") {
    return _jsxs11("form", { className: "af-auto-wait af-auto-wait--ask_user", "data-wait-key": w.wait_key, "data-wait-kind": w.kind, "aria-labelledby": promptId, onSubmit: (e) => {
      e.preventDefault();
      const v = fieldValue(e.currentTarget, "response");
      if (v)
        answer({ response: v });
    }, children: [head("The run is waiting for your input."), w.choices && w.choices.length ? _jsx12("div", { className: "af-auto__row", role: "group", "aria-label": "Choices", children: w.choices.map((c) => _jsx12("button", { type: "button", className: "af-auto__btn", "data-action": "wait-choice", disabled: p.busy, onClick: () => answer({ response: c }), children: c }, c)) }) : null, _jsxs11("div", { className: "af-auto__row", children: [_jsx12("input", { name: "response", "aria-label": "Your answer", placeholder: "Your answer", disabled: p.busy }), _jsx12("button", { type: "submit", className: "af-auto__btn af-auto__btn--primary", "data-action": "wait-answer", disabled: p.busy, children: _jsx12(IconLabel, { icon: "send", label: "Answer" }) })] })] });
  }
  return _jsxs11("div", { className: "af-auto-wait", role: "group", "data-wait-key": w.wait_key, "data-wait-kind": String(w.kind), "aria-labelledby": promptId, children: [head("The run is waiting."), _jsxs11("p", { className: "af-auto__hint", children: ["This kind of wait (", String(w.kind), ") cannot be answered here; open the run."] })] });
}
var ATTENTION_FOCUS_MS = 2600;
function attentionTarget(root, unseenIndex) {
  if (!root)
    return null;
  const wait = root.querySelector(".af-auto-occ .af-auto-wait");
  if (wait)
    return wait;
  if (typeof unseenIndex === "number")
    return root.querySelector(`.af-auto-occ[data-index="${unseenIndex}"]`);
  return null;
}
function OccurrencePair(p) {
  const { row, tone, badge, statusText } = p.view;
  const idBase = `af-auto-occ-${row.run_id}`;
  const render = p.renderText ?? plainTextRenderer;
  const discussOk = p.discuss.enabled && p.view.canDiscuss && !p.busy;
  const discussWhy = !p.discuss.enabled ? p.discuss.reason ?? "Not available." : !p.view.canDiscuss ? "Available once this run finishes." : null;
  const turn = (kind, text2) => p.renderTurn ? p.renderTurn({ kind, role: kind === "trigger" ? "user" : "assistant", text: text2, index: row.index, runId: row.run_id }) : render(text2);
  const turnClass = p.renderTurn ? " af-auto-turn--card" : "";
  const task = typeof p.task === "string" ? p.task.trim() : "";
  const showTask = taskOfTurn(row.user_turn, task) !== null;
  const started = occurrenceStartWords(row);
  const firedWords = whenWords(row.fired_at, { timeZone: p.timeZone, nowMs: p.nowMs, style: "day" });
  const empty = tone === "failed" ? row.failure ? "No answer." : "No answer: the run failed." : tone === "waiting" ? "Waiting for your answer." : tone === "running" ? "Running\u2026" : "No answer.";
  return _jsxs11("li", { className: `af-auto-occ af-auto-occ--${tone}`, "data-index": row.index, "data-tone": tone, "aria-labelledby": `${idBase}-h`, children: [_jsxs11("div", { className: `af-auto-turn af-auto-turn--trigger${turnClass}`, "data-turn": "trigger", children: [_jsxs11("div", { className: "af-auto-turn__meta", id: `${idBase}-h`, title: `${row.trigger.summary} \xB7 fired ${whenWords(row.fired_at, { timeZone: p.timeZone, nowMs: p.nowMs, style: "day" })}`, children: [_jsxs11("span", { className: "af-auto-turn__index", children: ["Run #", row.index] }), started ? ` \xB7 ${started}` : "", firedWords ? ` \xB7 ${firedWords}` : ""] }), p.eventCard ? _jsxs11("div", { className: "af-auto-event", "data-event-card": "true", children: [_jsx12(Icon, { name: "inbox", size: 14, className: "af-auto__btn-icon" }), _jsxs11("span", { className: "af-auto-event__text", children: [_jsx12("strong", { className: "af-auto-event__source", children: p.eventCard.source }), p.eventCard.what ? _jsxs11("span", { children: [" \xB7 ", p.eventCard.what] }) : null, p.eventCard.at ? _jsxs11("span", { className: "af-auto-turn__muted", children: [" \xB7 ", p.eventCard.at] }) : null] })] }) : null, (showTask ? task : row.user_turn).trim() ? _jsx12("div", { className: "af-auto-turn__text", children: turn("trigger", showTask ? task : row.user_turn) }) : null, showTask ? _jsxs11("details", { className: "af-auto-received", "data-received": "true", children: [_jsx12("summary", { children: RECEIVED_LABEL }), _jsx12("div", { className: "af-auto-received__body", children: render(row.user_turn) })] }) : null] }), _jsxs11("div", { className: `af-auto-turn af-auto-turn--answer${turnClass}`, "data-turn": "answer", children: [_jsxs11("div", { className: "af-auto-turn__meta", children: [badge ? _jsx12("span", { className: `af-auto-badge af-auto-badge--${tone}`, children: badge }) : null, _jsx12("span", { className: "af-auto-turn__status", children: statusText }), row.finished_at ? _jsxs11("span", { title: whenWords(row.finished_at, { timeZone: p.timeZone, nowMs: p.nowMs, style: "clock" }), children: [" \xB7 ", whenWords(row.finished_at, { timeZone: p.timeZone, nowMs: p.nowMs, style: "day" })] }) : null] }), row.notify ? _jsxs11("div", { className: "af-auto-notify", "data-notify": "true", children: [_jsx12("strong", { children: row.notify.title }), row.notify.body ? _jsx12("div", { className: "af-auto-notify__body", children: render(row.notify.body) }) : null] }) : null, row.failure ? _jsxs11("div", { className: "af-auto-failure", "data-failure": row.failure.reason_code, children: [_jsx12("strong", { children: failureReasonWords(row.failure.reason_code) }), row.failure.message && row.failure.message.trim().toLowerCase() !== failureReasonWords(row.failure.reason_code).toLowerCase() ? `: ${row.failure.message}` : "", " ", _jsxs11("span", { className: "af-auto-turn__muted", children: ["(after ", row.failure.attempts, " ", row.failure.attempts === 1 ? "attempt" : "attempts", ")"] })] }) : null, row.answer ? _jsx12("div", { className: "af-auto-turn__text", children: turn("answer", row.answer) }) : _jsx12("div", { className: "af-auto-turn__empty", children: empty }), row.artifacts.length ? _jsx12("ul", { className: "af-auto-artifacts", "aria-label": "Artifacts", children: row.artifacts.map((a) => _jsxs11("li", { children: [p.onOpenResource ? _jsxs11("button", { type: "button", className: "af-auto__linkbtn", "data-action": "open-artifact", onClick: () => p.onOpenResource?.({ kind: "artifact", url: a.url, name: a.name, mimeType: a.mime_type, runId: row.run_id }), children: [_jsx12(Icon, { name: "file", size: 13, className: "af-auto__btn-icon" }), " ", a.name] }) : _jsx12("span", { className: "af-auto-artifact__name", children: a.name }), " ", _jsx12("span", { className: "af-auto-turn__muted", children: a.mime_type })] }, a.artifact_id)) }) : null, row.waits.map((w) => _jsx12(WaitAnswerForm, { wait: w, busy: p.busy, idBase, onAnswerWait: p.onAnswerWait, onWaitError: p.onWaitError, renderText: p.renderText }, `${w.run_id}:${w.wait_key}`)), p.readMarker] }), _jsxs11("div", { className: "af-auto-occ__foot", children: [_jsxs11("details", { className: "af-auto-occ__details", children: [_jsx12("summary", { children: "Run details" }), _jsxs11("dl", { className: "af-auto__facts", children: [_jsx12("dt", { children: "Run" }), _jsx12("dd", { children: _jsx12("code", { children: row.run_id }) }), _jsx12("dt", { children: "Attempts" }), _jsx12("dd", { children: row.attempts })] }), _jsxs11("div", { className: "af-auto__row", children: [_jsx12("button", { type: "button", className: "af-auto__btn", "data-action": "open-run", onClick: () => p.onOpenRun(row.run_id), children: _jsx12(IconLabel, { icon: "list", label: "Open run ledger" }) }), p.onOpenResource ? _jsx12("button", { type: "button", className: "af-auto__btn", "data-action": "open-ledger-json", onClick: () => p.onOpenResource?.({ kind: "ledger", url: row.ledger_url, name: `run-${row.run_id}-ledger.json`, runId: row.run_id }), children: _jsx12(IconLabel, { icon: "file", label: "Ledger (JSON)" }) }) : null, row.workspace_url && p.onOpenWorkspace ? _jsx12("button", { type: "button", className: "af-auto__btn", "data-action": "open-workspace", title: "Browse this run's folder", onClick: () => p.onOpenWorkspace?.(row.run_id), children: _jsx12(IconLabel, { icon: "folder", label: "Workspace" }) }) : null] })] }), p.discussOpen ? _jsxs11("form", { className: "af-auto-discuss", "aria-label": `${DISCUSS_LABEL}, from run ${row.index}`, onSubmit: (e) => {
    e.preventDefault();
    const v = fieldValue(e.currentTarget, "prompt");
    if (v)
      p.onDiscussSubmit(row.index, v);
  }, children: [_jsxs11("p", { className: "af-auto__hint", children: ["Starts a new conversation from run #", row.index, " with the automation's whole history (runs 1\u2013", row.index, "). It works in its own folder; the automation's files can be read but not changed (by the file tools; shell commands are not sandboxed), and nothing is written back into the automation."] }), _jsx12("textarea", { name: "prompt", rows: 3, "aria-label": "Your message", placeholder: "Ask about this result\u2026", required: true }), _jsxs11("div", { className: "af-auto__row", children: [_jsx12("button", { type: "submit", className: "af-auto__btn af-auto__btn--primary", "data-action": "discuss-submit", disabled: p.busy, children: _jsx12(IconLabel, { icon: "send", label: "Start discussion" }) }), _jsx12("button", { type: "button", className: "af-auto__btn", "data-action": "discuss-cancel", onClick: p.onDiscussCancel, children: _jsx12(IconLabel, { icon: "x", label: "Cancel" }) })] })] }) : _jsxs11(_Fragment3, { children: [_jsx12("button", { type: "button", className: "af-auto__btn af-auto__btn--quiet", "data-action": "discuss", disabled: !discussOk, title: CONTROL_HINTS.discuss, "aria-description": CONTROL_HINTS.discuss, "aria-describedby": discussWhy ? `${idBase}-discuss-why` : void 0, onClick: () => p.onDiscussOpen(row.index), children: _jsx12(IconLabel, { icon: CONTROL_ICONS.discuss, label: DISCUSS_LABEL }) }), discussWhy ? _jsx12("span", { className: "af-auto__reasons", id: `${idBase}-discuss-why`, children: discussWhy }) : null] })] })] });
}
var NOTICE_MS = 5e3;
var COMMAND_NOTICES = {
  [CONTROL_COMMANDS.pause]: "Automation paused.",
  [CONTROL_COMMANDS.resume]: "Automation active.",
  [CONTROL_COMMANDS.run_now]: "Run requested.",
  [CONTROL_COMMANDS.stop_current]: "Stop requested.",
  [CONTROL_COMMANDS.unarchive]: "Unarchived: it is paused until you make it active."
};
function AutomationPanel(props) {
  const { summary, busy } = props;
  const render = props.renderText ?? plainTextRenderer;
  const titleId = useId2();
  const rootRef = useRef4(null);
  const [ownEditOpen, setOwnEditOpen] = useState4(false);
  const controlled = props.editOpen !== void 0;
  const editable = automationControls(summary, props.occurrences, false).revise.enabled;
  const reviseOpen = editable && (controlled ? props.editOpen === true : ownEditOpen);
  const editBaseRef = useRef4(null);
  if (!reviseOpen)
    editBaseRef.current = null;
  else if (!editBaseRef.current || editBaseRef.current.summary.automation_id !== summary.automation_id)
    editBaseRef.current = { summary, definition: props.definition };
  const editBase = editBaseRef.current;
  const onEditOpenChangeRef = useRef4(props.onEditOpenChange);
  onEditOpenChangeRef.current = props.onEditOpenChange;
  const setReviseOpen = (open) => {
    if (!controlled)
      setOwnEditOpen(open);
    onEditOpenChangeRef.current?.(open);
  };
  const [reviseErrors, setReviseErrors] = useState4([]);
  const [confirmingArchive, setConfirmingArchive] = useState4(false);
  const [discussAt, setDiscussAt] = useState4(null);
  const [localError, setLocalError] = useState4(null);
  const [notice, setNotice] = useState4(null);
  useEffect5(() => {
    if (!notice)
      return;
    const t = setTimeout(() => setNotice(null), NOTICE_MS);
    return () => clearTimeout(t);
  }, [notice]);
  useEffect5(() => {
    if (!reviseOpen)
      return;
    setReviseErrors([]);
    const field = pickFocusTarget(rootRef.current, ['.af-auto__revise [name="title"]']);
    field?.focus();
    field?.scrollIntoView?.({ block: "nearest" });
  }, [reviseOpen, summary.automation_id]);
  const [focusAfter, setFocusAfter] = useState4(null);
  useEffect5(() => {
    if (!focusAfter)
      return;
    pickFocusTarget(rootRef.current, [...focusAfter, ".af-auto__notice", ".af-auto__title"])?.focus();
    setFocusAfter(null);
  }, [focusAfter]);
  const idsRef = useRef4(null);
  if (!idsRef.current)
    idsRef.current = new ActionIds(props.newId ?? mintUuid);
  const ids = idsRef.current;
  const report = (e) => setLocalError(toApiError(e));
  const act = (signature, run, done) => {
    setLocalError(null);
    setNotice(null);
    run(ids.idFor(signature)).then((value) => {
      ids.settle(signature, { ok: true });
      done(value);
    }, (error) => {
      ids.settle(signature, { ok: false, error });
      report(error);
    });
  };
  const consumedRef = useRef4({ id: summary.automation_id, cursors: /* @__PURE__ */ new Set() });
  const [, consumedChanged] = useState4(0);
  if (consumedRef.current.id !== summary.automation_id)
    consumedRef.current = { id: summary.automation_id, cursors: /* @__PURE__ */ new Set() };
  const currentCursors = new Set(summary.attention.items.map((it) => it.cursor));
  for (const cursor of consumedRef.current.cursors)
    if (!currentCursors.has(cursor))
      consumedRef.current.cursors.delete(cursor);
  const markConsumed = (cursor) => {
    const owner = summary.automation_id;
    if (consumedRef.current.id !== owner || consumedRef.current.cursors.has(cursor))
      return;
    consumedRef.current.cursors.add(cursor);
    consumedChanged((n) => n + 1);
  };
  const marker = (cursor) => _jsx12(VisibleContentMarker, { ownerKey: summary.automation_id, contentKey: cursor, enabled: true, onConsume: () => markConsumed(cursor) }, `${summary.automation_id}:${cursor}`);
  const ack = consumedAttentionCursor(summary, consumedRef.current.cursors);
  const onSeenRef = useRef4(props.onSeen);
  onSeenRef.current = props.onSeen;
  const seenRef = useRef4(null);
  if (!seenRef.current)
    seenRef.current = new SeenAckTracker();
  useEffect5(() => {
    const tracker = seenRef.current;
    const key = ack ? `${summary.automation_id}|${ack}` : null;
    if (!ack || !tracker.next(key, summary))
      return;
    const token = summary;
    onSeenRef.current(ack).then(() => tracker.succeeded(key), (e) => {
      tracker.failed(key, token);
      report(e);
    });
  });
  const openedAtRef = useRef4(null);
  const openAt = props.openAt ?? "attention";
  const firstUnseen = summary.attention.items[0]?.index;
  useEffect5(() => {
    if (openAt !== "attention" || openedAtRef.current === summary.automation_id || !props.occurrences.length)
      return;
    const target = attentionTarget(rootRef.current, firstUnseen);
    if (!target)
      return;
    openedAtRef.current = summary.automation_id;
    target.scrollIntoView?.({ block: "start" });
    target.classList.add("is-attention-focus");
    const t = setTimeout(() => target.classList.remove("is-attention-focus"), ATTENTION_FOCUS_MS);
    return () => clearTimeout(t);
  }, [openAt, summary.automation_id, props.occurrences, firstUnseen]);
  const controls = automationControls(summary, props.occurrences, busy);
  const views = occurrenceViews(props.occurrences);
  const task = props.definition?.target.input_data?.prompt;
  const eventCardOf = (runId) => props.occurrenceEvents && runId in props.occurrenceEvents ? occurrenceEventCard(props.occurrenceEvents[runId], { trigger: summary.trigger, connections: props.triggerConnections, mailboxes: props.mailboxes, timeZone: summary.time_zone, nowMs: props.nowMs }) : null;
  const more = summary.occurrence_count - props.occurrences.length;
  const shownError = localError ?? props.error ?? null;
  const errText = shownError ? apiErrorText(shownError) : null;
  const att = summary.attention;
  return _jsxs11("section", { ref: rootRef, className: `af-auto${props.className ? ` ${props.className}` : ""}`, ...props.hideHeader ? { "aria-label": summary.title } : { "aria-labelledby": titleId }, "aria-busy": busy, "data-text-rendering": props.renderText ? "rich" : "unformatted", children: [props.hideHeader ? null : _jsxs11(_Fragment3, { children: [_jsx12(AutomationHeader, { summary, workflowLabel: props.workflowName, triggerSources: props.triggerSources, titleId, nowMs: props.nowMs, onOpenWorkspace: props.onOpenWorkspace, triggerConnections: props.triggerConnections, mailboxes: props.mailboxes }), _jsx12(AutomationControlsBar, { summary, occurrences: props.occurrences, busy, confirmingArchive, reviseOpen, notice, onDismissNotice: () => setNotice(null), idBase: `${titleId}-ctl`, onCommand: (type) => act(`command:${type}`, (command_id) => props.onCommand(type, void 0, { command_id }), () => {
    if (type === CONTROL_COMMANDS.archive) {
      setConfirmingArchive(false);
      setNotice("Archive requested.");
      setFocusAfter(['[data-action="archive"]']);
    } else
      setNotice(COMMAND_NOTICES[type] ?? "Command sent.");
  }), onToggleRevise: () => {
    setReviseErrors([]);
    setReviseOpen(!reviseOpen);
  }, onAskArchive: () => setConfirmingArchive(true), onCancelArchive: () => {
    setConfirmingArchive(false);
    setFocusAfter(['[data-action="archive"]']);
  } })] }), reviseOpen && editBase ? _jsx12(AutomationReviseForm, { summary: editBase.summary, definition: editBase.definition, busy, errors: reviseErrors, availableTools: props.availableTools, workflowPickerOptions: props.workflowPickerOptions, emailStatus: props.emailStatus, onOpenMyEmail: props.onOpenMyEmail, previewSchedule: props.previewSchedule, onCancel: () => {
    setReviseOpen(false);
    setFocusAfter(['[data-action="edit"]']);
  }, onSubmit: (form) => {
    const base = editBase.summary;
    const changes = reviseChanges(base, form, editBase.definition);
    if (changes === null) {
      setReviseErrors(["Nothing changed."]);
      return;
    }
    if ("errors" in changes) {
      setReviseErrors(changes.errors);
      return;
    }
    setReviseErrors([]);
    act(`revise:${base.revision}:${JSON.stringify(changes)}`, async (command_id) => {
      const prepared = form.target && changes.target ? { ...changes, target: await (props.prepareTarget ? props.prepareTarget(changes.target) : prepareAutomationTarget(changes.target, props.workflowPickerOptions)) } : changes;
      return props.onRevise(prepared, base.revision, { command_id });
    }, () => {
      setNotice("Saved; applies from the next run.");
      setReviseOpen(false);
      setFocusAfter(['[data-action="edit"]']);
    });
  } }) : props.definition ? _jsx12(AutomationDefinitionBlock, { definition: props.definition, renderText: render, served: summary, triggerConnections: props.triggerConnections, mailboxes: props.mailboxes }) : null, errText ? _jsxs11("div", { className: "af-auto__error", role: "alert", "data-code": shownError?.code, children: [_jsx12(Icon, { name: "error", size: 14, className: "af-auto__btn-icon" }), _jsxs11("span", { className: "af-auto__error-text", children: [_jsx12("strong", { children: errText.title }), " ", _jsx12("span", { children: errText.detail })] }), localError ? _jsx12("button", { type: "button", className: "af-auto__icon-btn af-auto__icon-btn--bare", "data-action": "dismiss-error", "aria-label": "Dismiss", title: "Dismiss", onClick: () => setLocalError(null), children: _jsx12(Icon, { name: "x", size: 12 }) }) : null] }) : null, att.items.length || att.waits.length ? _jsx12("section", { className: "af-auto__attention", "aria-label": "Needs attention", children: _jsxs11("ul", { children: [att.items.map((it) => _jsxs11("li", { className: `af-auto__attention-item af-auto__attention-item--${it.kind}`, "data-cursor": it.cursor, children: [_jsx12("span", { className: `af-auto-badge af-auto-badge--${it.kind === "failure" ? "failed" : "notified"}`, children: it.kind === "failure" ? "Failed" : "Notified" }), " ", _jsx12("strong", { children: it.title }), " ", _jsxs11("span", { className: "af-auto-turn__muted", children: ["Run #", it.index, " \xB7 ", whenWords(it.at, { timeZone: summary.time_zone, nowMs: props.nowMs, style: "day" })] }), it.body ? _jsx12("div", { className: "af-auto__attention-body", children: render(it.body) }) : null, marker(it.cursor)] }, it.cursor)), att.waits.map((w) => _jsxs11("li", { className: "af-auto__attention-item af-auto__attention-item--wait", children: [_jsx12("span", { className: "af-auto-badge af-auto-badge--waiting", "data-wait-kind": w.kind, children: WAIT_KIND_LABELS[w.kind] ?? "Waiting for you" }), " ", _jsxs11("span", { className: "af-auto-turn__muted", children: ["Run #", w.index] }), w.prompt ? _jsx12("div", { className: "af-auto__attention-body", children: render(w.prompt) }) : null] }, `${w.run_id}:${w.wait_key}`))] }) }) : null, more > 0 ? _jsx12("button", { type: "button", className: "af-auto__btn af-auto__more", "data-action": "load-more", disabled: busy, onClick: props.onLoadMore, children: _jsx12(IconLabel, { icon: "history", label: `Load earlier runs (${more} more)` }) }) : null, views.length ? _jsx12("ol", { className: "af-auto__timeline", "aria-label": "Runs", children: views.map((v) => {
    const rowSel = `[data-index="${v.row.index}"]`;
    return _jsx12(OccurrencePair, { view: v, busy, eventCard: eventCardOf(v.row.run_id), task: typeof task === "string" ? task : void 0, timeZone: summary.time_zone, nowMs: props.nowMs, discuss: controls.discuss, renderText: render, renderTurn: props.renderTurn, readMarker: summary.attention.items.filter((it) => it.index === v.row.index).map((it) => marker(it.cursor)), onOpenWorkspace: props.onOpenWorkspace, onOpenResource: props.onOpenResource ? (resource) => {
      setLocalError(null);
      try {
        Promise.resolve(props.onOpenResource?.(resource)).catch(report);
      } catch (e) {
        report(e);
      }
    } : void 0, discussOpen: discussAt === v.row.index, onOpenRun: props.onOpenRun, onAnswerWait: (runId, waitKey, payload) => {
      setLocalError(null);
      props.onAnswerWait(runId, waitKey, payload).then(() => setNotice("Answer sent."), report);
    }, onWaitError: (message) => setLocalError({ status: 0, code: "invalid_payload", message }), onDiscussOpen: setDiscussAt, onDiscussCancel: () => {
      setDiscussAt(null);
      setFocusAfter([`${rowSel} [data-action="discuss"]`]);
    }, onDiscussSubmit: (index, prompt) => act(`discuss:${index}:${prompt}`, (request_id) => props.onDiscuss(index, prompt, { request_id }), () => {
      setDiscussAt(null);
      setNotice("Discussion started in a new conversation.");
      setFocusAfter([`${rowSel} [data-action="discuss"]`]);
    }) }, v.row.run_id);
  }) }) : _jsx12("p", { className: "af-auto__empty", children: "No runs yet." })] });
}
var AutomationPanel_default = AutomationPanel;
export {
  ATTENTION_FOCUS_MS,
  ATTENTION_GLYPH,
  ATTENTION_TEXT,
  AutomationControlsBar,
  AutomationDefinitionBlock,
  AutomationHeader,
  AutomationPanel,
  AutomationReviseForm,
  AutomationStateLabel,
  CONTROL_HINTS,
  CONTROL_ICONS,
  CONTROL_LABELS,
  DISCUSS_LABEL,
  NOTICE_MS,
  OccurrencePair,
  RECEIVED_LABEL,
  RUN_NOW_GLYPH,
  RUN_NOW_GROWING_LINE,
  RUN_NOW_NEXT_RUN_LINE,
  RUN_NOW_ONE_LINE,
  STATUS_ICONS,
  TOOL_APPROVAL_HEADING,
  WaitAnswerForm,
  WrappingPath,
  attentionBadgeLabel,
  attentionBadgeTooltip,
  attentionTarget,
  controlHint,
  AutomationPanel_default as default,
  disabledReasons,
  occurrenceStartWords,
  plainTextRenderer,
  readReviseForm,
  taskOfTurn,
  triggerSourceProblem
};

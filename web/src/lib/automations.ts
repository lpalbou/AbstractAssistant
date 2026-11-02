/**
 * Automations in the web Assistant: what the Apple Watch assistant does, from the gateway's data
 * (watch/apple Sources/App/Automations, the shared Swift client's `NewAutomation`). The rules that
 * already live in the kit are used from there (`intervalLabel`, `occurrenceViews`, `reviseChanges`);
 * this module holds only what the watch decides on its own side, written once for the web pages.
 */
import { intervalLabel, occurrenceViews, type AutomationSummary, type OccurrenceRow, type RunToolPlan } from "@abstractframework/ui-kit";
import type { ChatMessage } from "@abstractframework/panel-chat";

/** A JSON object as the gateway sends and reads it. */
export type JsonObject = Record<string, unknown>;

/** The interface an automation's gateway default runs (the watch's: its Ask uses the same). */
export const AUTOMATION_INTERFACE = "abstractcode.agent.v1";

/** How often an automation can run, shortest first (the watch's `ScheduleLine.presets`). */
export const EVERY_PRESETS = ["30s", "1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "24h", "48h", "7d"] as const;

/** How many of its runs an automation's page shows (the watch's: the latest ten). */
export const RUNS_SHOWN = 10;

/** `GET /automations` as the gateway serves it (ADR 0048: `section` and the counts; older gateways serve none). */
export type AutomationsListing = {
  items: AutomationSummary[];
  next_cursor: string | null;
  paused_automations_count?: number;
  archived_automations_count?: number;
  archived_automations?: number;
};

const sectionOf = (s: AutomationSummary): unknown => (s as AutomationSummary & { section?: unknown }).section;

const count = (n: unknown): number | null => (typeof n === "number" && Number.isFinite(n) && n >= 0 ? Math.floor(n) : null);

/**
 * The list as the watch draws it (ADR 0048): the gateway's rows in its order, the paused ones folded
 * under "Paused · N" with the gateway's count. Nothing is sorted here; a gateway that serves no
 * `section` gets every row in the main list and no Paused section.
 */
export function automationSections(page: AutomationsListing | null): { main: AutomationSummary[]; paused: AutomationSummary[]; pausedCount: number; archivedCount: number } {
  const rows = (page?.items ?? []).filter((s) => s.status !== "archived");
  const archivedCount = count(page?.archived_automations_count) ?? count(page?.archived_automations) ?? 0;
  if (!rows.some((s) => typeof sectionOf(s) === "string")) return { main: rows, paused: [], pausedCount: 0, archivedCount };
  const paused = rows.filter((s) => sectionOf(s) === "paused");
  return { main: rows.filter((s) => sectionOf(s) !== "paused"), paused, pausedCount: paused.length ? count(page?.paused_automations_count) ?? paused.length : 0, archivedCount };
}

/** "30s" → 30, "5m" → 300, "2h" → 7200, "1d" → 86400 (the gateway's `^[1-9][0-9]*[smhd]$`). */
export function everySeconds(every: string): number | null {
  const m = /^([1-9][0-9]*)([smhd])$/.exec(every);
  return m ? Number(m[1]) * { s: 1, m: 60, h: 3600, d: 86400 }[m[2] as "s" | "m" | "h" | "d"] : null;
}

/** "Every hour", "Every 12 hours": the kit's interval words, as a choice reads. */
export function everyLabel(every: string): string {
  const words = intervalLabel(every);
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** The interval choices for an automation: the presets, its own first when none of them is it. */
export function everyChoices(current: string): string[] {
  const s = everySeconds(current);
  const presets: string[] = [...EVERY_PRESETS];
  return !current || presets.some((p) => everySeconds(p) === s) ? presets : [current, ...presets];
}

/** The automation's interval (`trigger.config.every`), or "" for another trigger. */
export function everyOf(s: AutomationSummary): string {
  const every = (s.trigger?.config as JsonObject | undefined)?.every;
  return typeof every === "string" ? every : "";
}

/** "08:00" from a `HH:MM` input, or "" when it is not one. */
export function clockOf(value: string): string {
  const m = /^([01][0-9]|2[0-3]):([0-5][0-9])$/.exec(value.trim());
  return m ? `${m[1]}:${m[2]}` : "";
}

/** When a new automation runs: every `every`, or daily at `at` (the account's time zone). */
export type NewAutomationWhen = { kind: "every"; every: string } | { kind: "daily"; at: string };

/** The default title: the task's first line, at most 120 characters (the other clients' default). */
export function titleOfTask(task: string): string {
  const line = (task.trim().split("\n")[0] ?? "").trim();
  return line.length <= 120 ? line : `${line.slice(0, 119)}…`;
}

/**
 * The title after the task is edited: an automation named by its task (the title is the task, or
 * its first 120 characters) keeps that name in step; a title of its own is left alone (null).
 */
export function titleAfterTask(newTask: string, oldTitle: string | undefined, oldTask: string | undefined): string | null {
  if (oldTitle === undefined || oldTask === undefined) return null;
  const namedByTask = oldTitle === oldTask || (oldTitle.length === 120 && oldTask.startsWith(oldTitle));
  return namedByTask ? newTask.slice(0, 120) : null;
}

/**
 * `POST /automations` for a new automation, as the watch writes it (`NewAutomation.body`): the task as
 * the workflow's prompt (the gateway's default for the interface, or a chosen workflow with its
 * inputs), the tools its runs may use and which ask first, `schedule@2` every or daily at, whether
 * each run builds on the earlier ones (and how much of them it reads), and `tool_approval` "ask"
 * only when one tool asks.
 */
export function newAutomationBody(input: {
  requestId: string;
  task: string;
  /** null: the gateway's default workflow for `AUTOMATION_INTERFACE`. */
  workflow: { bundle_ref: string; flow_id: string; input_data: JsonObject } | null;
  when: NewAutomationWhen;
  buildsOnEarlierRuns: boolean;
  /** How much of its earlier runs each run reads, in tokens (null: the gateway's default). */
  growingMaxTokens: number | null;
  tools: RunToolPlan;
}): JsonObject {
  const task = input.task.trim();
  const runtime: JsonObject = { allowed_tools: [...input.tools.allowed_tools] };
  if (input.tools.tool_policy)
    runtime.tool_policy = {
      auto_approve_tools: [...input.tools.tool_policy.auto_approve_tools],
      require_approval_tools: [...input.tools.tool_policy.require_approval_tools],
    };
  const base: JsonObject = input.workflow ? { ...input.workflow.input_data } : { prompt: task };
  const prior = base._runtime && typeof base._runtime === "object" && !Array.isArray(base._runtime) ? (base._runtime as JsonObject) : {};
  const input_data: JsonObject = { ...base, tools: [...input.tools.tools], _runtime: { ...prior, ...runtime } };
  const target: JsonObject = input.workflow
    ? { bundle_ref: input.workflow.bundle_ref, flow_id: input.workflow.flow_id, input_data }
    : { flow_id: "@default", interface: AUTOMATION_INTERFACE, input_data };
  const context: JsonObject = { mode: input.buildsOnEarlierRuns ? "growing" : "independent" };
  if (input.buildsOnEarlierRuns && input.growingMaxTokens && input.growingMaxTokens > 0) context.growing = { max_tokens: input.growingMaxTokens };
  const asks = (input.tools.tool_policy?.require_approval_tools.length ?? 0) > 0;
  return {
    request_id: input.requestId,
    title: titleOfTask(task),
    target,
    trigger: {
      source_id: "schedule",
      source_version: 2,
      config: input.when.kind === "every" ? { kind: "every", every: input.when.every } : { kind: "daily", at: input.when.at },
    },
    context,
    policy: { tool_approval: asks ? "ask" : "auto" },
  };
}

/** A whole number of tokens typed in ("50,000" and "50 000" allowed), or null. */
export function tokensOf(text: string): number | null {
  const digits = text.replace(/[\s,.'’]/g, "");
  if (!/^[0-9]+$/.test(digits)) return null;
  const n = Number(digits);
  return Number.isSafeInteger(n) && n > 0 ? n : null;
}

/**
 * An automation's runs as the conversation's messages (the watch's orb page): what its trigger
 * sent, then the answer, oldest first, the latest `RUNS_SHOWN`. A run that failed says so; one in
 * progress or waiting for you says that instead of an answer.
 */
export function runMessages(rows: OccurrenceRow[]): ChatMessage[] {
  const views = occurrenceViews(rows).slice(-RUNS_SHOWN);
  const out: ChatMessage[] = [];
  for (const v of views) {
    const r = v.row;
    if (r.user_turn.trim()) out.push({ id: `run:${r.run_id}:asked`, role: "user", title: "Task", content: r.user_turn, ts: r.fired_at, runId: r.run_id });
    const failed = v.tone === "failed";
    const content = failed
      ? `It failed${r.failure?.message ? `: ${r.failure.message}` : "."}`
      : v.tone === "waiting"
        ? "Waiting for you."
        : v.tone === "running"
          ? "Working…"
          : r.status === "cancelled"
            ? "Stopped."
            : r.answer.trim() || "It finished without a written answer.";
    out.push({ id: `run:${r.run_id}`, role: "assistant", title: "Assistant", content, ts: r.finished_at || r.fired_at, runId: r.run_id, ...(failed ? { level: "error" as const } : {}) });
  }
  return out;
}

/** The newest run the page can talk about (`POST /discuss` needs a run that happened), or null. */
export function latestDiscussable(rows: OccurrenceRow[]): number | null {
  const indexes = occurrenceViews(rows).filter((v) => v.canDiscuss).map((v) => v.row.index);
  return indexes.length ? Math.max(...indexes) : null;
}

/** The run of the page that waits for you (the newest), or null. */
export function waitingRun(rows: OccurrenceRow[]): OccurrenceRow | null {
  const waiting = occurrenceViews(rows).filter((v) => v.tone === "waiting");
  return waiting.length ? waiting[waiting.length - 1].row : null;
}

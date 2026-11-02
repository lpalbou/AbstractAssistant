import {
  apiErrorText,
  createAutomationsClient,
  isApiError,
  normalizeToolCatalog,
  waitToolCalls,
  type AttentionWait,
  type AutomationCommandType,
  type AutomationSummary,
  type AutomationsClient,
  type ToolCatalogItem,
} from "@abstractframework/ui-kit";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { GatewayClient } from "../gateway/client";
import { allowedByApproveAll, automationToolModes, automationTrust, trustedAutomations } from "../lib/automation_tools";
import type { AutomationsListing } from "../lib/automations";

/** The list is read at most once a minute (the watch's), and at once after an action. */
export const AUTOMATIONS_POLL_MS = 60_000;

/** One plain sentence for a failed call (the kit's words for the gateway's error codes). */
export function automationErrorText(error: unknown): string {
  if (isApiError(error)) {
    const t = apiErrorText(error);
    return t.detail ? `${t.title} ${t.detail}` : t.title;
  }
  const inner = (error as { error?: unknown } | null)?.error;
  if (isApiError(inner)) return automationErrorText(inner);
  return error instanceof Error ? error.message : String(error);
}

/** The kit's automations client over this app's gateway fetch (its credentials and CSRF header). */
export function assistantAutomationsClient(client: GatewayClient): AutomationsClient {
  return createAutomationsClient({ fetch: client.fetchGateway, baseUrl: "" });
}

/** Answers a tool approval of an automation's run (`resume` with `{approved}`), as the watch does. */
export async function answerToolWait(client: GatewayClient, wait: Pick<AttentionWait, "run_id" | "wait_key">, approved: boolean): Promise<void> {
  await client.submitCommand({ command_id: crypto.randomUUID(), run_id: wait.run_id, type: "resume", payload: { wait_key: wait.wait_key, payload: { approved } } });
}

/** The gateway's tools (its offer and defaults), read at most every 10 minutes. */
export function useToolCatalog(client: GatewayClient) {
  const cache = useRef<{ at: number; items: ToolCatalogItem[] } | null>(null);
  return useCallback(async (): Promise<ToolCatalogItem[]> => {
    if (cache.current && Date.now() - cache.current.at < 600_000) return cache.current.items;
    const items = normalizeToolCatalog(await client.discoveryTools());
    cache.current = { at: Date.now(), items };
    return items;
  }, [client]);
}

export type AutomationsState = {
  /** The first page as served (its order, `section`, counts); null until read. */
  page: AutomationsListing | null;
  error: string;
  loading: boolean;
  /** The archived ones (`status=archived`), read when Archived is opened; null until then. */
  archived: AutomationSummary[] | null;
  archivedError: string;
};

/** The person's automations (ADR 0048 order), read again every minute while the app is open. */
export function useAutomations(client: GatewayClient, trustScope: string) {
  const api = useMemo(() => assistantAutomationsClient(client), [client]);
  const catalog = useToolCatalog(client);
  const decided = useRef(new Set<string>());

  /**
   * "Allowed for its runs" (the watch's poll): a tool approval of a run of an automation whose
   * Approve all covers every call is answered by this browser, once, whoever sees it first. True
   * when one was answered (the list is then read again).
   */
  const approveTrusted = useCallback(async (items: AutomationSummary[]): Promise<boolean> => {
    const trusted = new Set(trustedAutomations(trustScope));
    const waiting = items.filter((s) => trusted.has(s.automation_id) && s.attention.waits.some((w) => w.kind === "tool_approval"));
    if (!waiting.length) return false;
    let answered = false;
    const tools = await catalog();
    for (const s of waiting) {
      const modes = automationToolModes(tools, (await api.getAutomation(s.automation_id)).definition);
      const trust = automationTrust(trustScope, s.automation_id);
      for (const w of s.attention.waits) {
        const key = `${w.run_id}|${w.wait_key}`;
        const calls = waitToolCalls(w)?.map((c) => c.name) ?? [];
        if (decided.current.has(key) || !allowedByApproveAll(modes, trust, calls)) continue;
        decided.current.add(key);
        await answerToolWait(client, w, true);
        answered = true;
      }
    }
    return answered;
  }, [api, catalog, client, trustScope]);
  const [state, setState] = useState<AutomationsState>({ page: null, error: "", loading: true, archived: null, archivedError: "" });
  const archivedWanted = useRef(false);
  const seq = useRef(0);

  const loadArchived = useCallback(async () => {
    archivedWanted.current = true;
    try {
      const page = await api.listAutomations({ status: "archived", limit: 200 });
      setState((s) => ({ ...s, archived: page.items, archivedError: "" }));
    } catch (error) {
      setState((s) => ({ ...s, archivedError: automationErrorText(error) }));
    }
  }, [api]);

  const refresh = useCallback(async () => {
    const mine = ++seq.current;
    setState((s) => ({ ...s, loading: true }));
    try {
      let page = (await api.listAutomations({ limit: 50 })) as AutomationsListing;
      if (mine !== seq.current) return;
      // A failure here leaves the request for the person (it shows as Needs you).
      if (await approveTrusted(page.items).catch(() => false)) page = (await api.listAutomations({ limit: 50 })) as AutomationsListing;
      if (mine !== seq.current) return;
      setState((s) => ({ ...s, page, error: "", loading: false }));
      if (archivedWanted.current) void loadArchived();
    } catch (error) {
      if (mine !== seq.current) return;
      setState((s) => ({ ...s, error: automationErrorText(error), loading: false }));
    }
  }, [api, loadArchived, approveTrusted]);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => {
      if (typeof document === "undefined" || document.visibilityState !== "hidden") void refresh();
    }, AUTOMATIONS_POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  /** A command (`automation.archive`, …), then the list read again. Rejects with the reason. */
  const command = useCallback(
    async (id: string, type: AutomationCommandType) => {
      await api.sendAutomationCommand(id, { type });
      await refresh();
    },
    [api, refresh],
  );

  /** A fresher row for one automation (its page knows first that it runs or has finished). */
  const replace = useCallback((row: AutomationSummary) => {
    setState((s) => (s.page ? { ...s, page: { ...s.page, items: s.page.items.map((r) => (r.automation_id === row.automation_id ? row : r)) } } : s));
  }, []);

  return { api, client, catalog, trustScope, approveTrusted, state, refresh, loadArchived, command, replace };
}

export type Automations = ReturnType<typeof useAutomations>;

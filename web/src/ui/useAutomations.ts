import { apiErrorText, createAutomationsClient, isApiError, type AutomationCommandType, type AutomationSummary, type AutomationsClient } from "@abstractframework/ui-kit";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { GatewayClient } from "../gateway/client";
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
export function useAutomations(client: GatewayClient) {
  const api = useMemo(() => assistantAutomationsClient(client), [client]);
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
      const page = (await api.listAutomations({ limit: 50 })) as AutomationsListing;
      if (mine !== seq.current) return;
      setState((s) => ({ ...s, page, error: "", loading: false }));
      if (archivedWanted.current) void loadArchived();
    } catch (error) {
      if (mine !== seq.current) return;
      setState((s) => ({ ...s, error: automationErrorText(error), loading: false }));
    }
  }, [api, loadArchived]);

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

  return { api, state, refresh, loadArchived, command, replace };
}

export type Automations = ReturnType<typeof useAutomations>;

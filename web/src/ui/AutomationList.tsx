import { Icon, type AutomationSummary } from "@abstractframework/ui-kit";
import { useState, type ReactNode } from "react";
import { AutomationCard } from "../vendor/abstractsessions/session_cards.js";
import "../vendor/abstractsessions/session_cards.css";

import { automationSections } from "../lib/automations";
import { automationErrorText, type Automations } from "./useAutomations";

/**
 * The automations, as the watch lists them (ADR 0048): New and a search on top, the active ones in
 * the gateway's order, then "Paused · N" and "Archived · N", each folded until opened. A card opens
 * the automation; its archive button asks first. AbstractUIC owns the card.
 */
export function AutomationList(props: {
  automations: Automations;
  heading: ReactNode;
  activeId: string;
  onOpen: (s: AutomationSummary) => void;
  onNew: () => void;
  onSettings: () => void;
}) {
  const { state, command, loadArchived, refresh } = props.automations;
  // The first page (50), as the watch reads it: with more automations than that, the paused ones
  // past it are counted ("Paused · N", the gateway's figure) but not listed.
  const [query, setQuery] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState("");
  const [problem, setProblem] = useState("");
  const [pausedOpen, setPausedOpen] = useState(false);
  const [archivedOpen, setArchivedOpen] = useState(false);
  const now = Date.now();
  const sections = automationSections(state.page);
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const matches = (s: AutomationSummary) => words.every((w) => (s.title || "").toLowerCase().includes(w));
  const searching = words.length > 0;
  const main = sections.main.filter(matches);
  const paused = sections.paused.filter(matches);

  const act = async (id: string, run: () => Promise<void>) => {
    setBusy(id);
    setProblem("");
    try {
      await run();
    } catch (error) {
      setProblem(automationErrorText(error));
    } finally {
      setBusy("");
    }
  };

  const card = (s: AutomationSummary) => (
    <li key={s.automation_id}>
      <AutomationCard className="aa-automation" summary={s} selected={s.automation_id === props.activeId} nowMs={now}
        onOpen={() => props.onOpen(s)} onArchive={() => { setConfirm(s.automation_id); setProblem(""); }}
        archiveDisabled={busy === s.automation_id} />
      {confirm === s.automation_id && <div className="aa-archive-confirm">
        <p>Archive this automation? It stops running. Its history is kept and it can be restored.</p>
        <button type="button" disabled={busy === s.automation_id}
          onClick={() => void act(s.automation_id, async () => { await command(s.automation_id, "automation.archive"); setConfirm(""); })}>Archive</button>
        <button type="button" disabled={busy === s.automation_id} onClick={() => setConfirm("")}>Cancel</button>
      </div>}
    </li>
  );

  return (
    <div className="aa-sidebar" data-list="automations">
      <div className="aa-sidebar__top">
        {props.heading}
        <button type="button" className="aa-button aa-button--primary" onClick={props.onNew}>
          <Icon name="plus" size={16} /> New
        </button>
      </div>
      <label className="aa-search"><Icon name="chat" size={15} /><input aria-label="Search automations" placeholder="Find an automation" value={query} onChange={(e) => setQuery(e.target.value)} /></label>
      {state.error ? (
        <p className="aa-sidebar__error" role="alert">
          {state.error}{" "}
          <button type="button" className="aa-link" onClick={() => void refresh()}>Try again</button>
        </p>
      ) : null}
      {problem ? <p className="aa-sidebar__error" role="alert">{problem}</p> : null}
      <div className="aa-sidebar__list">
        {!state.page && state.loading ? <p className="aa-sidebar__more" role="status">Loading automations…</p> : null}
        <ul className="aa-sessions">{main.map(card)}</ul>
        {sections.pausedCount > 0 && (
          <section className="aa-fold" data-section="paused">
            <button type="button" className="aa-fold__toggle" aria-expanded={pausedOpen || (searching && paused.length > 0)}
              onClick={() => setPausedOpen((o) => !o)}>
              <Icon name="pause" size={14} /> Paused · {sections.pausedCount}
            </button>
            {(pausedOpen || (searching && paused.length > 0)) && <ul className="aa-sessions">{paused.map(card)}</ul>}
          </section>
        )}
        {sections.archivedCount > 0 && (
          <section className="aa-fold" data-section="archived">
            <button type="button" className="aa-fold__toggle" aria-expanded={archivedOpen}
              onClick={() => { const open = !archivedOpen; setArchivedOpen(open); if (open && state.archived === null) void loadArchived(); }}>
              <Icon name="archive" size={14} /> Archived · {sections.archivedCount}
            </button>
            {archivedOpen && (
              <ul className="aa-archived">
                {state.archived === null && !state.archivedError ? <li className="aa-sidebar__more" role="status">Loading…</li> : null}
                {state.archivedError ? <li className="aa-sidebar__error" role="alert">{state.archivedError}</li> : null}
                {(state.archived ?? []).map((s) => (
                  <li key={s.automation_id} className="aa-archived__row">
                    <span className="aa-archived__title" title={s.title}>{s.title || "Automation"}</span>
                    <button type="button" disabled={busy === s.automation_id}
                      onClick={() => void act(s.automation_id, async () => { await command(s.automation_id, "automation.unarchive"); await loadArchived(); })}>
                      {busy === s.automation_id ? "Restoring…" : "Restore"}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
        {state.page && !main.length && (searching ? !paused.length : !sections.pausedCount) ? (
          <p className="aa-sidebar__more">{searching ? "No automation holds these words." : "No automations yet."}</p>
        ) : null}
      </div>
      <div className="aa-sidebar__footer">
        <button type="button" onClick={props.onSettings}><Icon name="settings" size={16} /> Settings</button>
        <button type="button" onClick={() => void refresh()} aria-label="Refresh automations" title="Refresh automations"><Icon name="refresh" size={16} /></button>
      </div>
    </div>
  );
}

import { Icon } from "@abstractframework/ui-kit";
import { useState } from "react";
import { SessionCard, type SessionActivity } from "../vendor/abstractsessions/session_cards.js";
import "../vendor/abstractsessions/session_cards.css";

import { type SessionRow } from "../lib/session_fold";

/** Host navigation, search and grouping; AbstractUIC owns card presentation. */
export function SessionList(props: {
  rows: SessionRow[];
  activity: Record<string, SessionActivity>;
  isUnread: (row: SessionRow) => boolean;
  onArchive: (row: SessionRow) => Promise<void>;
  titles: Record<string, string>;
  truncated: boolean;
  error: string;
  /** One line about titles that could not be loaded. */
  notice: string;
  activeId: string;
  onOpen: (row: SessionRow) => void;
  onNew: () => void;
  onRefresh: () => void;
  onSettings: () => void;
}) {
  const [query, setQuery] = useState("");
  const [confirm, setConfirm] = useState("");
  const [archiving, setArchiving] = useState(false);
  const [archiveError, setArchiveError] = useState("");
  const now = Date.now();
  const today = new Date().setHours(0, 0, 0, 0);
  const yesterday = new Date(today); yesterday.setDate(yesterday.getDate() - 1);
  const filtered = props.rows.filter((row) => (props.titles[row.session_id] || "Untitled conversation").toLowerCase().includes(query.toLowerCase()));
  const group = (row: SessionRow) => props.activity[row.session_id]?.needsAttention ? "Needs you" : props.activity[row.session_id]?.working ? "In progress"
    : Date.parse(row.updated_at) >= today ? "Today" : Date.parse(row.updated_at) >= yesterday.getTime() ? "Yesterday" : "Earlier";
  const groups = ["Needs you", "In progress", "Today", "Yesterday", "Earlier"].map((name) => ({ name, rows: filtered.filter((r) => group(r) === name) })).filter((g) => g.rows.length);
  return (
    <div className="aa-sidebar">
      <div className="aa-sidebar__top">
        <span className="aa-sidebar__heading">Conversations</span>
        <button type="button" className="aa-button aa-button--primary" onClick={props.onNew}>
          <Icon name="plus" size={16} /> New
        </button>
      </div>
      <label className="aa-search"><Icon name="chat" size={15} /><input aria-label="Search conversations" placeholder="Find a conversation" value={query} onChange={(e) => setQuery(e.target.value)} /></label>
      {props.error ? (
        <p className="aa-sidebar__error" role="alert">
          {props.error}{" "}
          <button type="button" className="aa-link" onClick={props.onRefresh}>
            Try again
          </button>
        </p>
      ) : null}
      {props.notice ? <p className="aa-sidebar__more" role="status">{props.notice}</p> : null}
      <div className="aa-sidebar__list">
      {groups.map(({ name, rows }) => <section className="aa-session-group" key={name} aria-label={name}>
      <h2>{name}</h2>
      <ul className="aa-sessions">
        {rows.map((row) => {
          // An unloaded title is labelled as such (the list says why once, above).
          const title = props.titles[row.session_id] || "Untitled conversation";
          const activity = props.activity[row.session_id];
          return (
            <li key={row.session_id}>
              <SessionCard className="aa-session" sessionId={row.session_id} title={title} selected={row.session_id === props.activeId}
                unread={props.isUnread(row)} needsAttention={activity?.needsAttention} working={activity?.working}
                turnCount={row.turns} toolCount={activity?.toolCount} countsPartial={props.truncated} updatedAt={row.updated_at} nowMs={now}
                onOpen={() => props.onOpen(row)} onArchive={() => { setConfirm(row.session_id); setArchiveError(""); }}
                archiveDisabled={row.state === "waiting" || activity?.working || archiving} />
              {confirm === row.session_id && <div className="aa-archive-confirm">
                <p>Archive this conversation? It can be restored later.</p>
                <button type="button" disabled={archiving} onClick={async () => { setArchiving(true); try { await props.onArchive(row); setConfirm(""); } catch (e) { setArchiveError(e instanceof Error ? e.message : String(e)); } finally { setArchiving(false); } }}>Archive</button>
                <button type="button" disabled={archiving} onClick={() => setConfirm("")}>Cancel</button>
                {archiveError && <p role="alert">{archiveError}</p>}
              </div>}
            </li>
          );
        })}
      </ul>
      </section>)}
      {!filtered.length && <p className="aa-sidebar__more">{query ? "No conversations match." : "Your conversations will appear here."}</p>}
      {props.truncated ? <p className="aa-sidebar__more">Older conversations are not listed yet.</p> : null}
      </div>
      <div className="aa-sidebar__footer">
        <button type="button" onClick={props.onSettings}><Icon name="settings" size={16} /> Settings</button>
        <button type="button" onClick={props.onRefresh} aria-label="Refresh conversations" title="Refresh conversations"><Icon name="refresh" size={16} /></button>
      </div>
    </div>
  );
}

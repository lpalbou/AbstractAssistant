import { Icon, formatRelativeTime } from "@abstractframework/ui-kit";
import { useState } from "react";

import { STATE_WORDS, type SessionRow } from "../lib/session_fold";

/**
 * The conversations, as the shell's navigation (AfAppShell `nav`: docked from 1024 px, a
 * drawer below it). Sign-out lives in the top bar's identity menu and pill.
 *
 * Kit gap (backlog 0030 item 6, "sessions" / ChatSessionList, not built yet): this list stays
 * the app's until the kit has a session list.
 */
export function SessionList(props: {
  rows: SessionRow[];
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
  const now = Date.now();
  const today = new Date().setHours(0, 0, 0, 0);
  const yesterday = new Date(today); yesterday.setDate(yesterday.getDate() - 1);
  const filtered = props.rows.filter((row) => (props.titles[row.session_id] || "Untitled conversation").toLowerCase().includes(query.toLowerCase()));
  const group = (row: SessionRow) => row.state === "waiting" ? "Needs you" : row.state === "running" ? "In progress"
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
          const state = STATE_WORDS[row.state];
          return (
            <li key={row.session_id}>
              <button
                type="button"
                className={`aa-session${row.session_id === props.activeId ? " aa-session--active" : ""}`}
                aria-current={row.session_id === props.activeId ? "page" : undefined}
                onClick={() => props.onOpen(row)}
              >
                <span className="aa-session__title" title={title}>{title}</span>
                <span className="aa-session__meta">
                  {state ? <span className={`aa-state aa-state--${row.state}`}>{state}</span> : null}
                  <span>{row.updated_at ? formatRelativeTime(row.updated_at, now) : ""}</span>
                  <span>{row.turns === 1 ? "1 turn" : `${row.turns} turns`}</span>
                </span>
              </button>
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

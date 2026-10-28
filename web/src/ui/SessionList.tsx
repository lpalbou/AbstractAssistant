import { formatRelativeTime } from "@abstractframework/ui-kit";

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
}) {
  const now = Date.now();
  return (
    <div className="aa-sidebar">
      <div className="aa-sidebar__top">
        <span className="aa-sidebar__heading">Conversations</span>
        <button type="button" className="aa-button aa-button--primary" onClick={props.onNew}>
          New
        </button>
      </div>
      {props.error ? (
        <p className="aa-sidebar__error" role="alert">
          {props.error}{" "}
          <button type="button" className="aa-link" onClick={props.onRefresh}>
            Try again
          </button>
        </p>
      ) : null}
      {props.notice ? <p className="aa-sidebar__more" role="status">{props.notice}</p> : null}
      <ul className="aa-sessions">
        {props.rows.map((row) => {
          // An unloaded title is labelled as such (the list says why once, above).
          const title = props.titles[row.session_id] || "Untitled conversation";
          const state = STATE_WORDS[row.state];
          return (
            <li key={row.session_id}>
              <button
                type="button"
                className={`aa-session${row.session_id === props.activeId ? " aa-session--active" : ""}`}
                aria-current={row.session_id === props.activeId ? "true" : undefined}
                onClick={() => props.onOpen(row)}
              >
                <span className="aa-session__title">{title}</span>
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
      {props.truncated ? <p className="aa-sidebar__more">Older conversations are not listed yet.</p> : null}
    </div>
  );
}

import { formatRelativeTime } from "@abstractframework/ui-kit";

import type { SessionRow } from "../lib/session_fold";

const STATE_WORDS: Record<SessionRow["state"], string> = {
  waiting: "Needs you",
  running: "Working",
  failed: "Stopped or failed",
  done: "",
  unknown: "",
};

export function SessionList(props: {
  rows: SessionRow[];
  titles: Record<string, string>;
  truncated: boolean;
  error: string;
  activeId: string;
  onOpen: (row: SessionRow) => void;
  onNew: () => void;
  onRefresh: () => void;
  onSignOut: () => void;
}) {
  const now = Date.now();
  return (
    <nav className="aa-sidebar" aria-label="Conversations">
      <div className="aa-sidebar__top">
        <span className="aa-brand">Assistant</span>
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
      <ul className="aa-sessions">
        {props.rows.map((row) => {
          const title = props.titles[row.session_id] || "Conversation";
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
      <div className="aa-sidebar__bottom">
        <button type="button" className="aa-link" onClick={props.onSignOut}>
          Sign out
        </button>
      </div>
    </nav>
  );
}

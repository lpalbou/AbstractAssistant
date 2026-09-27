"""The session list, as the gateway knows it.

The gateway is the only source of truth for which sessions exist: a session is
the set of ROOT runs that carry the same ``session_id``. This module turns one
``GET /api/gateway/runs`` page into one row per session, with the rules
AbstractCode uses (``abstractcode/tui/src/runner.rs`` ``fold_session_rows``,
``abstractcode/web/src/workspace/catalog.ts`` ``normalizeSessionSummaries``) —
divergence from those is a bug in one of the three:

- a run without a ``session_id`` (or without a ``run_id``) is not a session;
- a run whose ``session_kind`` is ``automation`` or ``occurrence`` is not a
  REGULAR session: those are listed under the Automations section (grouped by
  ``automation_id``), never here. ``chat`` and ``discussion`` stay; a row
  without ``session_kind`` (a gateway that does not stamp it) is a chat. The
  kind is the gateway's own stamp — never inferred from an id prefix;
- a child run (``parent_run_id`` set) is never a turn;
- turns = the root runs of the session in the page;
- recency = the newest ``updated_at`` (``created_at`` when absent) — the field
  the gateway pages on, so the order matches the page's membership;
- state = the liveliest run: waiting > running > failed/cancelled > completed;
  a status the gateway did not report is ``unknown``, never "done";
- the first run (oldest ``created_at``) is where the session's opening prompt
  lives; the latest run (newest ``created_at``) is the one whose history bundle
  carries every turn up to it (``include_session`` stops at that run's
  ``created_at``), so it anchors the transcript;
- ``has_more`` other than an explicit ``false`` means the page is truncated:
  a session missing from it is not provably absent.

Synthetic ``__session_memory__`` runs never reach this fold: the listing drops
internal workflows server-side unless a ``workflow_id`` filter is sent.

Pure and Qt-free, so it is tested from JSON fixtures without a gateway.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .automations import is_regular_session_kind
from .session_digest import parse_timestamp

__all__ = [
    "SESSION_PAGE_RUNS",
    "SESSION_PAGE_SESSIONS",
    "SESSION_PROMPT_MAX",
    "GatewaySession",
    "fold_session_rows",
    "prompt_from_input_data",
]

# The session list reads `/runs` in pages of SESSION_PAGE_RUNS turn roots
# (`offset` paging, `has_more` says whether a next page exists) and shows
# SESSION_PAGE_SESSIONS sessions at a time; "Load more" reads further pages
# until SESSION_PAGE_SESSIONS more sessions (or the end). Every gateway session
# of kind chat or discussion is listed, whichever client started it.
SESSION_PAGE_RUNS = 200
SESSION_PAGE_SESSIONS = 100
# How many sessions' opening prompts one refresh fetches (one request each),
# newest first — AbstractCode's SESSION_PROMPT_MAX. Fetched prompts are cached,
# so the next refresh continues where this one stopped.
SESSION_PROMPT_MAX = 40

_STATE_RANK = {"waiting": 4, "running": 3, "failed": 2, "done": 1, "unknown": 0}
_STATUS_TO_STATE = {
    "waiting": "waiting",
    "running": "running",
    "failed": "failed",
    "cancelled": "failed",
    "completed": "done",
}
_FLOOR = datetime.min.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class GatewaySession:
    """One session row, folded from the gateway's root runs."""

    session_id: str
    state: str = "unknown"
    updated_at: str = ""
    created_at: str = ""
    first_run_id: str = ""
    latest_run_id: str = ""
    turns: int = 0
    # The gateway's `session_kind` of the session's turns ("" = not stamped,
    # i.e. a chat) and, for a discussion, the automation it is about.
    session_kind: str = ""
    automation_id: str = ""
    # The latest turn's workspace folder, from the gateway's `/runs` row
    # (`workspace_root`); `workspace_reported` = the row carries that field at
    # all (older gateways do not).
    workspace_root: str = ""
    workspace_reported: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "state": self.state,
            "updated_at": self.updated_at,
            "created_at": self.created_at,
            "first_run_id": self.first_run_id,
            "latest_run_id": self.latest_run_id,
            "turns": int(self.turns),
            "session_kind": self.session_kind,
            "automation_id": self.automation_id,
            "workspace_root": self.workspace_root,
            "workspace_reported": self.workspace_reported,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> Optional["GatewaySession"]:
        if not isinstance(raw, dict):
            return None
        sid = str(raw.get("session_id") or "").strip()
        if not sid:
            return None
        state = str(raw.get("state") or "unknown")
        try:
            turns = max(0, int(raw.get("turns") or 0))
        except Exception:
            turns = 0
        return cls(
            session_id=sid,
            state=state if state in _STATE_RANK else "unknown",
            updated_at=str(raw.get("updated_at") or ""),
            created_at=str(raw.get("created_at") or ""),
            first_run_id=str(raw.get("first_run_id") or ""),
            latest_run_id=str(raw.get("latest_run_id") or ""),
            turns=turns,
            session_kind=str(raw.get("session_kind") or ""),
            automation_id=str(raw.get("automation_id") or ""),
            workspace_root=str(raw.get("workspace_root") or ""),
            workspace_reported=bool(raw.get("workspace_reported")),
        )


def _text(value: Any) -> str:
    return str(value).strip() if isinstance(value, str) else ""


def _state_for(run: Dict[str, Any]) -> str:
    return _STATUS_TO_STATE.get(_text(run.get("status")).lower(), "unknown")


def _activity(run: Dict[str, Any]) -> str:
    return _text(run.get("updated_at")) or _text(run.get("created_at"))


def _created(run: Dict[str, Any]) -> str:
    return _text(run.get("created_at")) or _activity(run)


def _when(value: str) -> datetime:
    return parse_timestamp(value) or _FLOOR


def fold_session_rows(payload: Any) -> Tuple[List[GatewaySession], bool]:
    """Fold one ``/runs`` page into session rows, newest first.

    Returns ``(rows, truncated)``.
    """
    body = payload if isinstance(payload, dict) else {}
    items = body.get("items")
    if not isinstance(items, list):
        items = body.get("runs") if isinstance(body.get("runs"), list) else []
    truncated = body.get("has_more") is not False

    groups: Dict[str, List[Tuple[int, Dict[str, Any]]]] = {}
    for index, run in enumerate(items):
        if not isinstance(run, dict):
            continue
        if not is_regular_session_kind(_text(run.get("session_kind"))):
            continue
        if _text(run.get("parent_run_id")):
            continue
        sid = _text(run.get("session_id"))
        rid = _text(run.get("run_id"))
        if not sid or not rid:
            continue
        groups.setdefault(sid, []).append((index, run))

    rows: List[GatewaySession] = []
    for sid, group in groups.items():
        state = "unknown"
        for _index, run in group:
            candidate = _state_for(run)
            if _STATE_RANK[candidate] > _STATE_RANK[state]:
                state = candidate
        # Ties go to the earlier position in the page (the listing is
        # newest-first), as in the web fold.
        newest = max(group, key=lambda entry: (_when(_activity(entry[1])), -entry[0]))[1]
        oldest = min(group, key=lambda entry: (_when(_created(entry[1])), entry[0]))[1]
        latest = max(group, key=lambda entry: (_when(_created(entry[1])), -entry[0]))[1]
        kind = next((_text(run.get("session_kind")) for _i, run in group if _text(run.get("session_kind"))), "")
        automation_id = next((_text(run.get("automation_id")) for _i, run in group if _text(run.get("automation_id"))), "")
        rows.append(
            GatewaySession(
                session_id=sid,
                state=state,
                updated_at=_activity(newest),
                created_at=_created(oldest),
                first_run_id=_text(oldest.get("run_id")),
                latest_run_id=_text(latest.get("run_id")),
                turns=len(group),
                session_kind=kind,
                automation_id=automation_id if kind == "discussion" else "",
                workspace_root=_text(latest.get("workspace_root")),
                workspace_reported="workspace_root" in latest,
            )
        )
    # Newest first by the field the gateway paged on; ties by id (stable).
    rows.sort(key=lambda row: row.session_id)
    rows.sort(key=lambda row: _when(row.updated_at), reverse=True)
    return rows, truncated


def prompt_from_input_data(payload: Any) -> str:
    """The prompt a run was started with, from ``GET /runs/{id}/input_data``.

    The same read AbstractCode's session board does (`input_data.prompt`, or a
    bare `prompt` on older gateways), plus `context.task` — where this client's
    own run input also carries it (`gateway/run_input.py`).
    """
    body = payload if isinstance(payload, dict) else {}
    for node in (body.get("input_data"), body):
        if not isinstance(node, dict):
            continue
        prompt = _text(node.get("prompt"))
        if prompt:
            return prompt
        context = node.get("context")
        if isinstance(context, dict):
            task = _text(context.get("task"))
            if task:
                return task
    return ""

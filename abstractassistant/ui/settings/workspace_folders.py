"""Workspace folders (round 9): the same folder model and words as the web.

The gateway decides everything (R9 workspace API):
``GET/PUT /api/gateway/workspace/policy/me`` answers
``{policy: {enabled_folders, own_folders}, gateway: {...}, effective: {...}}``;
a refused folder is a 4xx whose sentence is shown with "Not saved.".

This module is the Qt-free half of Settings → Workspace: the wording table
(a VERBATIM copy of the ui-kit's ``WORKSPACE_CHOOSER_TEXT``, AbstractUIC
``ui-kit/src/workspace_chooser_core.ts`` — the console, AbstractCode and this
app show exactly these strings) and the mapping from the gateway's answer to
rows and from a click to the PUT body. No policy logic: no path checks, no
clamp, no deny list. A folder can only become a switch when the gateway
listed it in ``available_folders``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

WORKSPACE_CHOOSER_TEXT: Dict[str, str] = {
    "title": "Workspace folders",
    "help": "The folders agents may use. The shared workspace is always on; other folders the gateway admin allows can be turned on.",
    "sharedLabel": "Shared workspace",
    "sharedState": "Always on",
    "sharedHelp": "Every agent can always use it. Each conversation also keeps a private folder of its own.",
    "neverAllowed": "Never allowed on this gateway.",
    "allowedTitle": "Allowed folders",
    "allowedHelp": "Allowed by the gateway admin. Off until turned on.",
    "allowedEmpty": "The gateway admin has not allowed other folders.",
    "ownTitle": "My folders",
    "ownHelp": "Folders of this account. The gateway admin allows any folder.",
    "ownHidden": "My folders appear when the gateway admin allows any folder.",
    "ownInactive": "My folders are kept but unused until the gateway admin allows any folder again.",
    "ownEmpty": "No folders added yet.",
    "ownPlaceholder": "/absolute/path/to/folder",
    "add": "Add",
    "remove": "Remove",
    "effectivePrefix": "Agents may use:",
    "saved": "Saved",
    "notSaved": "Not saved.",
    "automationHelp": "The folders this automation's runs may use, chosen among this account's folders.",
    "automationFollows": "Follows this account's folders.",
    "automationUseAccount": "Use this account's folders",
    "automationOwnHidden": "Add folders of your own in the account's workspace settings.",
}

T = WORKSPACE_CHOOSER_TEXT


def folder_name(path: str) -> str:
    """The last path segment (the row's name); the full path is shown under it."""
    parts = [p for p in str(path or "").replace("\\", "/").split("/") if p]
    return parts[-1] if parts else str(path or "")


@dataclass(frozen=True)
class FolderRow:
    path: str
    name: str
    on: bool
    blocked: bool = False  # the gateway marks it never allowed: shown, not switchable


@dataclass(frozen=True)
class WorkspaceView:
    shared_path: str
    extras: List[FolderRow]
    own_visible: bool
    own_rows: List[str]
    own_note: Optional[str]
    summary: str


class WorkspaceAnswerError(ValueError):
    """The gateway answered without the round-9 workspace model."""


def parse_state(payload: Any) -> Dict[str, Any]:
    """``{policy, effective}`` from a GET/PUT answer; fails loudly on an older gateway."""
    data = payload if isinstance(payload, dict) else {}
    effective = data.get("effective")
    if not isinstance(effective, dict) or not isinstance(effective.get("shared_workspace"), str):
        raise WorkspaceAnswerError("The gateway answered without a workspace policy (it needs the round-9 workspace model).")
    policy = data.get("policy") if isinstance(data.get("policy"), dict) else {}
    return {
        "policy": {
            "enabled_folders": [str(p) for p in (policy.get("enabled_folders") or [])],
            "own_folders": [str(p) for p in (policy.get("own_folders") or [])],
        },
        "effective": dict(effective),
    }


def account_view(state: Dict[str, Any]) -> WorkspaceView:
    eff = state["effective"]
    own = list(state.get("policy", {}).get("own_folders") or [])
    allowed = eff.get("own_folders_allowed") is True
    if allowed:
        note = None
    elif eff.get("own_folders_inactive") and own:
        note = T["ownInactive"]
    else:
        note = T["ownHidden"]
    return WorkspaceView(
        shared_path=str(eff.get("shared_workspace") or ""),
        extras=[
            FolderRow(
                path=str(f.get("path") or ""),
                name=folder_name(str(f.get("path") or "")),
                on=f.get("enabled") is True,
                blocked=f.get("never_allowed") is True,
            )
            for f in (eff.get("available_folders") or [])
            if isinstance(f, dict)
        ],
        own_visible=allowed,
        own_rows=own if allowed else [],
        own_note=note,
        summary=str(eff.get("summary") or ""),
    )


def extra_body(view: WorkspaceView, path: str, on: bool) -> Dict[str, List[str]]:
    """The PUT body for one switch, built from the rows shown (only listed folders)."""
    return {"enabled_folders": [r.path for r in view.extras if (on if r.path == path else r.on)]}


def add_own_body(state: Dict[str, Any], path: str) -> Dict[str, List[str]]:
    return {"own_folders": list(state["policy"]["own_folders"]) + [str(path).strip()]}


def remove_own_body(state: Dict[str, Any], path: str) -> Dict[str, List[str]]:
    return {"own_folders": [p for p in state["policy"]["own_folders"] if p != path]}


def refusal(error: Any) -> str:
    """The gateway's sentence + "Not saved."."""
    sentence = str(getattr(error, "body_text", "") or "").strip() or str(error or "").strip() or "The gateway refused the change."
    if sentence.startswith("{"):
        sentence = str(error or "").strip() or sentence
    end = "" if sentence[-1:] in ".!?" else "."
    return f"{sentence}{end} {T['notSaved']}"


def effective_line(view: WorkspaceView) -> str:
    return f"{T['effectivePrefix']} {view.summary}".strip()


__all__ = [
    "WORKSPACE_CHOOSER_TEXT",
    "FolderRow",
    "WorkspaceView",
    "WorkspaceAnswerError",
    "parse_state",
    "account_view",
    "extra_body",
    "add_own_body",
    "remove_own_body",
    "refusal",
    "effective_line",
    "folder_name",
]

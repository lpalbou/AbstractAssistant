"""Workspaces (round 9 FINAL wording): the same model and words as the web.

Two dimensions only: the gateway's posture — "Deny everything, allow listed
workspaces" or "Allow everything, refuse listed workspaces" (everything at
ONE default mode) — and, per workspace, Read & write / Read-only / Refused.
The shared workspace is always in, Read & write. Accounts narrow only.

The gateway decides everything (R9 WORKSPACE API — FINAL):
``GET/PUT /api/gateway/workspace/policy/me`` answers ``{policy: {account,
default_mode, folders}, gateway: {...}, effective: {...}}``; a write is
``{folders: [{path, mode: "ro"|"deny"}]}`` or ``{default_mode: "ro"|null}``;
a refused change is a 4xx whose sentence is shown with "Not saved.".

This module is the Qt-free half of Settings → Workspace: the wording table
(a VERBATIM copy of the ui-kit's ``WORKSPACE_CHOOSER_TEXT``, AbstractUIC
``ui-kit/src/workspace_chooser_core.ts`` — the console, AbstractCode and this
app show exactly these strings) and the mapping from the gateway's answer to
rows and from a click to the PUT body. No policy logic: no path checks, no
clamp; the effective line is the gateway's own ``summary``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

WORKSPACE_CHOOSER_TEXT: Dict[str, str] = {
    "title": "Workspaces",
    "help": "Which workspaces agents may use, and how.",
    "postureAllowedOnly": "Deny everything, allow listed workspaces",
    "postureAllowedOnlyHelp": "Agents may use the shared workspace and the allowed workspaces, nothing else.",
    "postureAnyExceptDenied": "Allow everything, refuse listed workspaces",
    "postureAnyExceptDeniedHelp": "Agents may use any workspace at the default mode, except the refused ones.",
    "sharedLabel": "Shared workspace",
    "sharedState": "Always on",
    "sharedHelp": "Every agent can always use it, read and write.",
    "accessLabel": "Permission",
    "accessRead": "Read-only",
    "accessReadWrite": "Read & write",
    "accessDenied": "Refused",
    "accessCeiling": "The gateway admin allows read only.",
    "everythingElse": "Everything else",
    "foldersTitle": "Workspaces",
    "allowedTitle": "Allowed workspaces",
    "deniedTitle": "Refused workspaces",
    "policyTitle": "Gateway policy",
    "adminOnlyAdds": "While everything is denied, only the gateway admin can add workspaces.",
    "addPlaceholder": "Add a workspace path",
    "add": "Add",
    "remove": "Remove",
    "saved": "Saved",
    "notSaved": "Not saved.",
    "automationHelp": "The workspaces this automation's runs may use, chosen among this account's workspaces.",
    "runHelp": "The workspaces this run may use, chosen among this account's workspaces.",
    "automationFollows": "Follows this account's workspaces.",
    "automationUseAccount": "Use this account's workspaces",
}

T = WORKSPACE_CHOOSER_TEXT
MODES = ("ro", "rw", "deny")
_ORDER = {"deny": 0, "ro": 1, "rw": 2}


def folder_name(path: str) -> str:
    """The last path segment; the full path is shown with it."""
    parts = [p for p in str(path or "").replace("\\", "/").split("/") if p]
    return parts[-1] if parts else str(path or "")


def mode_label(mode: str) -> str:
    return T["accessRead"] if mode == "ro" else T["accessDenied"] if mode == "deny" else T["accessReadWrite"]


def posture_label(posture: str) -> str:
    return T["postureAnyExceptDenied"] if posture == "any_except_denied" else T["postureAllowedOnly"]


def _narrowing(ceiling: str) -> List[str]:
    """The choices at and below a ceiling: rw -> rw, ro, deny; ro -> ro, deny; deny -> fixed."""
    if ceiling == "deny":
        return []
    return [m for m in ("rw", "ro", "deny") if _ORDER[m] <= _ORDER[ceiling]]


@dataclass(frozen=True)
class FolderRow:
    path: str
    name: str
    origin: str  # "gateway" (listed by the admin) or "account" (added by this account, posture b)
    admin_mode: str
    mode: str  # what applies now
    choices: tuple  # the modes the account may pick (narrowing only); empty = fixed


@dataclass(frozen=True)
class WorkspaceView:
    posture: str
    shared_path: str
    rows: List[FolderRow]
    everything_else: Optional[tuple]  # (mode, choices) under posture b
    can_add: bool
    summary: str


class WorkspaceAnswerError(ValueError):
    """The gateway answered without the round-9 workspace model."""


def _is_rules(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(r, dict) and isinstance(r.get("path"), str) and r.get("mode") in MODES for r in value)


def parse_state(payload: Any) -> Dict[str, Any]:
    """``{policy, gateway, effective}`` from a GET/PUT answer; fails loudly on an older gateway."""
    data = payload if isinstance(payload, dict) else {}
    e, g, p = data.get("effective"), data.get("gateway"), data.get("policy")
    ok = (
        isinstance(e, dict)
        and isinstance(e.get("shared_workspace"), str)
        and e.get("posture") in ("allowed_only", "any_except_denied")
        and (e.get("default_mode") is None or e.get("default_mode") in ("ro", "rw"))
        and _is_rules(e.get("folders"))
        and isinstance(e.get("summary"), str)
        and isinstance(g, dict)
        and isinstance(g.get("shared_workspace"), str)
        and g.get("posture") in ("allowed_only", "any_except_denied")
        and g.get("default_mode") in ("ro", "rw")
        and _is_rules(g.get("folders"))
        and isinstance(p, dict)
        and p.get("default_mode") in (None, "ro")
        and _is_rules(p.get("folders") or [])
    )
    if not ok:
        raise WorkspaceAnswerError("The gateway answered without a workspace policy (it needs the round-9 workspace model).")
    return {
        "policy": {"default_mode": p.get("default_mode"), "folders": [dict(r) for r in (p.get("folders") or []) if r.get("mode") in ("ro", "deny")]},
        "gateway": dict(g),
        "effective": dict(e),
    }


def account_view(state: Dict[str, Any]) -> WorkspaceView:
    gw, eff = state["gateway"], state["effective"]
    account_rules = {r["path"]: r["mode"] for r in state["policy"]["folders"]}
    eff_modes = {f["path"]: f["mode"] for f in eff.get("folders") or []}
    rows = [
        FolderRow(
            path=r["path"],
            name=folder_name(r["path"]),
            origin="gateway",
            admin_mode=r["mode"],
            mode=eff_modes.get(r["path"], account_rules.get(r["path"], r["mode"])),
            choices=tuple(_narrowing(r["mode"])),
        )
        for r in gw.get("folders") or []
    ]
    listed = {r["path"] for r in gw.get("folders") or []}
    posture_b = gw.get("posture") == "any_except_denied"
    if posture_b:
        for r in state["policy"]["folders"]:
            if r["path"] in listed:
                continue
            rows.append(
                FolderRow(
                    path=r["path"],
                    name=folder_name(r["path"]),
                    origin="account",
                    admin_mode=gw["default_mode"],
                    mode=eff_modes.get(r["path"], r["mode"]),
                    choices=tuple(m for m in _narrowing(gw["default_mode"]) if m != "rw"),
                )
            )
    everything_else = None
    if posture_b:
        everything_else = (eff.get("default_mode") or gw["default_mode"], ("rw", "ro") if gw["default_mode"] == "rw" else ())
    return WorkspaceView(
        posture=str(gw.get("posture")),
        shared_path=str(eff.get("shared_workspace") or ""),
        rows=rows,
        everything_else=everything_else,
        can_add=posture_b,
        summary=str(eff.get("summary") or ""),
    )


def mode_body(state: Dict[str, Any], row: FolderRow, mode: str) -> Dict[str, List[Dict[str, str]]]:
    """PUT body for one row's choice; choosing the admin's mode removes the account rule (rw is never stored)."""
    others = [r for r in state["policy"]["folders"] if r["path"] != row.path]
    if mode == "rw" or (row.origin == "gateway" and mode == row.admin_mode):
        return {"folders": others}
    return {"folders": others + [{"path": row.path, "mode": mode}]}


def default_mode_body(mode: str) -> Dict[str, Optional[str]]:
    """Everything else (posture b): Read-only lowers the default, Read & write follows the admin."""
    return {"default_mode": "ro" if mode == "ro" else None}


def add_row_body(state: Dict[str, Any], path: str, mode: str) -> Dict[str, List[Dict[str, str]]]:
    return {"folders": list(state["policy"]["folders"]) + [{"path": str(path).strip(), "mode": mode}]}


def remove_row_body(state: Dict[str, Any], path: str) -> Dict[str, List[Dict[str, str]]]:
    return {"folders": [r for r in state["policy"]["folders"] if r["path"] != path]}


def refusal(error: Any) -> str:
    """The gateway's sentence + "Not saved."."""
    sentence = str(getattr(error, "body_text", "") or "").strip() or str(error or "").strip() or "The gateway refused the change."
    end = "" if sentence[-1:] in ".!?" else "."
    return f"{sentence}{end} {T['notSaved']}"


__all__ = [
    "WORKSPACE_CHOOSER_TEXT",
    "FolderRow",
    "WorkspaceView",
    "WorkspaceAnswerError",
    "parse_state",
    "account_view",
    "mode_body",
    "default_mode_body",
    "add_row_body",
    "remove_row_body",
    "mode_label",
    "posture_label",
    "refusal",
    "folder_name",
]

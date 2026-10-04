"""Workspaces (round 11, DESIGN "R11.1 FINAL"): the Qt-free half of
Settings → Workspace.

The gateway admin defines the ELIGIBLE workspaces, each with a CAP
(Read-only | Read & write | Refused). Below it, two levels the Assistant
edits, with the SAME shape and words:

- ACCOUNT — "My default workspaces": ``GET/PUT /api/gateway/workspace/policy/me``
  ``{account, configured, posture, default_mode, folders: [{path, mode}]}``;
  ``{configured: false}`` = "Follow the gateway policy".
- SESSION — "This chat": ``GET/PUT /api/gateway/sessions/{id}/workspaces``
  (same shape); ``{configured: false}`` = "Use my default". The gateway keeps it
  on the session, so every app opening the conversation sees the same choice,
  and applies it at run start (clamped to the eligible set).

Each GET/PUT answers ``{policy, gateway, effective, …}`` where ``effective``
(also ``GET /api/gateway/workspace/effective/me[?session=<id>]``) is
``{posture, default_mode, folders: [{path, mode, cap, source}], summary,
gateway_summary}`` and the session answer adds ``account_default``. The top line is "Gateway: <gateway_summary>" and the line
under the rows is ``summary``, both verbatim. A run's private workspace is
automatic and never listed here.

No policy logic: no path checks, no clamp. The only thing read from the
answer is each row's ``cap``, to show the modes above it disabled (the gateway
refuses them anyway). A refused change shows the gateway's sentence + "Not
saved.". The wording table mirrors the ui-kit WorkspaceChooser table
(AbstractUIC ``ui-kit/src/workspace_chooser_core.ts``) key for key.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# VERBATIM copy of the kit's WORKSPACE_CHOOSER_TEXT (ui-kit 0.8.3, uic 16175e1; unchanged since 0.8.2).
WORKSPACE_CHOOSER_TEXT: Dict[str, str] = {
    "title": "Workspaces",
    "gatewayTitle": "Eligible workspaces",
    "gatewayHelp": "The workspaces accounts may choose from, and the most each one allows.",
    "accountHelp": "The workspaces this account's agents use, among the eligible ones.",
    "sessionHelp": "The workspaces this conversation uses, among the eligible ones.",
    "runHelp": "The workspaces this run uses, among the eligible ones.",
    "gatewayPrefix": "Gateway:",
    "postureLabel": "Workspaces agents may use",
    "postureAllowedOnly": "Deny everything, allow listed workspaces",
    "postureAllowedOnlyHelp": "Agents may only work in the listed workspaces.",
    "postureAnyExceptDenied": "Allow everything, refuse listed workspaces",
    "postureAnyExceptDeniedHelp": "Agents may work in any workspace except the refused ones.",
    "accessLabel": "Permission",
    "accessRead": "Read-only",
    "accessReadWrite": "Read & write",
    "accessDenied": "Refused",
    "capReadOnly": "The gateway allows this workspace read-only",
    "capRefused": "The gateway refuses this workspace",
    "everythingElse": "Everything else",
    "allowedTitle": "Allowed workspaces",
    "deniedTitle": "Refused workspaces",
    "builtinRefused": "Always refused: the gateway's own data and credentials",
    "emptyAllowed": "No workspace is listed: agents only use their private workspace.",
    "privateNote": "The private workspace of each run is always available, read & write.",
    "addPlaceholder": "Add a workspace path",
    "add": "Add",
    "choose": "Choose…",
    "remove": "Remove",
    "followGateway": "Follow the gateway policy",
    "followGatewayHelp": "On: this account gets exactly what the gateway allows.",
    "useDefault": "Use my default",
    "useDefaultHelp": "On: the account's default workspaces apply.",
    "locked": "These workspaces can be seen here but not changed.",
    "loading": "Loading…",
    "saved": "Saved",
    "notSaved": "Not saved.",
}

# The Assistant's two sections (Settings → Workspace); the help lines are the kit's.
ACCOUNT_TITLE = "My default workspaces"
SESSION_TITLE = "This chat"

T = WORKSPACE_CHOOSER_TEXT
POSTURES = ("allowed_only", "any_except_denied")
MODES = ("rw", "ro", "deny")  # the kit's order: Read & write | Read-only | Refused
_RANK = {"deny": 0, "ro": 1, "rw": 2}


class WorkspaceAnswerError(ValueError):
    """The gateway answered without the round-11 workspace model."""


def mode_label(mode: str) -> str:
    return T["accessRead"] if mode == "ro" else T["accessDenied"] if mode == "deny" else T["accessReadWrite"]


def posture_label(posture: str) -> str:
    return T["postureAnyExceptDenied"] if posture == "any_except_denied" else T["postureAllowedOnly"]


def posture_help(posture: str) -> str:
    return T["postureAnyExceptDeniedHelp"] if posture == "any_except_denied" else T["postureAllowedOnlyHelp"]


def gateway_line(effective: Dict[str, Any]) -> str:
    """"Gateway: <gateway_summary>" (the kit's gatewayPrefix + the line verbatim)."""
    return f"{T['gatewayPrefix']} {effective.get('gateway_summary') or ''}"


def new_row_mode(posture: str) -> str:
    """The mode a newly added workspace starts with (kit workspaceNewRowMode,
    below the gateway level): Refused under "Allow everything, refuse listed
    workspaces", Read-only under "Deny everything, allow listed workspaces"."""
    return "deny" if posture == "any_except_denied" else "ro"


def _rows(value: Any, *, need_cap: bool = False) -> bool:
    if not isinstance(value, list):
        return False
    for row in value:
        if not (isinstance(row, dict) and isinstance(row.get("path"), str) and row.get("mode") in MODES):
            return False
        if need_cap and row.get("cap") not in MODES:
            return False
    return True


def parse_level(payload: Any) -> Dict[str, Any]:
    """An account or session answer: ``{configured, posture, default_mode, folders}``.

    Fails loudly on a gateway without the round-11 model (no silent fallback).
    """
    data = payload if isinstance(payload, dict) else {}
    ok = (
        "shared_workspace" not in data
        and isinstance(data.get("configured"), bool)
        and data.get("posture") in POSTURES
        and data.get("default_mode") in ("ro", "rw")
        and _rows(data.get("folders"))
    )
    if not ok:
        raise WorkspaceAnswerError("The gateway answered without the round-11 workspace model (account and chat workspaces).")
    return {
        "configured": bool(data["configured"]),
        "posture": str(data["posture"]),
        "default_mode": str(data["default_mode"]),
        "folders": [{"path": str(r["path"]), "mode": str(r["mode"])} for r in data["folders"]],
    }


def parse_effective(payload: Any) -> Dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    ok = (
        "shared_workspace" not in data
        and data.get("posture") in POSTURES
        and data.get("default_mode") in ("ro", "rw")
        and _rows(data.get("folders"), need_cap=True)
        and isinstance(data.get("summary"), str)
        and isinstance(data.get("gateway_summary"), str)
    )
    if not ok:
        raise WorkspaceAnswerError("The gateway answered without the effective workspaces (summary, gateway_summary, caps).")
    return {
        "posture": str(data["posture"]),
        "default_mode": str(data["default_mode"]),
        "folders": [
            {"path": str(r["path"]), "mode": str(r["mode"]), "cap": str(r["cap"]), "source": str(r.get("source") or "")}
            for r in data["folders"]
        ],
        "summary": str(data["summary"]),
        "gateway_summary": str(data["gateway_summary"]),
    }


def parse_answer(payload: Any) -> Dict[str, Any]:
    """A GET/PUT answer of either level (R11 WORKSPACE API — FINAL):
    ``{policy, gateway, effective, [account_default], [can_edit]}`` →
    ``{policy, effective, account_default, can_edit}``."""
    data = payload if isinstance(payload, dict) else {}
    account_default = data.get("account_default")
    gateway = data.get("gateway") if isinstance(data.get("gateway"), dict) else {}
    if isinstance(gateway.get("policy"), dict):
        gateway = gateway["policy"]
    return {
        "policy": parse_level(data.get("policy")),
        "effective": parse_effective(data.get("effective")),
        "account_default": parse_effective(account_default) if account_default is not None else None,
        "can_edit": data.get("can_edit") is not False,
        # The admin's mode for "Everything else" (its cap); None = not reported.
        "gateway_default_mode": gateway.get("default_mode") if gateway.get("default_mode") in ("ro", "rw") else None,
    }


def cap_for(effective: Optional[Dict[str, Any]], path: str) -> Optional[str]:
    """The admin cap of one row, as the gateway reports it (None = not reported)."""
    for row in (effective or {}).get("folders") or []:
        if row.get("path") == path:
            return str(row.get("cap") or "") or None
    return None


def allowed_modes(cap: Optional[str]) -> List[str]:
    """The modes at or below a cap (all three when the gateway reported none)."""
    if cap not in _RANK:
        return list(MODES)
    return [m for m in MODES if _RANK[m] <= _RANK[cap]]


def cap_tooltip(cap: Optional[str]) -> str:
    """Why the modes above a cap cannot be picked (kit workspaceModesUnderCap)."""
    if cap == "deny":
        return T["capRefused"]
    if cap == "ro":
        return T["capReadOnly"]
    return ""


# ---------------------------------------------------------------- PUT bodies
# Every write is the WHOLE level, configured: the gateway stores what it gets.


def _body(level: Dict[str, Any], **changes: Any) -> Dict[str, Any]:
    body = {
        "configured": True,
        "posture": level["posture"],
        "default_mode": level["default_mode"],
        "folders": [dict(path=r["path"], mode=r["mode"]) for r in level["folders"]],
    }
    body.update(changes)
    return body


def own_body(effective: Dict[str, Any]) -> Dict[str, Any]:
    """Turning "Follow the gateway policy" / "Use my default" off: start from
    what applies now (the effective answer), as this level's own subset."""
    return {
        "configured": True,
        "posture": effective["posture"],
        "default_mode": effective["default_mode"],
        "folders": [{"path": r["path"], "mode": r["mode"]} for r in effective["folders"]],
    }


def follow_body() -> Dict[str, Any]:
    """"Follow the gateway policy" (account) / "Use my default" (session)."""
    return {"configured": False}


def posture_body(level: Dict[str, Any], posture: str) -> Dict[str, Any]:
    return _body(level, posture=posture)


def default_mode_body(level: Dict[str, Any], mode: str) -> Dict[str, Any]:
    return _body(level, default_mode=mode)


def mode_body(level: Dict[str, Any], path: str, mode: str) -> Dict[str, Any]:
    folders = [dict(path=r["path"], mode=(mode if r["path"] == path else r["mode"])) for r in level["folders"]]
    return _body(level, folders=folders)


def add_body(level: Dict[str, Any], path: str, mode: Optional[str] = None) -> Dict[str, Any]:
    target = str(path or "").strip()
    folders = [dict(path=r["path"], mode=r["mode"]) for r in level["folders"]]
    folders.append({"path": target, "mode": mode or new_row_mode(level["posture"])})
    return _body(level, folders=folders)


def remove_body(level: Dict[str, Any], path: str) -> Dict[str, Any]:
    return _body(level, folders=[dict(path=r["path"], mode=r["mode"]) for r in level["folders"] if r["path"] != path])


def refusal(error: Any) -> str:
    """The gateway's sentence + "Not saved."."""
    sentence = str(getattr(error, "body_text", "") or "").strip() or str(error or "").strip() or "The gateway refused the change."
    try:
        import json

        decoded = json.loads(sentence)
        if isinstance(decoded, dict):
            inner = decoded.get("detail") or decoded.get("error") or decoded.get("message")
            if isinstance(inner, dict):
                inner = inner.get("message") or inner.get("detail")
            if isinstance(inner, str) and inner.strip():
                sentence = inner.strip()
    except Exception:
        pass
    end = "" if sentence[-1:] in ".!?" else "."
    return f"{sentence}{end} {T['notSaved']}"


__all__ = [
    "ACCOUNT_TITLE",
    "SESSION_TITLE",
    "WORKSPACE_CHOOSER_TEXT",
    "WorkspaceAnswerError",
    "add_body",
    "allowed_modes",
    "cap_for",
    "cap_tooltip",
    "default_mode_body",
    "follow_body",
    "gateway_line",
    "mode_body",
    "mode_label",
    "new_row_mode",
    "own_body",
    "parse_answer",
    "parse_effective",
    "parse_level",
    "posture_body",
    "posture_help",
    "posture_label",
    "refusal",
    "remove_body",
]

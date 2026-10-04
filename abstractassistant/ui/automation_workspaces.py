"""An automation's Workspaces (round 13, DESIGN R13.2 + "R11.1 FINAL").

The schedule sheet ("Schedule this conversation" / "New automation") and an
automation's Edit box get a visible **Workspaces** section: the ONE
WorkspaceChooser at the RUN level, with the same rows and words as the
Settings → Workspace page, the console, AbstractCode and AbstractObserver
(``settings/workspace_chooser.WORKSPACE_CHOOSER_TEXT`` = the ui-kit table):
"Gateway: <gateway_summary>" on top, **Use my default** (on = no payload, the
account default applies), the posture, one row per workspace (Read & write |
Read-only | Refused; modes above the gateway's cap disabled with its
tooltip), "Everything else", "Add a workspace path" + Choose…, and the
effective line verbatim.

The value is the definition's ``target.input_data.workspace``
(``{posture, default_mode, folders}``; absent = "Use my default"). Nothing is
PUT: each change is the gateway's DRY RUN (``POST
/workspace/effective/me {workspace}``); a refusal shows the gateway's sentence
+ "Not saved." and the value stays. The form's own action (Create
automation / Save) stores it; the gateway clamps it to the eligible
workspaces at each run. No policy logic here (no path checks, no clamp).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QFileDialog, QWidget

from .settings.workspace_chooser import WORKSPACE_CHOOSER_TEXT as WT

#: The section title in all three apps (the kit's chooser title).
TITLE = WT["title"]

#: Keys the gateway derives from the payload when it stores a definition: dropped on every change.
DERIVED_KEYS = ("workspace_access_mode", "workspace_allowed_paths")

DryRun = Callable[[Optional[Dict[str, Any]]], Dict[str, Any]]


def workspaces_line(summary: str) -> str:
    """"Workspaces: <summary>" — the automation's one line (the gateway's summary, verbatim)."""
    return f"{TITLE}: {summary}"


def _is_payload(value: Any) -> bool:
    return isinstance(value, Mapping) and isinstance(value.get("folders"), list)


def automation_workspace(definition: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """The definition's ``target.input_data.workspace`` or None ("Use my default")."""
    target = (definition or {}).get("target") if isinstance(definition, Mapping) else None
    data = target.get("input_data") if isinstance(target, Mapping) else None
    value = data.get("workspace") if isinstance(data, Mapping) else None
    return payload(value) if _is_payload(value) else None


def payload(value: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """The stored shape ``{posture, default_mode, folders: [{path, mode}]}`` (None stays None)."""
    if value is None:
        return None
    return {
        "posture": str(value.get("posture") or ""),
        "default_mode": str(value.get("default_mode") or "rw"),
        "folders": [{"path": str(r.get("path") or ""), "mode": str(r.get("mode") or "")} for r in value.get("folders") or []],
    }


def with_workspace(input_data: Optional[Mapping[str, Any]], value: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """``input_data`` with this payload (None = removed: "Use my default"); the derived keys are dropped."""
    out = dict(input_data or {})
    for key in DERIVED_KEYS:
        out.pop(key, None)
    if value is None:
        out.pop("workspace", None)
    else:
        out["workspace"] = payload(value)
    return out


def run_state(value: Optional[Mapping[str, Any]], effective: Mapping[str, Any]) -> Dict[str, Any]:
    """The chooser's state for a run-level value and its dry run (the Settings page's state shape)."""
    own = payload(value)
    policy = (
        {"configured": True, **own}
        if own is not None
        else {"configured": False, "posture": effective["posture"], "default_mode": effective["default_mode"], "folders": []}
    )
    return {"policy": policy, "effective": dict(effective), "account_default": None, "can_edit": True, "gateway_default_mode": None}


class RunWorkspaces(QObject):
    """The run-level chooser host: holds the value, turns each chooser change
    (the Settings page's body: ``{configured: false}`` or the whole level)
    into a value, and asks the gateway's dry run. ``value_changed`` fires with
    the new value once the gateway accepted it. Nothing is stored yet, so no
    "Saved" status: the form's own action stores it."""

    value_changed = pyqtSignal(object)  # Optional[dict]: the new value
    changed = pyqtSignal()  # the _WorkspaceLevel page interface (after an accepted change)

    def __init__(self, parent: Optional[QWidget] = None, *, gateway_local: bool = True) -> None:
        super().__init__(parent)
        # Imported here: pages.py imports the whole settings dialog stack.
        from .settings.pages import _WorkspaceLevel

        self._parent_widget = parent
        self._gateway_local = bool(gateway_local)
        self._dry_run: Optional[DryRun] = None
        self.value: Optional[Dict[str, Any]] = None
        self.level = _WorkspaceLevel(self, "run", TITLE, WT["runHelp"], WT["useDefault"], WT["useDefaultHelp"])  # type: ignore[arg-type]
        self.card = self.level.card
        self.card.setProperty("workspaceLevel", "run")
        self.level.load({"error": "Connect to your gateway to choose workspaces."})
        self.changed.connect(self._accepted)

    def _accepted(self) -> None:
        # A draft, not stored: the level's "Saved" would be untrue here.
        self.level.status = None
        self.level.render()

    # The _WorkspaceLevel "page" interface -------------------------------------

    def _put(self, level: str, body: Dict[str, Any]) -> Dict[str, Any]:
        if self._dry_run is None:
            raise RuntimeError("Connect to your gateway to choose workspaces.")
        value = None if body.get("configured") is False else payload(body)
        effective = self._dry_run(value)
        self.value = value
        self.value_changed.emit(value)
        return run_state(value, effective)

    def choose_directory(self, start: str) -> str:
        """The folder picker ("Choose…"); a test replaces this."""
        return QFileDialog.getExistingDirectory(self._parent_widget, WT["addPlaceholder"], start or str(Path.home())) or ""

    # Host API --------------------------------------------------------------

    def set_dry_run(self, dry_run: Optional[DryRun]) -> None:
        self._dry_run = dry_run

    def show_value(self, value: Optional[Mapping[str, Any]], effective: Optional[Mapping[str, Any]], error: str = "") -> None:
        """Show a value and its dry run (``effective`` None = not read: ``error`` is said instead)."""
        self.value = payload(value)
        self.level.status = None
        self.level.draft = ""
        if effective is None:
            self.level.load({"error": error or "The gateway did not answer."})
        else:
            self.level.load({"state": run_state(self.value, effective)})

    def load(self, value: Optional[Mapping[str, Any]]) -> None:
        """Read the dry run for ``value`` now (blocking, as the Settings page's PUTs) and show it."""
        if self._dry_run is None:
            self.show_value(value, None, "Connect to your gateway to choose workspaces.")
            return
        try:
            effective = self._dry_run(payload(value))
        except Exception as exc:  # the gateway's sentence
            from .settings.workspace_chooser import refusal

            self.show_value(value, None, refusal(exc).replace(f" {WT['notSaved']}", ""))
            return
        self.show_value(value, effective)


__all__ = [
    "DERIVED_KEYS",
    "RunWorkspaces",
    "TITLE",
    "automation_workspace",
    "payload",
    "run_state",
    "with_workspace",
    "workspaces_line",
]

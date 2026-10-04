"""The eight Settings pages.

Persistence legend (also in docs/settings.md):
- conn  = ~/.abstractassistant/gateway_connection.json
- pref  = ~/.abstractassistant/preferences.json (local, per device, sent per request)
- ro    = read-only mirror of gateway truth (never written by the assistant)

Layout conventions (shared with ``common.py``): every row has a label in the
left column — switches included — so controls line up down the page; the
page's persistent actions (Save, Connect, …) live in the footer next to the
feedback line, never inside a card.

On/off settings are switches labelled by the feature (``ui.switch.AfSwitch``,
operator rule 2026-09-30). A switch that is a saved setting applies the moment
it is flipped (the feedback line names the new state; a failed save flips it
back and says so); it never waits for a Save button. A switch inside a form
with one primary action (Connect) sets that form's state.
"""

from __future__ import annotations

import json
import platform
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QEvent, Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...config import default_gateway_url
from ...core.tool_risk import describe_tool_risk
from ...icons import symbol_icon
from ...preferences import (
    DEFAULT_SCREEN_EDGE_GAP,
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    REASONING_EFFORT_LEVELS,
    SCREEN_EDGE_GAP_RANGE,
    normalize_stream_replies,
    WINDOW_WIDTH_RANGE,
    WORKFLOW_GATEWAY_DEFAULT,
)
from ...gateway_service import workflow_version_suffix
from ...theme import THEME
from ..switch import AfSwitch
from .common import Card, Chip, Note, SegmentedControl, SettingsPage, button, safe_attr, safe_call
from .route_editor import OVERRIDE_ROUTE_LABELS, RouteOverrideEditor
from .workspace_chooser import ACCOUNT_TITLE as WORKSPACE_ACCOUNT_TITLE
from .workspace_chooser import MODES as WORKSPACE_MODES
from .workspace_chooser import POSTURES as WORKSPACE_POSTURES
from .workspace_chooser import SESSION_TITLE as WORKSPACE_SESSION_TITLE
from .workspace_chooser import WORKSPACE_CHOOSER_TEXT as WT
from .workspace_chooser import add_body as workspace_add_body
from .workspace_chooser import allowed_modes as workspace_allowed_modes
from .workspace_chooser import cap_for as workspace_cap_for
from .workspace_chooser import cap_tooltip as workspace_cap_tooltip
from .workspace_chooser import default_mode_body as workspace_default_mode_body
from .workspace_chooser import follow_body as workspace_follow_body
from .workspace_chooser import gateway_line as workspace_gateway_line
from .workspace_chooser import mode_body as workspace_mode_body
from .workspace_chooser import mode_label as workspace_mode_label
from .workspace_chooser import own_body as workspace_own_body
from .workspace_chooser import posture_body as workspace_posture_body
from .workspace_chooser import posture_help as workspace_posture_help
from .workspace_chooser import posture_label as workspace_posture_label
from .workspace_chooser import refusal as workspace_refusal
from .workspace_chooser import remove_body as workspace_remove_body


def _prefs(controller: Any) -> Any:
    return safe_attr(controller, "preferences", None)


def _update_prefs(controller: Any, **updates: Any) -> bool:
    """Persist a partial change. Falls back to save_preferences for stub
    controllers that predate update_preferences."""
    if callable(getattr(controller, "update_preferences", None)):
        try:
            controller.update_preferences(**updates)
            return True
        except Exception:
            return False
    prefs = _prefs(controller)
    saver = getattr(controller, "save_preferences", None)
    if prefs is None or not callable(saver):
        return False
    try:
        from ...preferences import AssistantPreferences

        payload = prefs.to_dict() if hasattr(prefs, "to_dict") else {}
        payload.update(updates)
        saver(AssistantPreferences.from_dict(payload))
        return True
    except Exception:
        return False


_DESCRIPTION_MAX_CHARS = 150


def short_description(text: str, limit: int = _DESCRIPTION_MAX_CHARS) -> str:
    """First sentence of a tool description, bounded for a one-line row.

    Tool descriptions are written for the model (several paragraphs of
    guidance); the settings row shows the first sentence and keeps the full
    text in the tooltip.
    """
    flat = re.sub(r"\s+", " ", str(text or "")).strip()
    if not flat:
        return ""
    match = re.match(r"(.+?[.!?])(\s|$)", flat)
    first = match.group(1) if match else flat
    if len(first) > limit:
        #[WARNING:TRUNCATION] one-line settings row; the tooltip carries the full text
        first = first[: limit - 1].rstrip(" ,;:") + "…"
    return first


# =============================================================== Connection


class ConnectionPage(SettingsPage):
    title = "Connection"
    subtitle = "How this Mac signs in to the gateway. Everything here stays on this device."
    icon = "link"

    def __init__(self, controller: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(controller, parent)
        self._status_payload: Optional[dict] = None

        status_card = self.add_card(Card("Status"))
        self.connection_status = QLabel("Checking the gateway…")
        self.connection_status.setObjectName("statusNote")
        self.connection_status.setWordWrap(True)
        self.connection_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        status_card.add_widget(self.connection_status)

        form = self.add_card(Card("Gateway", "Where runs, tools and speech execute."))
        self.gateway_url_edit = QLineEdit()
        self.gateway_url_edit.setPlaceholderText("empty: this computer's gateway")
        form.add_row("Gateway URL", self.gateway_url_edit)

        self.auth_mode_combo = QComboBox()
        self.auth_mode_combo.addItem("Bearer token", "bearer")
        self.auth_mode_combo.addItem("Gateway session", "session")
        self.auth_mode_combo.currentIndexChanged.connect(self._refresh_connection_fields)
        form.add_row(
            "Sign-in mode",
            self.auth_mode_combo,
            help_text="A shared bearer token suits local and operator-run gateways; a gateway session signs one user in with a personal token.",
        )

        self.bearer_token_edit = QLineEdit()
        self.bearer_token_edit.setEchoMode(QLineEdit.Password)
        self.bearer_token_edit.setPlaceholderText("Shared gateway token")
        self.reveal_button = QPushButton()
        self.reveal_button.setObjectName("iconButton")
        self.reveal_button.setCheckable(True)
        self.reveal_button.setAutoDefault(False)
        self.reveal_button.setIcon(symbol_icon("eye", color=THEME.text_secondary, size=14))
        self.reveal_button.setToolTip("Show the token")
        self.reveal_button.toggled.connect(self._toggle_reveal)
        self._bearer_row = form.add_row("Bearer token", self.bearer_token_edit, trailing=[self.reveal_button])
        self.bearer_token_label = self._bearer_row.findChild(QLabel, "rowLabel")

        self.gateway_user_edit = QLineEdit()
        self.gateway_user_edit.setPlaceholderText("admin")
        self._user_row = form.add_row("Gateway user", self.gateway_user_edit)
        self.gateway_user_label = self._user_row.findChild(QLabel, "rowLabel")

        self.gateway_user_token_edit = QLineEdit()
        self.gateway_user_token_edit.setEchoMode(QLineEdit.Password)
        self.gateway_user_token_edit.setPlaceholderText("Paste the gateway user token")
        self._user_token_row = form.add_row("Gateway user token", self.gateway_user_token_edit)
        self.gateway_user_token_label = self._user_token_row.findChild(QLabel, "rowLabel")

        # Older callers and the dialog alias reach for `connection_feedback`;
        # it is the page's footer feedback line.
        self.connection_feedback = self.feedback

        self.connection_refresh_button = button("Reload status", "secondary", on_click=self.refresh_status_async)
        self.connection_logout_button = button("Sign out", "secondary", on_click=self._clear_connection)
        self.connection_save_button = button("Connect", "primary", on_click=self._save_connection)
        self.add_actions(self.connection_refresh_button, self.connection_logout_button, self.connection_save_button)

    # ---- state
    def refresh(self) -> None:
        self._load_connection_preferences()
        self.refresh_status_async()

    def _toggle_reveal(self, checked: bool) -> None:
        self.bearer_token_edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        self.reveal_button.setIcon(symbol_icon("eye-off" if checked else "eye", color=THEME.text_secondary, size=14))
        self.reveal_button.setToolTip("Hide the token" if checked else "Show the token")

    def _load_connection_preferences(self) -> None:
        connection = safe_call(self.controller, "current_connection", default=None)
        if connection is None:
            return
        self.gateway_url_edit.setText(str(getattr(connection, "base_url", "") or ""))
        idx = self.auth_mode_combo.findData(str(getattr(connection, "auth_mode", "bearer") or "bearer"))
        if idx >= 0:
            self.auth_mode_combo.setCurrentIndex(idx)
        self.bearer_token_edit.setText(str(getattr(connection, "auth_token", "") or ""))
        self.gateway_user_edit.setText(str(getattr(connection, "user_id", "") or ""))
        self.gateway_user_token_edit.clear()
        self._refresh_connection_fields()

    def _refresh_connection_fields(self) -> None:
        is_bearer = str(self.auth_mode_combo.currentData() or "bearer") == "bearer"
        self._bearer_row.setVisible(is_bearer)
        self._user_row.setVisible(not is_bearer)
        self._user_token_row.setVisible(not is_bearer)

    def refresh_status_async(self) -> None:
        """Probe /me off the GUI thread; the old tab blocked for up to 30 s."""
        self.connection_status.setText("Checking the gateway…")
        self.connection_status.setProperty("tone", "info")

        def _run() -> None:
            payload = safe_call(self.controller, "connection_status", default={"ok": False, "detail": "Unavailable."})
            self._status_payload = payload if isinstance(payload, dict) else {"ok": False}
            # QTimer.singleShot from a non-GUI thread is unreliable; use a
            # queued signal instead.
            self._status_ready.emit()

        threading.Thread(target=_run, name="settings-connection-status", daemon=True).start()

    _status_ready = pyqtSignal()

    def _apply_status(self) -> None:
        payload = self._status_payload or {}
        if payload.get("ok") is False:
            detail = str(payload.get("detail") or "Not connected yet.").strip()
            self.connection_status.setText(f"Not connected — {detail}")
            self.connection_status.setProperty("tone", "error")
        else:
            principal = payload.get("principal") if isinstance(payload.get("principal"), dict) else {}
            auth = payload.get("auth") if isinstance(payload.get("auth"), dict) else {}
            routing = payload.get("routing") if isinstance(payload.get("routing"), dict) else {}
            user_id = str(principal.get("user_id") or "unknown").strip()
            tenant_id = str(principal.get("tenant_id") or "").strip()
            roles = [str(r) for r in (principal.get("roles") or []) if str(r)]
            mode = str(auth.get("mode") or "").strip() or "unknown"
            routing_mode = str(routing.get("mode") or "").strip()
            parts = [f"Connected as {user_id}"]
            if tenant_id:
                parts.append(f"tenant {tenant_id}")
            if roles:
                parts.append("roles " + ", ".join(roles))
            parts.append(f"{mode} auth")
            if routing_mode:
                parts.append(f"routing {routing_mode}")
            version = self._gateway_version()
            if version:
                parts.append(f"gateway {version}")
            self.connection_status.setText(" · ".join(parts))
            self.connection_status.setProperty("tone", "success")
        from ..styles import refresh_style

        refresh_style(self.connection_status)

    def _gateway_version(self) -> str:
        manager = safe_attr(self.controller, "llm_manager", None)
        caps = safe_call(manager, "gateway_capabilities", stale_ok=True, default=None)
        raw = safe_attr(caps, "raw", {}) or {}
        gw = raw.get("abstractgateway") if isinstance(raw, dict) else None
        return str(gw.get("version") or "") if isinstance(gw, dict) else ""

    def _save_connection(self) -> None:
        base_url = self.gateway_url_edit.text().strip() or default_gateway_url()
        auth_mode = str(self.auth_mode_combo.currentData() or "bearer")
        try:
            if auth_mode == "bearer":
                self.controller.save_bearer_connection(base_url=base_url, auth_token=self.bearer_token_edit.text())
                self.say("Saved the bearer-token connection on this device.")
            else:
                self.controller.login_gateway_session(
                    base_url=base_url,
                    user_id=self.gateway_user_edit.text().strip(),
                    token=self.gateway_user_token_edit.text(),
                    # No retention switch (0.12.1): sessions belong to the gateway, which
                    # decides how long a sign-in lives; the Assistant never shortens it.
                    remember=True,
                )
                self.gateway_user_token_edit.clear()
                self.say("Saved the gateway session on this device.")
        except Exception as exc:
            QMessageBox.critical(self, "Connection failed", str(exc))
            return
        self.changed.emit()
        self.refresh()

    def _clear_connection(self) -> None:
        connection = safe_call(self.controller, "current_connection", default=None)
        base_url = self.gateway_url_edit.text().strip() or default_gateway_url()
        try:
            if (
                connection is not None
                and str(getattr(connection, "auth_mode", "") or "").strip() == "session"
                and str(getattr(connection, "session_id", "") or "").strip()
            ):
                self.controller.logout_gateway_session()
            else:
                self.controller.save_bearer_connection(base_url=base_url, auth_token="")
        except Exception as exc:
            QMessageBox.critical(self, "Sign-out failed", str(exc))
            return
        self.say("Signed out on this device.", tone="info")
        self.changed.emit()
        self.refresh()


# ================================================================= Models


_REASONING_LABELS = {
    "": "Gateway default",
    "none": "None",
    "minimal": "Minimal",
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "xhigh": "Extra high",
}


class ModelsPage(SettingsPage):
    title = "Models & reasoning"
    nav_title = "Models"
    subtitle = (
        "Every list starts with the gateway's own default. Pick anything else and it applies "
        "to this app only — kept on this Mac, sent with each request, and never written to the gateway."
    )
    icon = "cpu"

    def __init__(self, controller: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(controller, parent)

        # LIVE REPLIES (R11.4): streaming is app-specific — a plain switch,
        # on by default, sent as `_runtime.stream` true/false with every run.
        # No "Gateway default": the gateway's own switch (Workflows → Settings
        # → Streamed replies) is for clients that do not say.
        replies = self.add_card(
            Card("Replies", "Show the answer while the model writes it. The finished answer replaces the live text.")
        )
        self.stream_switch = AfSwitch("Stream replies")
        self.stream_switch.clicked.connect(self._on_stream_toggled)
        replies.add_row("Streaming", self.stream_switch)
        self.stream_detail = QLabel("")
        self.stream_detail.setObjectName("rowHelp")
        self.stream_detail.setWordWrap(True)
        replies.add_widget(self.stream_detail)

        # A card WITHOUT a title: the surface is what makes the form read as a
        # panel, but a card titled "Models" inside a page titled
        # "Models & reasoning" was a third heading for one thing.
        routes = self.add_card(Card())
        self.route_editor = RouteOverrideEditor(controller, routes)
        self.route_editor.changed.connect(self._on_routes_changed)
        routes.add_widget(self.route_editor)
        # The actions live in the footer, like every other page — inside the
        # card they were pushed off-screen at the dialog's own default width.
        self.add_actions(*self.route_editor.action_buttons())

    def refresh(self) -> None:
        self._refresh_stream()
        self.route_editor.refresh()

    def _refresh_stream(self) -> None:
        on = normalize_stream_replies(safe_attr(_prefs(self.controller), "stream_replies", None)) == "on"
        self.stream_switch.blockSignals(True)
        try:
            self.stream_switch.setChecked(on)
        finally:
            self.stream_switch.blockSignals(False)
        self._show_stream_detail()

    def _show_stream_detail(self) -> None:
        block = safe_call(self.controller, "gateway_streaming", default=None)
        advertised = None if block is None else block.get("deltas") is True
        if not self.stream_switch.isChecked():
            text = "Replies appear when they are finished."
        elif advertised is False:
            text = "This gateway does not offer live replies, so answers appear when they are finished."
        elif advertised is None:
            text = "Not connected — replies stream once the gateway says it offers live replies."
        else:
            text = "Every reply from this app streams while the model writes it."
        self.stream_detail.setText(text)

    def _on_stream_toggled(self, checked: bool) -> None:
        if not _update_prefs(self.controller, stream_replies="on" if checked else "off"):
            self._refresh_stream()
            self.say("Not saved. This device could not store the setting.", tone="error")
            return
        self._show_stream_detail()
        self.say("Replies stream." if checked else "Replies appear when finished.")
        self.changed.emit()

    def _on_routes_changed(self) -> None:
        self.changed.emit()


# =============================================================== Workflow
# R10.4 (R10-W3): its own page, right after Models. Other lanes: keep out of this class.


class WorkflowPage(SettingsPage):
    """WHICH WORKFLOW runs each turn (contract D). "Gateway default" is always
    the first row, selected until the user picks another, and saved as
    ``@default`` (never a copy of its id), so an admin's later change applies to
    the next turn. The list is the gateway's executable workflows for this app
    (``GET /bundles?executable_for=abstractassistant.agent.v1``), the same list
    the automation sheet offers. The choice applies on change (no Save).

    Stored in preferences.json (pref): the gateway has no per-account
    preference route for it (AbstractCode keeps its choice per signed-in
    identity in the browser the same way).

    "Open in AbstractFlow" (an icon button) appears only when the gateway
    serves AbstractFlow at /apps/flow/ (``GET /api/gateway/apps``); it opens the
    selected workflow through the gateway's signed-in app door."""

    title = "Workflow"
    nav_title = "Workflow"
    subtitle = "The agent workflow each new turn runs. A turn already running keeps its workflow."
    icon = "list-tree"

    _flow_ready = pyqtSignal(object)
    _flow_opened = pyqtSignal(object)

    def __init__(self, controller: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(controller, parent)
        card = self.add_card(Card())
        self.workflow_combo = QComboBox()
        self.workflow_combo.setMinimumWidth(320)
        self.workflow_combo.setAccessibleName("Workflow")
        self.workflow_combo.activated.connect(self._on_workflow_chosen)
        self.open_flow_button = QPushButton()
        self.open_flow_button.setObjectName("iconButton")
        self.open_flow_button.setAutoDefault(False)
        self.open_flow_button.setIcon(symbol_icon("external", color=THEME.text_secondary, size=14))
        self.open_flow_button.setToolTip("Open in AbstractFlow")
        self.open_flow_button.setAccessibleName("Open in AbstractFlow")
        self.open_flow_button.clicked.connect(self._open_in_flow)
        self.open_flow_button.setVisible(False)
        card.add_row("Runs", self.workflow_combo, stretch_control=False, trailing=[self.open_flow_button])
        self.workflow_detail = QLabel("")
        self.workflow_detail.setObjectName("rowHelp")
        self.workflow_detail.setWordWrap(True)
        card.add_widget(self.workflow_detail)
        self._workflow_rows: List[Dict[str, Any]] = []
        self.flow_state: Optional[Dict[str, Any]] = None
        self._flow_ready.connect(self._apply_flow_state)
        self._flow_opened.connect(self._apply_flow_opened)

    def refresh(self) -> None:
        self._refresh_workflows()
        self._probe_flow()

    # ---------------------------------------------------------- the choice

    def _refresh_workflows(self) -> None:
        rows = safe_call(self.controller, "workflow_menu", default=None)
        self._workflow_rows = list(rows or [])
        current = safe_call(self.controller, "workflow_choice", default=WORKFLOW_GATEWAY_DEFAULT)
        self.workflow_combo.blockSignals(True)
        try:
            self.workflow_combo.clear()
            selected = -1
            for index, row in enumerate(self._workflow_rows):
                self.workflow_combo.addItem(str(row.get("label") or ""))
                if row.get("choice") == current:
                    selected = index
            if selected < 0 and current != WORKFLOW_GATEWAY_DEFAULT and isinstance(current, dict):
                # The saved workflow left the catalog: show it, do not silently
                # move the selection to something else.
                missing = f"{current.get('bundle_id')}:{current.get('flow_id')} (not in the catalog any more)"
                self.workflow_combo.addItem(missing)
                self._workflow_rows.append({"choice": current, "label": missing, "detail": "Pick another workflow."})
                selected = self.workflow_combo.count() - 1
            self.workflow_combo.setCurrentIndex(max(0, selected))
        finally:
            self.workflow_combo.blockSignals(False)
        self.workflow_combo.setEnabled(bool(self._workflow_rows))
        self._show_workflow_detail()

    def _show_workflow_detail(self) -> None:
        index = self.workflow_combo.currentIndex()
        if 0 <= index < len(self._workflow_rows):
            self.workflow_detail.setText(str(self._workflow_rows[index].get("detail") or ""))
        else:
            self.workflow_detail.setText("Not connected — the gateway's workflows are not known yet.")

    def selected_choice(self) -> Any:
        index = self.workflow_combo.currentIndex()
        if 0 <= index < len(self._workflow_rows):
            return self._workflow_rows[index].get("choice")
        return None

    def _on_workflow_chosen(self, index: int) -> None:
        if not (0 <= index < len(self._workflow_rows)):
            return
        choice = self._workflow_rows[index].get("choice")
        try:
            self.controller.set_workflow_choice(choice)
        except Exception as exc:
            self.say(f"{str(exc).rstrip('.')}. Not saved.", tone="error")
            self._refresh_workflows()
            return
        self._show_workflow_detail()
        self.say("Saved on this device — applies from the next turn.")
        self.changed.emit()

    # ------------------------------------------------- Open in AbstractFlow

    def _probe_flow(self) -> None:
        """Ask the gateway whether it serves AbstractFlow (off the GUI thread)."""
        probe = getattr(self.controller, "flow_app", None)
        if not callable(probe):
            self._apply_flow_state(None)
            return

        def work() -> None:
            try:
                state = probe()
            except Exception:
                state = None
            try:
                self._flow_ready.emit(state)
            except RuntimeError:
                pass  # the dialog closed meanwhile

        threading.Thread(target=work, name="settings-flow-probe", daemon=True).start()

    def _apply_flow_state(self, state: Any) -> None:
        self.flow_state = dict(state) if isinstance(state, dict) else None
        available = bool(self.flow_state and self.flow_state.get("available"))
        self.open_flow_button.setVisible(available)
        if available and not self.flow_state.get("running"):
            self.open_flow_button.setToolTip("Open in AbstractFlow (AbstractFlow is not running on the gateway: start it from the gateway's Apps page)")
        else:
            self.open_flow_button.setToolTip("Open in AbstractFlow")

    def _open_in_flow(self) -> None:
        choice = self.selected_choice()
        opener = getattr(self.controller, "open_workflow_in_flow_url", None)
        if choice is None or not callable(opener):
            return
        self.open_flow_button.setEnabled(False)

        def work() -> None:
            try:
                outcome: Any = (True, opener(choice))
            except Exception as exc:  # noqa: BLE001 - shown as a sentence
                outcome = (False, _gateway_sentence(exc))
            try:
                self._flow_opened.emit(outcome)
            except RuntimeError:
                pass

        threading.Thread(target=work, name="settings-open-flow", daemon=True).start()

    def _apply_flow_opened(self, outcome: Any) -> None:
        self.open_flow_button.setEnabled(True)
        ok, value = outcome
        if not ok:
            self.say(f"Could not open AbstractFlow: {value}", tone="error")
            return
        if not QDesktopServices.openUrl(QUrl(str(value))):
            self.say("Could not open the browser.", tone="error")
            return
        self.say("Opened in AbstractFlow.")


def _gateway_sentence(exc: Exception) -> str:
    """The gateway's own ``message`` (+ ``hint``) from a refusal, else the error text."""
    body = getattr(exc, "body_text", "")
    try:
        data = json.loads(body) if body else None
    except Exception:
        data = None
    if isinstance(data, dict):
        detail = data.get("detail") if isinstance(data.get("detail"), dict) else data
        message = str(detail.get("message") or "").strip()
        hint = str(detail.get("hint") or "").strip()
        if message:
            return f"{message} {hint}".strip()
    if isinstance(body, str) and body.strip():
        return body.strip()  # the client already reduced the refusal to its message
    return str(exc)


# ================================================================== Voice


class _OutputDeviceCombo(QComboBox):
    """The device list, rebuilt every time it is opened.

    Audio devices come and go while this window is open — glasses, headphones, a dock —
    so a list captured when Settings was built is stale almost immediately. Repopulating
    on open is what removes the need for a Refresh button.
    """

    def __init__(self, reload_devices, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._reload_devices = reload_devices

    def showPopup(self) -> None:  # noqa: N802 - Qt override
        try:
            self._reload_devices()
        except Exception:
            pass
        super().showPopup()


class VoicePage(SettingsPage):
    title = "Voice"
    subtitle = "Speech runs on the gateway; audio is captured and played on this Mac."
    icon = "audio-lines"

    def __init__(self, controller: Any, route_editor: Optional[RouteOverrideEditor], parent: Optional[QWidget] = None) -> None:
        super().__init__(controller, parent)
        self._route_editor = route_editor

        # No "Engines" card (R11.5): the speech engines are chosen in ONE
        # place, Models → Voice output (TTS) / Voice input (STT).
        routes = self.add_card(Card("Output"))
        # WHICH SPEAKER. Until 2026-09-18 this row only NAMED the system default and
        # offered a shortcut to macOS Sound settings — and playback did not reliably
        # follow that default either, so replies came out of the built-in speakers
        # while the user was wearing AR glasses, with nothing on screen saying so.
        self.output_device_combo = _OutputDeviceCombo(
            lambda: self._reload_output_devices(announce=False)
        )
        self.output_device_combo.setMinimumWidth(280)
        is_macos = platform.system().lower() == "darwin"
        routes.add_row(
            "Output device",
            self.output_device_combo,
            trailing=[button("Test", "secondary", on_click=self._test_output_device)],
            stretch_control=False,
            help_text=(
                "Where spoken replies play. The list is the devices this Mac can play to, "
                "refreshed each time you open it. AirPlay speakers are not in it \u2014 macOS "
                "does not offer them to apps \u2014 so pick them in the Sound menu and leave "
                "this on \u201cSystem default\u201d, which follows whatever the Mac is using."
                if is_macos
                else "Where spoken replies play. \u201cSystem default\u201d follows the system output."
            ),
        )
        self.device_summary = QLabel("")
        self.device_summary.setObjectName("rowValue")
        self.device_summary.setWordWrap(True)
        routes.add_row("Playing on", self.device_summary)

        behaviour = self.add_card(Card("Replies"))
        self.auto_speak = AfSwitch("Speak replies automatically")
        self._immediate(self.auto_speak, "auto_speak", ("Replies are spoken automatically.", "Replies are not spoken automatically."))
        behaviour.add_row("Read aloud", self.auto_speak)
        self.voice_quality_combo = QComboBox()
        self.voice_quality_combo.addItem("Balanced", "standard")
        self.voice_quality_combo.addItem("Faster (lower quality)", "low")
        self.voice_quality_combo.addItem("Higher quality (slower)", "high")
        behaviour.add_row(
            "Voice latency",
            self.voice_quality_combo,
            stretch_control=False,
            help_text="Trades voice quality for a faster first word. Applied only when the gateway offers this control.",
        )

        conversation = self.add_card(
            Card(
                "Voice conversation",
                "Hands-free mode (⌘⇧V or the waveform button): the assistant listens, sends what you say, speaks the reply and listens again.",
            )
        )
        self.voice_auto_send = AfSwitch("Send what you say automatically")
        self._immediate(self.voice_auto_send, "voice_auto_send", ("What you say is sent automatically.", "What you say lands in the message box; Return sends it."))
        conversation.add_row("Sending", self.voice_auto_send, help_text="Off: your words land in the message box and Return sends them.")
        self.voice_spoken_replies = AfSwitch("Ask for short, spoken-style replies")
        self._immediate(self.voice_spoken_replies, "voice_spoken_replies", ("Short, spoken-style replies are on.", "Short, spoken-style replies are off."))
        conversation.add_row("Reply style", self.voice_spoken_replies, help_text="Adds a voice-style instruction to each request while the conversation runs.")
        # A two-option question is a list, like every other choice in Settings —
        # not a stack of radio buttons that has to be read twice to be answered.
        self.voice_mode_combo = QComboBox()
        self.voice_mode_combo.addItem("Pause the mic while speaking", "wait")
        self.voice_mode_combo.addItem("Keep the mic open", "full")
        conversation.add_row(
            "Barge-in",
            self.voice_mode_combo,
            stretch_control=False,
            help_text=(
                "Pause on speakers; keep it open with headphones and say “stop” "
                "to interrupt. With speakers, the open-mic option may transcribe "
                "the assistant's own voice."
            ),
        )

        # No Save button on this page: every control is a switch or a choice,
        # and each applies the moment it changes (user actions only:
        # `activated`, not `currentIndexChanged`, so a refresh saves nothing).
        for combo in (self.output_device_combo, self.voice_quality_combo, self.voice_mode_combo):
            combo.activated.connect(lambda _index=0: self._save())

    def _immediate(self, switch: AfSwitch, key: str, messages) -> None:
        """A switch that is a saved setting: apply on click, say the new
        state, flip back with an error when the save fails."""

        def apply(checked: bool) -> None:
            if _update_prefs(self.controller, **{key: bool(checked)}):
                self.say(messages[0] if checked else messages[1])
                self.changed.emit()
            else:
                switch.blockSignals(True)
                switch.setChecked(not checked)
                switch.blockSignals(False)
                self.say("Not saved. The voice settings could not be stored.", tone="error")

        switch.clicked.connect(apply)

    def refresh(self) -> None:
        prefs = _prefs(self.controller)
        self.auto_speak.setChecked(bool(safe_attr(prefs, "auto_speak", False)))
        idx = self.voice_quality_combo.findData(str(safe_attr(prefs, "voice_quality", "standard") or "standard"))
        self.voice_quality_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.voice_auto_send.setChecked(bool(safe_attr(prefs, "voice_auto_send", True)))
        self.voice_spoken_replies.setChecked(bool(safe_attr(prefs, "voice_spoken_replies", True)))
        mode = str(safe_attr(prefs, "voice_mode", "wait") or "wait")
        mode_index = self.voice_mode_combo.findData("full" if mode == "full" else "wait")
        self.voice_mode_combo.setCurrentIndex(mode_index if mode_index >= 0 else 0)
        self._reload_output_devices(announce=False)
        self._refresh_summaries()

    def _refresh_summaries(self) -> None:
        voice = safe_attr(self.controller, "voice_manager", None)
        device = str(safe_call(voice, "output_device_label", default="") or "").strip()
        volume, muted = (None, None)
        state = safe_call(voice, "output_volume_state", default=None)
        if isinstance(state, tuple) and len(state) == 2:
            volume, muted = state
        if not device:
            self.device_summary.setText("System default output")
        else:
            bits = [device]
            if muted is True:
                bits.append("muted")
            elif isinstance(volume, int):
                bits.append(f"{volume}%")
            self.device_summary.setText(" · ".join(bits))

    def _reload_output_devices(self, announce: bool = True) -> None:
        """Fill the picker from the devices the system can see right now.

        A device connected after launch is listed too, and labelled: PortAudio freezes
        its device list at initialization, so the player re-enumerates when it must —
        but the user has to be able to SEE the headset before choosing it.
        """
        prefs = _prefs(self.controller)
        stored = str(safe_attr(prefs, "audio_output_device", "") or "").strip()
        stored_name = str(safe_attr(prefs, "audio_output_device_name", "") or "").strip()
        voice = safe_attr(self.controller, "voice_manager", None)
        devices = safe_call(voice, "available_output_devices", default=[]) or []

        combo = self.output_device_combo
        combo.blockSignals(True)
        combo.clear()
        default_name = ""
        for device in devices:
            if getattr(device, "is_system_default", False):
                default_name = str(getattr(device, "name", "") or "")
                break
        combo.addItem(f"System default ({default_name})" if default_name else "System default", "")
        seen = {""}
        for device in devices:
            key = str(getattr(device, "key", "") or "")
            name = str(getattr(device, "name", "") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            label = name if getattr(device, "index", None) is not None else f"{name} (connected after launch)"
            combo.addItem(label, key)
        if stored and stored not in seen:
            # Chosen once, not here now: keep it selectable so the choice is not
            # silently lost the moment the headset is unplugged.
            combo.addItem(f"{stored_name or stored} (not connected)", stored)
        index = combo.findData(stored)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)
        if announce:
            self._refresh_summaries()

    def _test_output_device(self) -> None:
        voice = safe_attr(self.controller, "voice_manager", None)
        if voice is None or not callable(getattr(voice, "play_test_tone", None)):
            self.say("Audio playback is unavailable in this build.", tone="error")
            return
        spec = str(self.output_device_combo.currentData() or "")
        label = self.output_device_combo.currentText()
        try:
            problem = str(voice.play_test_tone(spec) or "")
        except Exception as exc:  # a settings button must never take the app down
            problem = str(exc)
        if problem:
            self.say(problem, tone="error")
        else:
            self.say(f"Played a test tone on {label}.")

    def _save(self) -> None:
        device_key = str(self.output_device_combo.currentData() or "")
        device_name = ""
        if device_key:
            voice = safe_attr(self.controller, "voice_manager", None)
            for device in (safe_call(voice, "available_output_devices", default=[]) or []):
                if str(getattr(device, "key", "") or "") == device_key:
                    device_name = str(getattr(device, "name", "") or "")
                    break
            if not device_name:
                device_name = str(safe_attr(_prefs(self.controller), "audio_output_device_name", "") or "")
        ok = _update_prefs(
            self.controller,
            auto_speak=bool(self.auto_speak.isChecked()),
            voice_quality=str(self.voice_quality_combo.currentData() or "standard"),
            voice_auto_send=bool(self.voice_auto_send.isChecked()),
            voice_spoken_replies=bool(self.voice_spoken_replies.isChecked()),
            voice_mode=str(self.voice_mode_combo.currentData() or "wait"),
            audio_output_device=device_key,
            audio_output_device_name=device_name,
        )
        if ok:
            self._refresh_summaries()
            self.say("Saved on this device.")
            self.changed.emit()
        else:
            self.say("Not saved. The voice settings could not be stored.", tone="error")


# ============================================================== Workspace


class _PathField(QLineEdit):
    """The "Add a workspace path" field: Return adds (returnPressed), Escape clears."""

    escaped = pyqtSignal()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.key() == Qt.Key_Escape:
            self.clear()
            self.escaped.emit()
            event.accept()
            return
        super().keyPressEvent(event)


def _mode_options(values) -> List[tuple]:
    # "&" is a Qt mnemonic marker: "Read & write" needs "&&" on a button.
    return [(v, workspace_mode_label(v).replace("&", "&&")) for v in values]


class _WorkspaceLevel:
    """One level of the WorkspaceChooser (R11.1 FINAL) as a Settings card:
    "Gateway: <gateway_summary>" on top (verbatim), the state switch ("Follow
    the gateway policy" for the account, "Use my default" for this chat),
    then — while this level has its own subset — the posture, one row per
    workspace (Read-only | Read & write | Refused, modes above the gateway's
    cap disabled with the gateway's tooltip, remove), "Everything else" under
    "Allow everything, refuse listed workspaces", the "Add a workspace path"
    row with Choose…, and the effective line (verbatim) under it all.

    Every change is ONE PUT through ``put(body)``; a refusal shows the
    gateway's sentence + "Not saved." and the page re-renders what the
    gateway holds. No policy logic: the gateway decides.
    """

    def __init__(self, page: "WorkspacePage", level: str, title: str, help_text: str, switch_label: str, switch_help: str) -> None:
        self.page = page
        self.level = level
        self.state: Optional[Dict[str, Any]] = None
        self.error = ""
        self.status: Optional[tuple] = None  # (text, tone)
        self.draft = ""
        self.card = Card(title, help_text)
        self.card.setProperty("workspaceLevel", level)
        self.gateway_label = QLabel("")
        self.gateway_label.setObjectName("rowHelp")
        self.gateway_label.setWordWrap(True)
        self.gateway_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.gateway_label.setProperty("workspace", "gateway-line")
        self.card.add_widget(self.gateway_label)
        self.load_note = Note("", "warning")
        self.card.add_widget(self.load_note)
        self.follow_switch = AfSwitch(switch_label)
        self.follow_switch.setProperty("workspace", "follow")
        self.follow_switch.clicked.connect(self._on_follow)
        self.follow_row = self.card.add_row("", self.follow_switch, help_text=switch_help)
        self.editor = QWidget()
        self.editor_layout = QVBoxLayout(self.editor)
        self.editor_layout.setContentsMargins(0, 0, 0, 0)
        self.editor_layout.setSpacing(6)
        self.card.add_widget(self.editor)
        self.status_note = Note("", "ok")
        self.card.add_widget(self.status_note)
        self.effective_label = QLabel("")
        self.effective_label.setObjectName("rowValue")
        self.effective_label.setWordWrap(True)
        self.effective_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.effective_label.setProperty("workspace", "effective")
        self.card.add_widget(self.effective_label)
        self.posture_control: Optional[SegmentedControl] = None
        self.default_mode_control: Optional[SegmentedControl] = None
        self.mode_controls: Dict[str, SegmentedControl] = {}
        self.remove_buttons: Dict[str, QPushButton] = {}
        self.add_field: Optional[_PathField] = None
        self.choose_button: Optional[QPushButton] = None
        self.add_button: Optional[QPushButton] = None

    # ------------------------------------------------------------ data

    def load(self, payload: Any) -> None:
        payload = payload if isinstance(payload, dict) else {}
        state = payload.get("state")
        self.state = state if isinstance(state, dict) else None
        self.error = str(payload.get("error") or "")
        self.render()

    def put(self, body: Dict[str, Any]) -> bool:
        try:
            self.state = self.page._put(self.level, body)
        except Exception as exc:  # the gateway's sentence, verbatim
            self.status = (workspace_refusal(exc), "error")
            self.render()
            return False
        self.status = (WT["saved"], "ok")
        self.render()
        self.page.changed.emit()
        return True

    # ------------------------------------------------------------ render

    def render(self) -> None:
        WorkspacePage._clear(self.editor_layout)
        self.posture_control = None
        self.default_mode_control = None
        self.mode_controls = {}
        self.remove_buttons = {}
        self.add_field = None
        self.choose_button = None
        self.add_button = None
        text, tone = self.status or ("", "ok")
        self.status_note.show_text(text, "error" if tone == "error" else "ok")
        self.status_note.setProperty("workspace", "refusal" if tone == "error" else "saved")
        if self.state is None:
            self.gateway_label.setText("")
            self.gateway_label.setVisible(False)
            self.follow_row.setVisible(False)
            self.editor.setVisible(False)
            self.effective_label.setText("")
            self.load_note.show_text(self.error or "The gateway did not answer.", "warning")
            return
        policy, effective = self.state["policy"], self.state["effective"]
        locked = not bool(self.state.get("can_edit", True))
        following = not policy["configured"]
        # Following: show what applies (the level above, as the gateway
        # computed it), read-only — the kit's view, not a hidden editor.
        rows = [{"path": r["path"], "mode": r["mode"]} for r in effective["folders"]] if following else policy["folders"]
        posture_now = effective["posture"] if following else policy["posture"]
        default_now = effective["default_mode"] if following else policy["default_mode"]
        editable = not following and not locked
        self.load_note.show_text(WT["locked"] if locked else "", "info")
        self.gateway_label.setVisible(True)
        self.gateway_label.setText(workspace_gateway_line(effective))
        self.follow_row.setVisible(True)
        self.follow_switch.blockSignals(True)
        self.follow_switch.setChecked(following)
        self.follow_switch.blockSignals(False)
        self.follow_switch.setEnabled(not locked)
        self.effective_label.setText(effective["summary"])
        self.editor.setVisible(True)

        caption = QLabel(WT["postureLabel"])
        caption.setObjectName("rowLabel")
        self.editor_layout.addWidget(caption)
        posture = SegmentedControl([(p, workspace_posture_label(p)) for p in WORKSPACE_POSTURES])
        posture.setProperty("workspace", "posture")
        posture.set_value(posture_now)
        posture.set_tooltips({p: workspace_posture_help(p) for p in WORKSPACE_POSTURES})
        posture.changed.connect(lambda value: value != policy["posture"] and self.put(workspace_posture_body(policy, value)))
        posture.setEnabled(editable)
        self.posture_control = posture
        self.editor_layout.addWidget(posture)

        if not rows and posture_now == "allowed_only":
            empty = QLabel(WT["emptyAllowed"])
            empty.setObjectName("rowHelp")
            empty.setWordWrap(True)
            empty.setProperty("workspace", "empty")
            self.editor_layout.addWidget(empty)
        for row in rows:
            line = QWidget()
            line.setProperty("workspace", "row")
            box = QHBoxLayout(line)
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(6)
            path = QLabel(row["path"])
            path.setObjectName("rowLabel")
            path.setWordWrap(True)
            path.setTextInteractionFlags(Qt.TextSelectableByMouse)
            path.setMinimumWidth(40)
            box.addWidget(path, 1)
            cap = workspace_cap_for(effective, row["path"])
            allowed = workspace_allowed_modes(cap)
            control = SegmentedControl(_mode_options(WORKSPACE_MODES))
            control.setProperty("workspace", "mode")
            control.set_value(row["mode"])
            for value in WORKSPACE_MODES:
                if value not in allowed:
                    control.set_option_enabled(value, False, workspace_cap_tooltip(cap))
            control.changed.connect(lambda value, p=row["path"], m=row["mode"]: value != m and self.put(workspace_mode_body(policy, p, value)))
            control.setEnabled(editable)
            control.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            box.addWidget(control, 0)
            self.mode_controls[row["path"]] = control
            if editable:
                remove = QPushButton()
                remove.setObjectName("iconButton")
                remove.setAutoDefault(False)
                remove.setIcon(symbol_icon("trash", color=THEME.text_secondary, size=14))
                remove.setToolTip(WT["remove"])
                remove.setAccessibleName(f"{WT['remove']} {row['path']}")
                remove.clicked.connect(lambda _c=False, p=row["path"]: self.put(workspace_remove_body(policy, p)))
                box.addWidget(remove, 0)
                self.remove_buttons[row["path"]] = remove
            self.editor_layout.addWidget(line)

        if posture_now == "any_except_denied":
            line = QWidget()
            line.setProperty("workspace", "everything-else")
            box = QHBoxLayout(line)
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(6)
            label = QLabel(WT["everythingElse"])
            label.setObjectName("rowLabel")
            box.addWidget(label, 1)
            control = SegmentedControl(_mode_options(("rw", "ro")))
            control.set_value(default_now)
            if self.state.get("gateway_default_mode") == "ro":
                control.set_option_enabled("rw", False, workspace_cap_tooltip("ro"))
            control.changed.connect(lambda value: value != policy["default_mode"] and self.put(workspace_default_mode_body(policy, value)))
            control.setEnabled(editable)
            box.addWidget(control, 0)
            self.default_mode_control = control
            self.editor_layout.addWidget(line)

        if not editable:
            return
        add = QWidget()
        add.setProperty("workspace", "add")
        box = QHBoxLayout(add)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        field = _PathField()
        field.setPlaceholderText(WT["addPlaceholder"])
        field.setAccessibleName(WT["addPlaceholder"])
        field.setText(self.draft)
        field.textChanged.connect(self._set_draft)
        field.returnPressed.connect(self._add_typed)
        field.escaped.connect(self._clear_draft)
        box.addWidget(field, 1)
        self.choose_button = button(WT["choose"], "secondary", on_click=self._choose)
        self.choose_button.setVisible(self.page._gateway_local)
        box.addWidget(self.choose_button, 0)
        self.add_button = button(WT["add"], "secondary", on_click=self._add_typed)
        box.addWidget(self.add_button, 0)
        self.add_field = field
        self.editor_layout.addWidget(add)

    # ------------------------------------------------------------ actions

    def _on_follow(self, checked: bool) -> None:
        if self.state is None:
            return
        if checked:
            self.put(workspace_follow_body())
        else:
            # Start from what applies now (the effective answer, verbatim) —
            # for this chat that is the account default.
            self.put(workspace_own_body(self.state["effective"]))

    def _set_draft(self, text: str) -> None:
        self.draft = str(text or "")

    def _clear_draft(self) -> None:
        self.draft = ""
        if self.status is not None:
            self.status = None
            self.render()

    def _add_typed(self) -> None:
        path = (self.add_field.text() if self.add_field is not None else self.draft).strip()
        if path:
            self.add_path(path)

    def add_path(self, path: str) -> bool:
        if self.state is None:
            return False
        ok = self.put(workspace_add_body(self.state["policy"], path))
        if ok:
            self.draft = ""
            self.render()
        return ok

    def _choose(self) -> None:
        start = self.draft.strip() or str(Path.home())
        chosen = self.page.choose_directory(start)
        if chosen:
            self.add_path(chosen)


class WorkspacePage(SettingsPage):
    """Settings → Workspace (R11.1 FINAL): two levels of the one
    WorkspaceChooser, same words as the console and the other apps
    (``workspace_chooser.WORKSPACE_CHOOSER_TEXT`` = the ui-kit table).

    - "My default workspaces" — the ACCOUNT level, ``PUT
      /workspace/policy/me`` per change, "Follow the gateway policy".
    - "This chat" — the SESSION level of the open conversation, ``PUT
      /sessions/{id}/workspaces`` per change, "Use my default". The gateway
      stores it on the session and applies it at run start.

    No "Run workspace" row: a run's private workspace is automatic (the
    gateway's, per chat), and every other workspace is chosen here.
    """

    title = "Workspace"
    subtitle = "Which workspaces the assistant's agents may use, and how. Your gateway decides; changes apply at once."
    icon = "folder"

    def __init__(self, controller: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(controller, parent)
        self._gateway_local = bool(safe_call(controller, "gateway_is_local", default=True))
        self._session_id = ""
        self.account = _WorkspaceLevel(self, "account", WORKSPACE_ACCOUNT_TITLE, WT["accountHelp"], WT["followGateway"], WT["followGatewayHelp"])
        self.session = _WorkspaceLevel(self, "session", WORKSPACE_SESSION_TITLE, WT["sessionHelp"], WT["useDefault"], WT["useDefaultHelp"])
        self.add_card(self.account.card)
        self.add_card(self.session.card)
        private = QLabel(WT["privateNote"])
        private.setObjectName("cardHelp")
        private.setWordWrap(True)
        private.setProperty("workspace", "private-note")
        self.private_note = private
        self.session.card.add_widget(private)

    def refresh(self) -> None:
        payload = safe_call(self.controller, "workspace_policy", default=None)
        payload = payload if isinstance(payload, dict) else {}
        session = payload.get("session") if isinstance(payload.get("session"), dict) else {}
        self._session_id = str(session.get("session_id") or "")
        self.account.status = None
        self.session.status = None
        self.account.load(payload.get("account") or {"error": "The gateway did not answer."})
        self.session.load(session or {"error": "The gateway did not answer."})

    def _put(self, level: str, body: Dict[str, Any]) -> Dict[str, Any]:
        state = self.controller.put_workspace_policy(level, body, session_id=self._session_id)
        if level == "account":
            # "Use my default" follows the account: re-read this chat's level.
            self._reload_session()
        return state

    def _reload_session(self) -> None:
        payload = safe_call(self.controller, "workspace_policy", default=None)
        session = payload.get("session") if isinstance(payload, dict) else None
        if isinstance(session, dict) and session.get("session_id") == self._session_id:
            status = self.session.status
            self.session.load(session)
            self.session.status = status

    def choose_directory(self, start: str) -> str:
        """The folder picker ("Choose…"); a test replaces this."""
        return QFileDialog.getExistingDirectory(self, WT["addPlaceholder"], start) or ""

    @staticmethod
    def _clear(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # Hidden + deleteLater, never reparented to None: this runs
                # inside the clicked control's own signal (see common.py).
                widget.hide()
                widget.deleteLater()
            elif item.layout() is not None:
                WorkspacePage._clear(item.layout())


# ================================================================== Tools


_TOOLSET_ICONS = {
    "files": "folder",
    "web": "globe",
    "system": "terminal",
    "shell": "terminal",
    "camera": "camera",
    "comms": "mail",
    "agora": "bot",
}


class _ToolGroup(QFrame):
    """One gateway toolset as a collapsible panel (R10.4).

    Header: the toolset name (the toggle, with a chevron), the tool count,
    then "All auto" / "All ask" — pressed-state controls that SHOW whether
    every tool of the panel is on that mode and set it when pressed. The rows
    live in ``body``; collapsing hides the body, the filter hides rows.
    """

    def __init__(self, toolset: str, count: int, *, bulk: bool, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsCard")
        self.setProperty("toolGroup", toolset)
        self.toolset = toolset
        self.count = count
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.toggle = QPushButton(toolset)
        self.toggle.setObjectName("ghostButton")
        self.toggle.setCheckable(True)
        self.toggle.setAutoDefault(False)
        self.toggle.setStyleSheet("font-weight: 700; text-align: left; padding-left: 2px;")
        self.toggle.toggled.connect(self._apply_open)
        head.addWidget(self.toggle, 0)
        self.glyph = QLabel()
        self.glyph.setPixmap(
            symbol_icon(_TOOLSET_ICONS.get(toolset.split(".")[0], "spark"), color=THEME.text_muted, size=14).pixmap(14, 14)
        )
        head.addWidget(self.glyph, 0, Qt.AlignVCenter)
        self.count_chip = Chip(str(count), "neutral")
        self.count_chip.setProperty("toolGroup", "count")
        head.addWidget(self.count_chip, 0, Qt.AlignVCenter)
        head.addStretch(1)

        self.bulk = QFrame()
        self.bulk.setObjectName("segmented")
        bulk_box = QHBoxLayout(self.bulk)
        bulk_box.setContentsMargins(0, 0, 0, 0)
        bulk_box.setSpacing(0)
        self.all_auto = self._bulk_button("All auto", "first")
        self.all_auto.setToolTip(
            f"Every {toolset} tool pre-approved on this Mac (outreach and destructive tools stay on Ask)"
        )
        self.all_ask = self._bulk_button("All ask", "last")
        self.all_ask.setToolTip(f"Ask before running any {toolset} tool")
        bulk_box.addWidget(self.all_auto)
        bulk_box.addWidget(self.all_ask)
        head.addWidget(self.bulk, 0, Qt.AlignVCenter)
        self.bulk.setVisible(bulk)
        outer.addLayout(head)

        self.body = Card()
        self.body.setObjectName("toolGroupBody")
        self.body._layout.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.body)
        self._apply_open(False)

    def _bulk_button(self, text: str, position: str) -> QPushButton:
        b = QPushButton(text)
        b.setObjectName("segment")
        b.setProperty("segment", position)
        b.setCheckable(True)
        b.setAutoDefault(False)
        b.setFocusPolicy(Qt.StrongFocus)
        b.setAccessibleName(f"{text} — {self.toolset}")
        return b

    def _apply_open(self, opened: bool) -> None:
        self.body.setVisible(bool(opened))
        self.toggle.setIcon(symbol_icon("chevron-down" if opened else "chevron-right", color=THEME.text_secondary, size=14))
        verb = "Hide" if opened else "Show"
        self.toggle.setToolTip(f"{verb} the {self.toolset} tools")
        self.toggle.setAccessibleName(f"{self.toolset} tools, {self.count}")

    def set_open(self, opened: bool) -> None:
        self.toggle.blockSignals(True)
        self.toggle.setChecked(bool(opened))
        self.toggle.blockSignals(False)
        self._apply_open(bool(opened))

    def is_open(self) -> bool:
        return self.body.isVisibleTo(self)

    def set_bulk_state(self, auto: bool, ask: bool, enabled: bool) -> None:
        for b, on in ((self.all_auto, auto), (self.all_ask, ask)):
            b.blockSignals(True)
            b.setChecked(bool(on))
            b.blockSignals(False)
            b.setEnabled(bool(enabled))


class ToolsPage(SettingsPage):
    title = "Tools & permissions"
    nav_title = "Tools"
    subtitle = "How this Mac handles tool requests before they reach the gateway. Off and Ask narrow what the gateway allows; Auto pre-approves a tool even where the gateway would ask. Risk tiers come from the gateway."
    icon = "shield"
    selection_saved = pyqtSignal(object)

    def __init__(self, controller: Any, parent: Optional[QWidget] = None, *, selection_only: bool = False) -> None:
        self.selection_only = selection_only
        super().__init__(controller, parent)
        if selection_only:
            self.title_label.setText("Tools")
            self.subtitle_label.setText("Choose the tools available to this automation. Its approval setting controls when they may run.")
        self._rows: Dict[str, Dict[str, Any]] = {}
        self.groups: Dict[str, _ToolGroup] = {}
        # Panels the user opened or closed by hand (kept across refreshes).
        self._open_choice: Dict[str, bool] = {}
        # The gateway's command-sandbox state (GET /discovery/tools
        # `command_sandbox`) and the state chips of the process-spawning tools.
        self._command_sandbox: Dict[str, Any] = {}
        self._sandbox_chips: Dict[str, Chip] = {}
        self.mode_note = Note("", "info")
        self.body.addWidget(self.mode_note)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter tools")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._apply_filter)
        self.body.addWidget(self.search_edit)

        self._groups_host = QWidget()
        self._groups = QVBoxLayout(self._groups_host)
        self._groups.setContentsMargins(0, 0, 0, 0)
        self._groups.setSpacing(8)
        self.body.addWidget(self._groups_host)

        # No Save button: a tool's mode applies the moment it is picked. The
        # automation tool picker (selection_only) keeps its one dialog action.
        self.reset_button = button("Use gateway defaults", "secondary", tooltip="Set every tool back to the gateway's own approval default", on_click=self._reset_defaults)
        self.save_button_tools = button("Use selection", "primary", on_click=self._save)
        if selection_only:
            self.add_actions(self.save_button_tools)
            self.mode_note.hide()
        else:
            self.add_actions(self.reset_button)

    def _tool_mode_text(self, mode: str) -> str:
        mode_s = str(mode or "").strip().lower()
        if mode_s in {"approval", "local_approval", "local-approval"}:
            return "Gateway tool mode: approval — the gateway runs tools it classifies as safe and pauses on risky ones. This Mac can further restrict or pre-approve requests."
        if mode_s in {"local", "local_all", "local-all"}:
            return "Gateway tool mode: local — tools execute directly; this Mac can still block or pre-approve before submission."
        if mode_s == "passthrough":
            return "Gateway tool mode: passthrough — tool requests are forwarded downstream after this Mac's gating step."
        if mode_s in {"delegated", "delegate", "job"}:
            return "Gateway tool mode: delegated — tool calls wait for external executors after this Mac's gating step."
        return "The gateway did not report its tool mode. This Mac can still restrict tools; an unavailable gateway policy fails closed."

    def refresh(self) -> None:
        inventory = safe_call(self.controller, "tool_inventory", default=None) or {}
        items = inventory.get("items") if isinstance(inventory, dict) else []
        sandbox_state = (inventory or {}).get("command_sandbox") if isinstance(inventory, dict) else None
        self._command_sandbox = dict(sandbox_state) if isinstance(sandbox_state, dict) else {}
        self.mode_note.show_text(self._tool_mode_text(str((inventory or {}).get("tool_mode") or "")), "info")
        if self.selection_only:
            self.mode_note.hide()
        note = str((inventory or {}).get("note") or "").strip()
        if note:
            self.say(note, tone="warning")
        while self._groups.count():
            item = self._groups.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._rows = {}
        self._sandbox_chips: Dict[str, Chip] = {}
        self.groups = {}
        # The categories are the gateway's own `toolset` field on each tool
        # (GET /discovery/tools): no hand-made list, nothing read from names.
        by_toolset: Dict[str, List[dict]] = {}
        for item in items or []:
            if isinstance(item, dict) and str(item.get("name") or "").strip():
                by_toolset.setdefault(str(item.get("toolset") or "other"), []).append(item)
        self.save_button_tools.setEnabled(bool(by_toolset))
        self.reset_button.setEnabled(bool(by_toolset))
        if not by_toolset:
            empty = QLabel("No tools reported by the gateway — nothing to set until it answers.")
            empty.setObjectName("cardHelp")
            self._groups.addWidget(empty)
            return
        # Sorted by name (R11.5): a plain string sort, nothing else decides
        # the order (an all-disabled category no longer sinks to the end).
        for toolset in sorted(by_toolset):
            group = self._build_group(toolset, by_toolset[toolset])
            self.groups[toolset] = group
            self._groups.addWidget(group)
            self._sync_group_state(toolset)
        self._apply_filter()

    def _build_group(self, toolset: str, items: List[dict]) -> _ToolGroup:
        group = _ToolGroup(toolset, len(items), bulk=not self.selection_only)
        card = group.body
        group.all_auto.clicked.connect(lambda _c=False, t=toolset: self._set_group(t, "approve"))
        group.all_ask.clicked.connect(lambda _c=False, t=toolset: self._set_group(t, "ask"))
        group.toggle.clicked.connect(lambda checked, t=toolset: self._open_choice.__setitem__(t, bool(checked)))
        # ALL collapsed by default (R11.5), overrides included; a panel the
        # user opened by hand stays open across refreshes.
        group.set_open(self._open_choice.get(toolset, False))
        for item in sorted(items, key=lambda entry: str(entry.get("name") or "")):
            name = str(item.get("name") or "")
            risk = describe_tool_risk(item)
            available = item.get("available") is not False
            head = QWidget()
            head_row = QHBoxLayout(head)
            head_row.setContentsMargins(0, 0, 0, 0)
            head_row.setSpacing(8)
            title = QLabel(name)
            title.setObjectName("rowLabel")
            title.setMinimumWidth(40)
            head_row.addWidget(title, 1)
            # One tier chip; the concrete facts ride its tooltip so the row
            # stays one line wide at the dialog's minimum width.
            chip = Chip(risk["label"] if available else "Disabled on gateway", risk["tone"] if available else "warning")
            chip.setToolTip(str(risk.get("sentence") or "") if available else "The gateway has this tool switched off; approval cannot run it.")
            head_row.addWidget(chip)
            control = SegmentedControl([("disabled", "Off"), ("ask", "On")] if self.selection_only else [("disabled", "Off"), ("approve", "Auto"), ("ask", "Ask")])
            default = str(item.get("policy_default") or "ask")
            control.set_tooltips(
                {
                    "disabled": "Never offered to the model",
                    "approve": "Pre-approved on this Mac" + (" · gateway default" if default == "approve" else ""),
                    "ask": "Prompt every time" + (" · gateway default" if default == "ask" else ""),
                }
            )
            control.set_value(str(item.get("selected_mode") or default))
            if self.selection_only:
                control.set_tooltips({"disabled": "Never offered to the model", "ask": "Available under this automation's approval setting"})
                control.set_value("disabled" if item.get("selected_mode") == "disabled" else "ask")
            else:
                control.changed.connect(lambda value, n=name: self._on_tool_changed(n, value))
            control.setEnabled(available or (self.selection_only and item.get("selected_mode") != "disabled"))
            control.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            head_row.addWidget(control, 0)
            sandbox_chip = self._sandbox_chip(item)
            if sandbox_chip is not None:
                # Second line of the card: the command-sandbox state (R12.1).
                line = QWidget()
                stack = QVBoxLayout(line)
                stack.setContentsMargins(0, 0, 0, 0)
                stack.setSpacing(4)
                stack.addWidget(head)
                state_row = QHBoxLayout()
                state_row.setContentsMargins(0, 0, 0, 0)
                state_row.addWidget(sandbox_chip, 1 if sandbox_chip.wordWrap() else 0)
                if not sandbox_chip.wordWrap():
                    state_row.addStretch(1)
                stack.addLayout(state_row)
                head = line
            desc_bits = [str(item.get("description") or "").strip(), str(item.get("when_to_use") or "").strip()]
            full_description = " ".join(bit for bit in desc_bits if bit) or "No description available."
            description = short_description(full_description)
            row = card.add_row("", head, help_text=description)
            help_label = getattr(row, "help_label", None)
            if help_label is not None and full_description != description:
                help_label.setToolTip(full_description)
            self._rows[name] = {
                "row": row,
                "control": control,
                "default_mode": default,
                "saved_mode": control.value(),
                "toolset": toolset,
                "available": available,
                "match": True,
                "rank": int(risk.get("rank") or 0),
                "search": f"{name}\n{full_description}\n{toolset}".lower(),
            }
        return group

    def _sandbox_chip(self, item: Dict[str, Any]) -> Optional[Chip]:
        """The command-sandbox state of a process-spawning tool, exactly as the
        gateway reports it: the row's `sandbox` text is the label, the
        inventory's `command_sandbox.sentence` its tooltip. A tool the gateway
        does not mark gets nothing (no client-side guess)."""
        label = str(item.get("sandbox") or "").strip()
        if not label or not isinstance(item.get("sandboxed"), bool):
            return None
        state = str(self._command_sandbox.get("state") or "").strip().lower()
        if item["sandboxed"]:
            tone = "success"
        elif state == "unsandboxed":
            tone = "danger"
        else:
            tone = "warning"
        chip = Chip(label, tone)
        chip.setObjectName("chip")
        chip.setProperty("sandboxState", "sandboxed" if item["sandboxed"] else (state or "refused"))
        # One line for the usual short states; a long state (the Landlock
        # partial sentence) wraps across the card's width instead of
        # widening the dialog.
        if len(label) > 60:
            chip.setWordWrap(True)
            chip.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        chip.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        sentence = str(self._command_sandbox.get("sentence") or "").strip()
        chip.setToolTip(sentence or label)
        chip.setAccessibleName(f"Command sandbox: {label}")
        self._sandbox_chips[str(item.get("name") or "")] = chip
        return chip

    # "All auto" never reaches outreach (3) / destroy (4): those are set to
    # Auto one tool at a time, by name.
    ALL_AUTO_MAX_RANK = 2

    def _group_rows(self, toolset: str) -> List[Dict[str, Any]]:
        return [info for info in self._rows.values() if info["toolset"] == toolset and info["available"]]

    def _sync_group_state(self, toolset: str) -> None:
        """Pressed state = the truth of the rows: "All auto" is pressed when
        every tool "All auto" may reach is on Auto, "All ask" when every tool
        of the panel is on Ask; neither when they are mixed."""
        group = self.groups.get(toolset)
        if group is None:
            return
        rows = self._group_rows(toolset)
        eligible = [info for info in rows if int(info.get("rank") or 0) <= self.ALL_AUTO_MAX_RANK]
        auto = bool(eligible) and all(info["control"].value() == "approve" for info in eligible)
        ask = bool(rows) and all(info["control"].value() == "ask" for info in rows)
        group.set_bulk_state(auto, ask, enabled=bool(rows))
        group.all_auto.setEnabled(bool(eligible))

    def _set_group(self, toolset: str, mode: str) -> None:
        skipped: List[str] = []
        hidden = 0
        changed: List[str] = []
        for name, info in self._rows.items():
            if info["toolset"] != toolset or not info["available"]:
                continue
            # Only what the filter shows: with a filter applied this used to
            # pre-approve mutating tools that were not on screen.
            if not info.get("match", True):
                hidden += 1
                continue
            if mode == "approve" and int(info.get("rank") or 0) > self.ALL_AUTO_MAX_RANK:
                skipped.append(name)
                continue
            if info["control"].value() != mode:
                info["control"].set_value(mode)
                changed.append(name)
        saved = self._persist(changed) if changed else True
        self._sync_group_state(toolset)
        if not saved:
            return
        if skipped and mode == "approve":
            self.say(
                "Left on Ask (outreach or destructive): " + ", ".join(sorted(skipped)) + ". Set them to Auto individually if you mean it.",
                tone="warning",
            )
        elif hidden:
            self.say(
                f"Applied to the {len(self._group_rows(toolset)) - hidden} tool(s) shown; "
                f"{hidden} hidden by the filter were left alone.",
                tone="info",
            )
        elif changed:
            self.say("Saved on this device.")

    def _on_tool_changed(self, name: str, value: str) -> None:
        info = self._rows.get(name)
        if info is None:
            return
        if self._persist([name]):
            self.say("Saved on this device.")
        self._sync_group_state(info["toolset"])

    def _apply_filter(self) -> None:
        query = str(self.search_edit.text() or "").strip().lower()
        matches: Dict[str, int] = {}
        for info in self._rows.values():
            hit = not query or query in info["search"]
            info["match"] = hit
            info["row"].setVisible(hit)
            matches[info["toolset"]] = matches.get(info["toolset"], 0) + (1 if hit else 0)
        for toolset, group in self.groups.items():
            found = matches.get(toolset, 0)
            if query:
                # The filter searches every panel: panels with a hit open to
                # show it, the others step aside.
                group.setVisible(found > 0)
                group.set_open(found > 0)
                group.count_chip.setText(f"{found} of {group.count}")
            else:
                group.setVisible(True)
                group.set_open(self._open_choice.get(toolset, False))
                group.count_chip.setText(str(group.count))

    def _reset_defaults(self) -> None:
        changed = []
        for name, info in self._rows.items():
            if info["control"].value() != info["default_mode"]:
                info["control"].set_value(info["default_mode"])
                changed.append(name)
        if self.selection_only:
            return
        if changed and not self._persist(changed):
            return
        for toolset in self.groups:
            self._sync_group_state(toolset)
        self.say("Every tool follows the gateway's approval default again.", tone="info")

    def _statuses(self) -> Dict[str, str]:
        """Only rows that differ from the gateway's default are stored, so a
        tool left on its default keeps following the gateway if that changes.
        Start from what is already saved: the gateway's inventory varies with
        what is connected, and rebuilding the map from this refresh alone
        silently dropped saved modes for tools it did not list this time."""
        statuses = dict(safe_attr(_prefs(self.controller), "tool_preferences", {}) or {})
        for name, info in self._rows.items():
            chosen = str(info["control"].value() or "ask")
            if chosen != str(info.get("default_mode") or "ask"):
                statuses[name] = chosen
            else:
                statuses.pop(name, None)
        return statuses

    def _persist(self, names: List[str]) -> bool:
        """Apply on change. A failed save puts the changed rows back and says
        "Not saved." with the reason."""
        saver = getattr(self.controller, "save_tool_preferences", None)
        try:
            if not callable(saver):
                raise RuntimeError("this build cannot store tool permissions")
            saver(self._statuses())
        except Exception as exc:
            for name in names:
                info = self._rows.get(name)
                if info is not None:
                    info["control"].set_value(info["saved_mode"])
            self.say(f"Not saved. {exc}", tone="error")
            return False
        for name in names:
            info = self._rows.get(name)
            if info is not None:
                info["saved_mode"] = info["control"].value()
        self.changed.emit()
        return True

    def _save(self) -> None:
        if not self._rows:
            self.say("Nothing to choose: the gateway reported no tools.", tone="warning")
            return
        if self.selection_only:
            self.selection_saved.emit([name for name, info in self._rows.items() if info["control"].value() != "disabled"])
            return
        if self._persist(list(self._rows)):
            self.say("Saved on this device.")


# ================================================================= Window


# (key cap, what it does). Every entry is a real QShortcut in app.py or the
# approval sheet; nothing here is aspirational.
_SHORTCUTS = (
    ("⏎", "Send"),
    ("⇧⏎", "New line"),
    ("Esc", "Stop speech, then hide the window"),
    ("⌘.", "Stop the run"),
    ("⌘N", "New chat"),
    ("⌘,", "Settings"),
    ("⌘⇧V", "Start or end a voice conversation"),
)
_APPROVAL_SHORTCUTS = (
    ("⏎", "Allow once"),
    ("⌘D", "Deny"),
    ("Esc", "Decide later"),
    ("F", "Show the full call"),
)


class WindowPage(SettingsPage):
    title = "Appearance & window"
    nav_title = "Appearance"
    subtitle = "Applies to this app on this Mac."
    icon = "keyboard"

    def __init__(self, controller: Any, apply_hotkey, parent: Optional[QWidget] = None) -> None:
        super().__init__(controller, parent)
        self._apply_hotkey = apply_hotkey

        appearance = self.add_card(
            Card(
                "Theme",
                "The colour palettes the rest of AbstractFramework uses. The choice "
                "applies to every window here — chat, settings, dialogs — and is "
                "remembered on this Mac.",
            )
        )
        self.theme_combo = QComboBox()
        self.theme_combo.setMinimumContentsLength(18)
        self._populate_themes()
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        appearance.add_row(
            "Theme",
            self.theme_combo,
            stretch_control=False,
            help_text="Light palettes are grouped at the end of the list.",
        )

        reading = self.add_card(
            Card(
                "Reading",
                "How replies are set in the chat. Takes effect immediately.",
            )
        )
        self.text_size = QSpinBox()
        self.text_size.setRange(10, 22)
        self.text_size.setSuffix(" px")
        self.text_size.valueChanged.connect(self._on_typography_changed)
        reading.add_row("Text size", self.text_size, stretch_control=False)
        self.line_spacing = QDoubleSpinBox()
        self.line_spacing.setRange(1.0, 2.2)
        self.line_spacing.setSingleStep(0.05)
        self.line_spacing.setDecimals(2)
        self.line_spacing.valueChanged.connect(self._on_typography_changed)
        reading.add_row(
            "Line spacing",
            self.line_spacing,
            stretch_control=False,
            help_text="Space between the lines of one paragraph, as a multiple of the text size.",
        )
        self.paragraph_spacing = QSpinBox()
        self.paragraph_spacing.setRange(0, 28)
        self.paragraph_spacing.setSuffix(" px")
        self.paragraph_spacing.valueChanged.connect(self._on_typography_changed)
        reading.add_row("Paragraph gap", self.paragraph_spacing, stretch_control=False)
        self.bullet_spacing = QSpinBox()
        self.bullet_spacing.setRange(0, 16)
        self.bullet_spacing.setSuffix(" px")
        self.bullet_spacing.valueChanged.connect(self._on_typography_changed)
        reading.add_row(
            "Bullet gap",
            self.bullet_spacing,
            stretch_control=False,
            help_text="Space between items of a list.",
        )

        summon = self.add_card(Card("Global shortcut"))
        self.hotkey_enabled = AfSwitch("Summon the assistant from anywhere")
        self.hotkey_enabled.clicked.connect(self._apply_hotkey_switch)
        summon.add_row("Summon", self.hotkey_enabled)
        self.hotkey_edit = QLineEdit()
        self.hotkey_edit.setPlaceholderText("cmd+shift+space")
        self.hotkey_edit.setMinimumWidth(160)
        # Applies when the field is left or Return is pressed (no Save).
        self.hotkey_edit.editingFinished.connect(self._apply_hotkey_sequence)
        summon.add_row("Key combination", self.hotkey_edit, stretch_control=False)
        # macOS Accessibility (R10.4): the state as a themed chip, a Configure
        # button (system prompt + the Privacy & Security → Accessibility pane),
        # re-checked whenever the app becomes active again or the page is shown.
        self.accessibility_state = Chip("", "neutral")
        self.accessibility_state.setProperty("hotkey", "accessibility-state")
        self.accessibility_configure = button(
            "Configure",
            "secondary",
            tooltip="Ask macOS for Accessibility access and open Privacy & Security → Accessibility",
            on_click=self._configure_accessibility,
        )
        self._accessibility_row = summon.add_row(
            "Accessibility",
            self.accessibility_state,
            trailing=[self.accessibility_configure],
            stretch_control=False,
            help_text="Works anywhere once macOS grants Accessibility access; otherwise use the menu bar icon.",
        )
        self._accessibility: Optional[bool] = None

        window = self.add_card(Card("Window size", "Limited by the screen. The chat takes whatever height remains after the header and composer."))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(*WINDOW_WIDTH_RANGE)
        self.width_spin.setSuffix(" px")
        window.add_row("Width", self.width_spin, stretch_control=False, help_text="Up to 62% of the screen the window is on.")
        self.height_spin = QSpinBox()
        # Must reach the app's own default (286): a floor above it meant
        # applying this page silently grew the window.
        self.height_spin.setRange(240, 880)
        self.height_spin.setSuffix(" px")
        window.add_row("Expanded height", self.height_spin, stretch_control=False, help_text="Height of the window once the chat opens fully.")
        self.bottom_offset_spin = QSpinBox()
        self.bottom_offset_spin.setRange(*SCREEN_EDGE_GAP_RANGE)
        self.bottom_offset_spin.setSuffix(" px")
        window.add_row("Screen edge gap", self.bottom_offset_spin, stretch_control=False, help_text="Space kept between the window and the edge of the screen (at most a quarter of the screen).")
        # Apply on change, no Save: typing applies on Return / leaving the
        # field (no keyboard tracking), the arrows apply each step.
        for spin in (self.width_spin, self.height_spin, self.bottom_offset_spin):
            spin.setKeyboardTracking(False)
            spin.valueChanged.connect(self._apply_window_size)

        shortcuts = self.add_card(Card("Keyboard shortcuts"))
        shortcuts.add_widget(self._shortcut_grid(_SHORTCUTS))
        approval_title = QLabel("In the approval sheet")
        approval_title.setObjectName("rowLabel")
        approval_title.setContentsMargins(0, 6, 0, 0)
        shortcuts.add_widget(approval_title)
        shortcuts.add_widget(self._shortcut_grid(_APPROVAL_SHORTCUTS))

    @staticmethod
    def _shortcut_grid(entries) -> QWidget:
        host = QWidget()
        grid = QGridLayout(host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)
        for row, (keys, action) in enumerate(entries):
            cap = QLabel(keys)
            cap.setObjectName("keyHint")
            cap.setAlignment(Qt.AlignCenter)
            grid.addWidget(cap, row, 0, Qt.AlignLeft | Qt.AlignVCenter)
            label = QLabel(action)
            label.setObjectName("rowValue")
            grid.addWidget(label, row, 1, Qt.AlignLeft | Qt.AlignVCenter)
        return host

    def _populate_themes(self) -> None:
        from ...ui_themes import theme_options

        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        last_group = None
        for theme_id, label, group in theme_options():
            if last_group is not None and group != last_group:
                self.theme_combo.insertSeparator(self.theme_combo.count())
            last_group = group
            self.theme_combo.addItem(label, theme_id)
        self.theme_combo.blockSignals(False)

    def _select_current_theme(self) -> None:
        from ...preferences import normalize_ui_theme

        current = normalize_ui_theme(safe_attr(_prefs(self.controller), "ui_theme", ""))
        index = self.theme_combo.findData(current)
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentIndex(max(0, index))
        self.theme_combo.blockSignals(False)

    def _on_theme_changed(self, _index: int) -> None:
        theme_id = str(self.theme_combo.currentData() or "")
        if not theme_id:
            return
        # The palette owns the switch: it repaints every window and re-renders
        # the transcript, then saves the choice.
        applier = getattr(self.controller, "apply_theme", None)
        if not callable(applier):
            self.say("Could not apply the theme.", tone="error")
            self.changed.emit()
            return
        # The return value is the SAVE, not the repaint. Ignoring it is how a
        # theme could be applied on screen and silently not written: the app
        # looked switched, and the next launch came back on the old one with
        # nothing having said so.
        if applier(theme_id):
            self.say("Theme applied and saved on this device.")
        else:
            self.say(
                "Theme applied, but it could not be saved — it will revert on the next launch.",
                tone="error",
            )
        self.changed.emit()

    def _on_typography_changed(self, _value=None) -> None:
        if bool(getattr(self, "_loading_typography", False)):
            return
        applier = getattr(self.controller, "apply_typography", None)
        if not callable(applier):
            self.say("Could not apply the text settings.", tone="error")
            return
        ok = applier(
            text_size=int(self.text_size.value()),
            line_spacing=float(self.line_spacing.value()),
            paragraph_spacing=int(self.paragraph_spacing.value()),
            bullet_spacing=int(self.bullet_spacing.value()),
        )
        self.say("Saved on this device." if ok else "Not saved. The text settings could not be stored.",
                 tone="" if ok else "error")

    def _load_typography(self, prefs: Any) -> None:
        self._loading_typography = True
        try:
            self.text_size.setValue(int(safe_attr(prefs, "text_size", 13) or 13))
            self.line_spacing.setValue(float(safe_attr(prefs, "line_spacing", 1.45) or 1.45))
            self.paragraph_spacing.setValue(int(safe_attr(prefs, "paragraph_spacing", 10)))
            self.bullet_spacing.setValue(int(safe_attr(prefs, "bullet_spacing", 3)))
        finally:
            self._loading_typography = False

    def refresh(self) -> None:
        self._select_current_theme()
        prefs = _prefs(self.controller)
        self._load_typography(prefs)
        self.hotkey_enabled.setChecked(bool(safe_attr(prefs, "hotkey_enabled", True)))
        self.hotkey_edit.setText(str(safe_attr(prefs, "hotkey_sequence", "cmd+shift+space") or "cmd+shift+space"))
        self._loading_window = True
        try:
            self.width_spin.setValue(int(safe_attr(prefs, "window_width", DEFAULT_WINDOW_WIDTH) or DEFAULT_WINDOW_WIDTH))
            self.height_spin.setValue(int(safe_attr(prefs, "window_height", DEFAULT_WINDOW_HEIGHT) or DEFAULT_WINDOW_HEIGHT))
            # 0 is a real choice (flush with the screen edge): never `or` it away.
            gap = safe_attr(prefs, "bottom_offset", DEFAULT_SCREEN_EDGE_GAP)
            self.bottom_offset_spin.setValue(DEFAULT_SCREEN_EDGE_GAP if gap is None else int(gap))
        finally:
            self._loading_window = False
        self.refresh_accessibility()

    # ---- macOS Accessibility (global shortcut)

    def refresh_accessibility(self) -> Optional[bool]:
        """Re-read the permission (never prompts) and show it. When it has
        just been granted and the shortcut is on, arm the shortcut now."""
        from ... import hotkey as hotkey_module

        state = hotkey_module.accessibility_state()
        previous = self._accessibility
        self._accessibility = state
        self._accessibility_row.setVisible(state is not None)
        if state is True:
            self.accessibility_state.setText("Granted")
            self.accessibility_state.set_tone("ok")
        else:
            self.accessibility_state.setText("Not granted")
            self.accessibility_state.set_tone("warning")
        if state is True and previous is False and self.hotkey_enabled.isChecked():
            failure = self._run_apply_hotkey()
            self.say(
                f"Accessibility granted, but the global shortcut did not start: {failure}" if failure
                else "Accessibility granted — the global shortcut is on.",
                tone="error" if failure else "ok",
            )
        elif state is True and previous is False:
            self.say("Accessibility granted.")
        return state

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt API
        # Coming back from System Settings re-activates the Settings window:
        # every widget of it gets ActivationChange, so re-check here (a page
        # never connects to an application-wide signal it could outlive).
        super().changeEvent(event)
        if event.type() == QEvent.ActivationChange and self.isVisible():
            self.refresh_accessibility()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self.refresh_accessibility()

    def _configure_accessibility(self) -> None:
        from ... import hotkey as hotkey_module

        try:
            hotkey_module.request_accessibility()
        except Exception as exc:  # the pane below is still the way in
            import logging

            logging.getLogger(__name__).warning("#FALLBACK: Accessibility prompt failed (%s)", exc)
        opened = hotkey_module.open_accessibility_settings()
        state = self.refresh_accessibility()
        if state is True:
            self.say("macOS already allows this app to read the keyboard.")
        elif opened:
            self.say("Allow this app in the Accessibility list that opened; this page updates when you come back.", tone="info")
        else:
            self.say("Open System Settings → Privacy & Security → Accessibility and allow this app.", tone="warning")

    def _run_apply_hotkey(self) -> Optional[str]:
        try:
            if callable(self._apply_hotkey):
                result = self._apply_hotkey()
                return result if isinstance(result, str) and result.strip() else None
        except Exception as exc:
            return str(exc) or "The shortcut could not be registered."
        return None

    def _apply_hotkey_sequence(self) -> None:
        sequence = self.hotkey_edit.text().strip() or "cmd+shift+space"
        if sequence == str(safe_attr(_prefs(self.controller), "hotkey_sequence", "") or ""):
            return
        if not _update_prefs(self.controller, hotkey_sequence=sequence):
            self.say("Not saved. The key combination could not be stored.", tone="error")
            return
        failure = self._run_apply_hotkey() if self.hotkey_enabled.isChecked() else None
        if failure:
            self.say(f"Saved {sequence}, but the global shortcut did not start: {failure}", tone="error")
        else:
            self.say(f"Saved on this device: {sequence}.")
        self.changed.emit()

    def _apply_window_size(self, _value=None) -> None:
        if getattr(self, "_loading_window", False):
            return
        ok = _update_prefs(
            self.controller,
            window_width=int(self.width_spin.value()),
            window_height=int(self.height_spin.value()),
            bottom_offset=int(self.bottom_offset_spin.value()),
        )
        if not ok:
            self.say("Not saved. The window size could not be stored.", tone="error")
            return
        self.say("Saved on this device.")
        self.changed.emit()

    def _apply_hotkey_switch(self, checked: bool) -> None:
        """The global shortcut switch applies at once (no Save)."""
        if not _update_prefs(self.controller, hotkey_enabled=bool(checked)):
            self.hotkey_enabled.blockSignals(True)
            self.hotkey_enabled.setChecked(not checked)
            self.hotkey_enabled.blockSignals(False)
            self.say("Not saved. The global shortcut could not be stored.", tone="error")
            return
        failure: Optional[str] = None
        try:
            if callable(self._apply_hotkey):
                result = self._apply_hotkey()
                failure = result if isinstance(result, str) and result.strip() else None
        except Exception as exc:
            failure = str(exc) or "The shortcut could not be registered."
        if checked and failure:
            # Saved ON, but not armed: say so instead of "on".
            self.say(f"The global shortcut is saved as on but did not start: {failure}", tone="error")
        else:
            self.say("The global shortcut is on." if checked else "The global shortcut is off.")
        self.changed.emit()

    def _save_preferences(self) -> None:
        ok = _update_prefs(
            self.controller,
            hotkey_enabled=bool(self.hotkey_enabled.isChecked()),
            hotkey_sequence=self.hotkey_edit.text().strip() or "cmd+shift+space",
            window_width=int(self.width_spin.value()),
            window_height=int(self.height_spin.value()),
            bottom_offset=int(self.bottom_offset_spin.value()),
        )
        if not ok:
            self.say("Not saved. The window settings could not be stored.", tone="error")
            return
        try:
            if callable(self._apply_hotkey):
                self._apply_hotkey()
        except Exception:
            pass
        self.say("Saved on this device.")
        self.changed.emit()


# ================================================================== About


def _assistant_version() -> str:
    # The package's own __version__ (the one `assistant --version` prints):
    # correct in an editable checkout and in the .app, where there may be no
    # dist-info metadata to read.
    from ... import __version__

    return __version__


def _gateway_rows(controller: Any) -> List[Any]:
    """Gateway version rows, formatted by the framework (the same lines every
    AbstractFramework About screen shows)."""
    from abstractcore.utils.identity import gateway_version_rows

    about = safe_call(controller, "gateway_about", cached_only=True, default=None)
    payload, error = about if isinstance(about, tuple) and len(about) == 2 else (None, "not connected")
    return gateway_version_rows(payload, error)


def _identity_fields(version: str) -> List[Any]:
    """(label, value) rows for the About card, straight from the framework
    descriptor. A missing entry for this app is a packaging bug and raises."""
    from abstractcore.utils.identity import about_fields, app_identity

    return about_fields(app_identity("abstractassistant", version))


def _identity_html_rows(version: str) -> Dict[str, str]:
    """Rich text per About row, rendered by the framework's ``about_html`` (one
    link rule for every app: URLs inside a value become links, only Contact is
    a mailto). ``about_html`` joins ``<b>Label:</b> value`` rows with
    ``<br>``; each row is split back out for the card's label column."""
    from html import escape

    from abstractcore.utils.identity import about_html, app_identity

    rendered = about_html(app_identity("abstractassistant", version))
    labels = [label for label, _value in _identity_fields(version)]
    parts = rendered.split("<br>")
    if len(parts) != len(labels):
        raise RuntimeError("abstractcore about_html rows do not match about_fields")
    out: Dict[str, str] = {}
    for label, part in zip(labels, parts):
        prefix = f"<b>{escape(label, quote=True)}:</b> "
        if not part.startswith(prefix):
            raise RuntimeError(f"unexpected about_html row for {label!r}")
        out[label] = part[len(prefix):]
    return out


def describe_workflow_selection(workflow: Any) -> str:
    """One line for the About page: what the NEXT turn runs, and why."""
    if workflow is None:
        return "not resolved"
    bundle_id = str(getattr(workflow, "bundle_id", "") or "")
    flow_id = str(getattr(workflow, "flow_id", "") or "")
    version = str(getattr(workflow, "bundle_version", "") or "")
    label = str(getattr(workflow, "label", "") or "") or bundle_id
    at = workflow_version_suffix(bundle_id, version)
    source = str(getattr(workflow, "source", "") or "")
    if flow_id == WORKFLOW_GATEWAY_DEFAULT:
        return f"Gateway default \u2192 {label}{at} ({bundle_id})"
    if source == "built_in":
        at = workflow_version_suffix(bundle_id, version, named_built_in=True)
        return f"Built-in orchestrator{at} ({bundle_id}:{flow_id})"
    return f"{label}{at} ({bundle_id}:{flow_id})"


def describe_resolved_workflow(resolved: Any) -> str:
    """The gateway's ``resolved_workflow`` for the last run start."""
    if not isinstance(resolved, dict) or not resolved:
        return "No turn yet in this session of the app"
    bundle_id = str(resolved.get("bundle_id") or "")
    version = str(resolved.get("bundle_version") or "")
    flow_id = str(resolved.get("flow_id") or "")
    name = str(resolved.get("name") or "") or bundle_id
    source = str(resolved.get("source") or "")
    origin = {"gateway_default": "the gateway default", "client": "chosen by this app"}.get(source, source)
    at = workflow_version_suffix(bundle_id, version)
    return f"{name}{at} ({bundle_id}:{flow_id})" + (f" \u2014 {origin}" if origin else "")


class AboutPage(SettingsPage):
    title = "About"
    subtitle = ""
    icon = "info"

    def __init__(self, controller: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(controller, parent)
        # Identity rows come from the framework's ONE descriptor
        # (abstractcore.utils.identity, vendored from AbstractFramework's
        # identity/abstractframework.json): every app's About shows the same
        # facts, and none of them is typed here.
        card = self.add_card(Card("AbstractAssistant"))
        self.identity_labels: Dict[str, QLabel] = {}
        for label, _value in _identity_fields(_assistant_version()):
            value_label = QLabel("")
            value_label.setObjectName("rowValue")
            value_label.setWordWrap(True)
            value_label.setTextFormat(Qt.RichText)
            value_label.setOpenExternalLinks(True)
            value_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
            card.add_row(label, value_label)
            self.identity_labels[label] = value_label
        self.version_label = self.identity_labels.get("Application") or QLabel("")

        setup = self.add_card(Card("This installation"))
        self.stack_label = QLabel("")
        self.stack_label.setObjectName("rowValue")
        self.stack_label.setWordWrap(True)
        self.stack_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        setup.add_row("Gateway", self.stack_label)
        self.workflow_label = QLabel("")
        self.workflow_label.setObjectName("rowValue")
        self.workflow_label.setWordWrap(True)
        setup.add_row("Workflow", self.workflow_label)
        self.resolved_label = QLabel("")
        self.resolved_label.setObjectName("rowValue")
        self.resolved_label.setWordWrap(True)
        self.resolved_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        setup.add_row("Last turn ran", self.resolved_label)
        self.data_label = QLabel("")
        self.data_label.setObjectName("rowValue")
        self.data_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # A path is arbitrarily long and the window is sized to its widest
        # page: unwrapped, one deep data folder pushed every other page wider.
        self.data_label.setWordWrap(True)
        reveal = button("Reveal in Finder", "secondary", on_click=self._reveal)
        setup.add_row("Data folder", self.data_label, trailing=[reveal])
        self.copy_button = button("Copy diagnostics", "secondary", tooltip="Versions, connection (no secrets), workflow and preferences", on_click=self._copy_diagnostics)
        self.add_actions(self.copy_button)

    def _diagnostics(self) -> Dict[str, Any]:
        version = _assistant_version()
        manager = safe_attr(self.controller, "llm_manager", None)
        caps = safe_call(manager, "gateway_capabilities", stale_ok=True, default=None)
        raw = safe_attr(caps, "raw", {}) or {}
        stack: Dict[str, str] = {}
        if isinstance(raw, dict):
            for key in ("abstractgateway", "abstractruntime", "abstractcore", "abstractvoice", "abstractvision", "abstractmemory"):
                entry = raw.get(key)
                if isinstance(entry, dict):
                    stack[key] = str(entry.get("version") or "") if entry.get("installed", True) else "not installed"
        contracts = raw.get("contracts") if isinstance(raw, dict) else None
        if isinstance(contracts, dict) and contracts.get("version") is not None:
            stack["contracts"] = f"v{contracts.get('version')}"
        workflow = safe_call(self.controller, "current_workflow", default=None)
        resolved = safe_call(self.controller, "last_resolved_workflow", default=None)
        connection = safe_call(self.controller, "current_connection", default=None)
        prefs = _prefs(self.controller)
        return {
            "assistant": version,
            "about": [f"{label}: {value}" for label, value in _identity_fields(version)],
            "gateway": [f"{label}: {value}" for label, value in _gateway_rows(self.controller)],
            "stack": stack,
            "workflow": describe_workflow_selection(workflow),
            "resolved_workflow": resolved if isinstance(resolved, dict) else None,
            "gateway_url": str(getattr(connection, "base_url", "") or ""),
            "auth_mode": str(getattr(connection, "auth_mode", "") or ""),
            "data_dir": str(safe_attr(self.controller, "data_dir", "") or ""),
            "preferences": prefs.to_dict() if hasattr(prefs, "to_dict") else {},
        }

    def refresh(self) -> None:
        diag = self._diagnostics()
        link_style = f'style="color: {THEME.accent}; text-decoration: none;" '
        for label, html in _identity_html_rows(str(diag["assistant"])).items():
            widget = self.identity_labels.get(label)
            if widget is not None:
                # Theme colour for links; the markup itself is core's.
                widget.setText(html.replace("<a href=", f"<a {link_style}href="))
        self.stack_label.setText("\n".join(diag["gateway"]))
        self.workflow_label.setText(str(diag["workflow"]))
        self.resolved_label.setText(describe_resolved_workflow(diag.get("resolved_workflow")))
        self.data_label.setText(str(diag["data_dir"] or "~/.abstractassistant"))

    def _reveal(self) -> None:
        path = str(safe_attr(self.controller, "data_dir", "") or (Path.home() / ".abstractassistant"))
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _copy_diagnostics(self) -> None:
        diag = self._diagnostics()
        diag["preferences"] = {k: v for k, v in dict(diag.get("preferences") or {}).items()}
        try:
            QApplication.clipboard().setText(json.dumps(diag, indent=2, ensure_ascii=False))
            self.say("Diagnostics copied (no tokens included).")
        except Exception as exc:
            self.say(f"Could not copy: {exc}", tone="error")


__all__ = [
    "AboutPage",
    "ConnectionPage",
    "ModelsPage",
    "ToolsPage",
    "VoicePage",
    "WindowPage",
    "WorkspacePage",
    "short_description",
]

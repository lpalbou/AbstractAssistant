"""The seven Settings pages.

Persistence legend (also in docs/settings.md):
- conn  = ~/.abstractassistant/gateway_connection.json
- pref  = ~/.abstractassistant/preferences.json (local, per device, sent per request)
- ro    = read-only mirror of gateway truth (never written by the assistant)

Layout conventions (shared with ``common.py``): every row has a label in the
left column — checkboxes included — so controls line up down the page; the
page's persistent actions (Save, Connect, …) live in the footer next to the
feedback line, never inside a card.
"""

from __future__ import annotations

import json
import platform
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
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

from ...config import DEFAULT_GATEWAY_URL
from ...core.tool_risk import describe_tool_risk
from ...icons import symbol_icon
from ...preferences import (
    DEFAULT_SCREEN_EDGE_GAP,
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    REASONING_EFFORT_LEVELS,
    SCREEN_EDGE_GAP_RANGE,
    WINDOW_WIDTH_RANGE,
    WORKFLOW_GATEWAY_DEFAULT,
    WORKSPACE_ACCESS_MODES,
    normalize_workspace_path,
)
from ...theme import THEME
from .common import Card, Chip, Note, SegmentedControl, SettingsPage, button, safe_attr, safe_call
from .route_editor import OVERRIDE_ROUTE_LABELS, RouteOverrideEditor


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
        self.gateway_url_edit.setPlaceholderText(DEFAULT_GATEWAY_URL)
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

        self.remember_session = QCheckBox("Keep the session after this app closes")
        self._remember_row = form.add_row("Session", self.remember_session)

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
        self.gateway_url_edit.setText(str(getattr(connection, "base_url", "") or DEFAULT_GATEWAY_URL))
        idx = self.auth_mode_combo.findData(str(getattr(connection, "auth_mode", "bearer") or "bearer"))
        if idx >= 0:
            self.auth_mode_combo.setCurrentIndex(idx)
        self.bearer_token_edit.setText(str(getattr(connection, "auth_token", "") or ""))
        self.gateway_user_edit.setText(str(getattr(connection, "user_id", "") or ""))
        self.remember_session.setChecked(bool(getattr(connection, "remember_session", True)))
        self.gateway_user_token_edit.clear()
        self._refresh_connection_fields()

    def _refresh_connection_fields(self) -> None:
        is_bearer = str(self.auth_mode_combo.currentData() or "bearer") == "bearer"
        self._bearer_row.setVisible(is_bearer)
        self._user_row.setVisible(not is_bearer)
        self._user_token_row.setVisible(not is_bearer)
        self._remember_row.setVisible(not is_bearer)

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
        base_url = self.gateway_url_edit.text().strip() or DEFAULT_GATEWAY_URL
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
                    remember=bool(self.remember_session.isChecked()),
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
        base_url = self.gateway_url_edit.text().strip() or DEFAULT_GATEWAY_URL
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

        # WHICH WORKFLOW runs each turn (contract D). The gateway's default is
        # always the first row and is saved as "@default", never as a copy of
        # its id, so an operator's later change applies to the next turn.
        workflow = self.add_card(
            Card("Workflow", "The agent workflow each new turn runs. A turn already running keeps its workflow.")
        )
        self.workflow_combo = QComboBox()
        self.workflow_combo.setMinimumWidth(320)
        self.workflow_combo.activated.connect(self._on_workflow_chosen)
        workflow.add_row("Runs", self.workflow_combo, stretch_control=False)
        self.workflow_detail = QLabel("")
        self.workflow_detail.setObjectName("rowHelp")
        self.workflow_detail.setWordWrap(True)
        workflow.add_widget(self.workflow_detail)
        self._workflow_rows: List[Dict[str, Any]] = []

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
        self._refresh_workflows()
        self.route_editor.refresh()

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
            self.workflow_detail.setText("Not connected \u2014 the gateway's workflows are not known yet.")

    def _on_workflow_chosen(self, index: int) -> None:
        if not (0 <= index < len(self._workflow_rows)):
            return
        choice = self._workflow_rows[index].get("choice")
        try:
            self.controller.set_workflow_choice(choice)
        except Exception as exc:
            self.say(f"Could not save the workflow: {exc}", tone="error")
            return
        self._show_workflow_detail()
        self.say("Saved on this device \u2014 applies from the next turn.")
        self.changed.emit()

    def _on_routes_changed(self) -> None:
        self.changed.emit()


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
    navigate = pyqtSignal(str, str)

    def __init__(self, controller: Any, route_editor: Optional[RouteOverrideEditor], parent: Optional[QWidget] = None) -> None:
        super().__init__(controller, parent)
        self._route_editor = route_editor

        routes = self.add_card(Card("Engines", "Which engines speak and listen. Change them under Models."))
        self.tts_summary = QLabel("")
        self.tts_summary.setObjectName("rowValue")
        self.tts_summary.setWordWrap(True)
        tts_button = button("Change…", "secondary", on_click=lambda: self.navigate.emit("models", "output.voice"))
        routes.add_row("Text → speech", self.tts_summary, trailing=[tts_button])
        self.stt_summary = QLabel("")
        self.stt_summary.setObjectName("rowValue")
        self.stt_summary.setWordWrap(True)
        stt_button = button("Change…", "secondary", on_click=lambda: self.navigate.emit("models", "input.voice"))
        routes.add_row("Speech → text", self.stt_summary, trailing=[stt_button])
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
        self.auto_speak = QCheckBox("Speak replies automatically")
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
        self.voice_auto_send = QCheckBox("Send what you say automatically")
        conversation.add_row("Sending", self.voice_auto_send, help_text="Off: your words land in the message box and Return sends them.")
        self.voice_spoken_replies = QCheckBox("Ask for short, spoken-style replies")
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

        self.save_button_voice = button("Save", "primary", on_click=self._save)
        self.add_actions(self.save_button_voice)

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
        editor = self._route_editor
        for key, label in (("output.voice", self.tts_summary), ("input.voice", self.stt_summary)):
            summary = editor.route_summary(key) if editor is not None else {"value": "", "source": ""}
            value = str(summary.get("value") or "")
            source = str(summary.get("source") or "")
            if not value:
                label.setText("Gateway default (the engine chooses at call time)")
            else:
                suffix = " — this app" if source == "app" else " — gateway default"
                label.setText(f"{value}{suffix}")
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
            self.say("Could not save the voice settings.", tone="error")


# ============================================================== Workspace


_MODE_LABELS = {
    "": "Gateway decides (send nothing)",
    "workspace_only": "Workspace only — tools stay under the workspace root",
    "workspace_or_allowed": "Workspace + allowed folders",
    "all_except_ignored": "Any absolute path except ignored ones",
}


class WorkspacePage(SettingsPage):
    title = "Workspace"
    subtitle = "Which folders the assistant's file tools may use. Paths are resolved on the gateway's host and limited by its policy."
    icon = "folder"

    def __init__(self, controller: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(controller, parent)

        policy = self.add_card(Card("Gateway policy", "Read from the gateway. This app can only narrow what the policy allows."))
        self.policy_note = Note("Reading the gateway policy…", "info")
        policy.add_widget(self.policy_note)
        self.policy_lines = QLabel("")
        self.policy_lines.setObjectName("rowValue")
        self.policy_lines.setWordWrap(True)
        self.policy_lines.setTextInteractionFlags(Qt.TextSelectableByMouse)
        policy.add_widget(self.policy_lines)

        self._effective_policy: Dict[str, Any] = {}
        self._gateway_local = bool(safe_call(controller, "gateway_is_local", default=True))
        local = self.add_card(Card("This app", "Stored on this device and sent with each run."))
        self.workspace_root_edit = QLineEdit()
        self.workspace_root_edit.setPlaceholderText(
            "Optional — the gateway assigns one per chat"
            if self._gateway_local
            else "Optional — a path on the gateway's host"
        )
        choose_root = button("Choose…", "secondary", on_click=self._choose_root)
        clear_root = button("Clear", "ghost", on_click=lambda: self.workspace_root_edit.clear())
        # A folder picker browses THIS Mac; that only matches the gateway's
        # view of the filesystem when the gateway runs here.
        choose_root.setVisible(self._gateway_local)
        local.add_row(
            "Workspace root",
            self.workspace_root_edit,
            trailing=[choose_root, clear_root],
            help_text=(
                "Where the assistant reads and writes files. Without one, the gateway assigns a folder on the chat's first run and reuses it afterwards."
                if self._gateway_local
                else "Where the assistant reads and writes files, as a path on the gateway's host (this app cannot browse it). Without one, the gateway assigns a folder per chat."
            ),
        )
        self.workspace_mode_combo = QComboBox()
        local.add_row("Access mode", self.workspace_mode_combo, help_text="Only the modes the gateway offers are listed.")
        self.workspace_allowed_list = QListWidget()
        self.workspace_allowed_list.setMinimumHeight(88)
        self.workspace_allowed_list.setMaximumHeight(140)
        add_folder = button("Add folder…", "secondary", on_click=self._add_folder)
        add_folder.setVisible(self._gateway_local)
        remove = button("Remove", "ghost", on_click=self._remove_selected)
        buttons = QWidget()
        col = QVBoxLayout(buttons)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(6)
        col.addWidget(add_folder)
        col.addWidget(remove)
        col.addStretch(1)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self.workspace_allowed_list, 1)
        row.addWidget(buttons, 0)
        host = QWidget()
        host.setLayout(row)
        local.add_row(
            "Allowed folders",
            host,
            help_text="Extra folders the tools may reach in “Workspace + allowed folders” mode. Absolute paths (or ~) only; a path outside the gateway's policy stops the run from starting.",
        )
        self.path_entry = QLineEdit()
        self.path_entry.setPlaceholderText("/absolute/path/on/the/gateway/host — press Return to add")
        self.path_entry.returnPressed.connect(self._add_typed_path)
        local.add_row("Add a path", self.path_entry)

        self.current_note = QLabel("")
        self.current_note.setObjectName("cardHelp")
        self.current_note.setWordWrap(True)
        local.add_widget(self.current_note)

        self.reset_button_workspace = button("Reset", "secondary", tooltip="Send nothing: the gateway decides", on_click=self._reset)
        self.save_button_workspace = button("Save", "primary", on_click=self._save)
        self.add_actions(self.reset_button_workspace, self.save_button_workspace)

    def refresh(self) -> None:
        prefs = _prefs(self.controller)
        self.workspace_root_edit.setText(str(safe_attr(prefs, "workspace_root", "") or ""))
        self.workspace_allowed_list.clear()
        for path in list(safe_attr(prefs, "workspace_allowed_paths", []) or []):
            self.workspace_allowed_list.addItem(QListWidgetItem(str(path)))
        self._refresh_policy()
        mode = str(safe_attr(prefs, "workspace_access_mode", "") or "")
        idx = self.workspace_mode_combo.findData(mode)
        self.workspace_mode_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._refresh_current_note()

    def _refresh_policy(self) -> None:
        payload = safe_call(self.controller, "workspace_policy", default=None) or {}
        policy = payload.get("policy") if isinstance(payload, dict) else {}
        me = payload.get("self") if isinstance(payload, dict) else {}
        error = str(payload.get("error") or "") if isinstance(payload, dict) else ""
        modes = safe_call(self.controller, "workspace_access_modes", default=None) or list(WORKSPACE_ACCESS_MODES)
        self.workspace_mode_combo.blockSignals(True)
        self.workspace_mode_combo.clear()
        self.workspace_mode_combo.addItem(_MODE_LABELS[""], "")
        for mode in modes:
            self.workspace_mode_combo.addItem(_MODE_LABELS.get(mode, mode), mode)
        self.workspace_mode_combo.blockSignals(False)
        if not policy and not me:
            self._effective_policy = {}
            self.policy_note.show_text(
                f"Could not read the gateway workspace policy: {error or 'not advertised by this gateway'}.",
                "warning",
            )
            self.policy_lines.setText("")
            return
        self.policy_note.hide()
        lines: List[str] = []
        effective = me.get("effective") if isinstance(me, dict) else {}
        self._effective_policy = dict(effective) if isinstance(effective, dict) else {}
        if isinstance(effective, dict) and effective:
            lines.append(f"Your posture: {effective.get('mode', 'unknown')}" + (" · customized for you" if me.get("customized") else " · gateway default"))
            lines.append(
                "Client scope overrides: " + ("allowed — any absolute path you grant is honored" if effective.get("client_workspace_scope_overrides") else "not allowed — grants outside the gateway's own folders are refused")
            )
            allowed = list(effective.get("workspace_allowed_paths") or [])
            blocked = list(effective.get("workspace_blocked_paths") or [])
            lines.append(f"Gateway-allowed paths for you: {', '.join(allowed) if allowed else 'none'}")
            if blocked:
                lines.append(f"Blocked paths: {', '.join(blocked)}")
        if isinstance(policy, dict) and policy:
            mounts = policy.get("mounts") or []
            lines.append(f"Access modes offered: {', '.join(modes)}")
            lines.append(f"Gateway mounts: {len(mounts)} · launch-folder trust: {'on' if policy.get('trust_client_launch_folder') else 'off'}")
        self.policy_lines.setText("\n".join(lines))

    def _refresh_current_note(self) -> None:
        status = safe_call(self.controller, "workspace_root_status", default=None) or {}
        root = str(status.get("root") or "")
        source = str(status.get("source") or "gateway")
        if source == "local":
            self.current_note.setText(f"Next run works in your folder: {root}")
        elif source == "session" and root:
            self.current_note.setText(f"Next run reuses this chat's gateway folder: {root}")
        else:
            self.current_note.setText("Next run: the gateway picks a fresh folder (remembered for the rest of the chat).")

    def _choose_root(self) -> None:
        start = self.workspace_root_edit.text().strip() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Choose the workspace root", start)
        if chosen:
            self.workspace_root_edit.setText(normalize_workspace_path(chosen))

    def _add_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Add an allowed folder", str(Path.home()))
        if chosen:
            self._add_path(chosen)

    def _add_typed_path(self) -> None:
        text = self.path_entry.text()
        if self._add_path(text):
            self.path_entry.clear()

    def _add_path(self, raw: str) -> bool:
        path = normalize_workspace_path(raw)
        if not path:
            self.say("Only absolute paths (or ~) can be sent — the gateway resolves them on its own host.", tone="error")
            return False
        existing = [self.workspace_allowed_list.item(i).text() for i in range(self.workspace_allowed_list.count())]
        if path in existing:
            self.say(f"{path} is already in the list.", tone="warning")
            return False
        self.workspace_allowed_list.addItem(QListWidgetItem(path))
        mode = str(self.workspace_mode_combo.currentData() or "")
        if mode in {"", "workspace_only"}:
            idx = self.workspace_mode_combo.findData("workspace_or_allowed")
            if idx >= 0:
                self.workspace_mode_combo.setCurrentIndex(idx)
                self.say(f"Added {path} and switched the access mode to “Workspace + allowed folders” so it takes effect.")
                return True
        self.say(f"Added {path}.")
        return True

    def _remove_selected(self) -> None:
        for item in self.workspace_allowed_list.selectedItems():
            self.workspace_allowed_list.takeItem(self.workspace_allowed_list.row(item))

    def _paths_outside_policy(self, roots: List[str], paths: List[str]) -> List[str]:
        """Entries the gateway's effective policy would refuse: only judged
        when the policy is known and forbids client scope overrides."""
        effective = self._effective_policy or {}
        if not effective or bool(effective.get("client_workspace_scope_overrides")):
            return []
        allowed = [str(p).rstrip("/") for p in (effective.get("workspace_allowed_paths") or []) if str(p).strip()]
        if not allowed:
            return []

        def _inside(candidate: str) -> bool:
            c = str(candidate).rstrip("/") or "/"
            return any(c == a or c.startswith(a + "/") or a == "/" for a in allowed)

        return [p for p in list(roots) + list(paths) if p and not _inside(p)]

    def _reset(self) -> None:
        self.workspace_root_edit.clear()
        self.workspace_mode_combo.setCurrentIndex(0)
        self.workspace_allowed_list.clear()
        self._save()

    def _save(self) -> None:
        root_raw = self.workspace_root_edit.text().strip()
        root = normalize_workspace_path(root_raw)
        if root_raw and not root:
            self.say("The workspace root must be an absolute path (or ~).", tone="error")
            return
        paths = [self.workspace_allowed_list.item(i).text() for i in range(self.workspace_allowed_list.count())]
        refused = self._paths_outside_policy([root] if root else [], paths)
        if refused:
            # The gateway would refuse the run before it starts: say which
            # entries, here, instead of a "Not sent" banner on every message.
            self.say(
                "Not saved — this gateway only accepts folders inside its own allowed paths, and these are outside: "
                + ", ".join(refused)
                + ". Remove them or ask the gateway operator to allow them.",
                tone="error",
            )
            return
        ok = _update_prefs(
            self.controller,
            workspace_root=root,
            workspace_access_mode=str(self.workspace_mode_combo.currentData() or ""),
            workspace_allowed_paths=paths,
        )
        if ok:
            self.say("Saved on this device — applies from your next message.")
            self.changed.emit()
            self._refresh_current_note()
        else:
            self.say("Could not save the workspace settings.", tone="error")


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


class ToolsPage(SettingsPage):
    title = "Tools & permissions"
    nav_title = "Tools"
    subtitle = "How this Mac handles tool requests before they reach the gateway. Off and Ask narrow what the gateway allows; Auto pre-approves a tool even where the gateway would ask. Risk tiers come from the gateway."
    icon = "shield"

    def __init__(self, controller: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(controller, parent)
        self._rows: Dict[str, Dict[str, Any]] = {}
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
        self._groups.setSpacing(12)
        self.body.addWidget(self._groups_host)

        self.reset_button = button("Use gateway defaults", "secondary", tooltip="Set every tool back to the gateway's own approval default", on_click=self._reset_defaults)
        self.save_button_tools = button("Save", "primary", on_click=self._save)
        self.add_actions(self.reset_button, self.save_button_tools)

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
        self.mode_note.show_text(self._tool_mode_text(str((inventory or {}).get("tool_mode") or "")), "info")
        note = str((inventory or {}).get("note") or "").strip()
        if note:
            self.say(note, tone="warning")
        while self._groups.count():
            item = self._groups.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._rows = {}
        by_toolset: Dict[str, List[dict]] = {}
        for item in items or []:
            if isinstance(item, dict) and str(item.get("name") or "").strip():
                by_toolset.setdefault(str(item.get("toolset") or "other"), []).append(item)
        self.save_button_tools.setEnabled(bool(by_toolset))
        self.reset_button.setEnabled(bool(by_toolset))
        if not by_toolset:
            empty = QLabel("No tools reported by the gateway — nothing to save until it answers.")
            empty.setObjectName("cardHelp")
            self._groups.addWidget(empty)
            return
        def _group_key(toolset: str) -> tuple:
            entries = by_toolset[toolset]
            all_disabled = all(entry.get("available") is False for entry in entries)
            return (all_disabled, toolset)

        for toolset in sorted(by_toolset, key=_group_key):
            self._groups.addWidget(self._build_group(toolset, by_toolset[toolset]))
        self._apply_filter()

    def _build_group(self, toolset: str, items: List[dict]) -> QWidget:
        card = Card(f"{toolset} ({len(items)})")
        glyph = QLabel()
        glyph.setPixmap(symbol_icon(_TOOLSET_ICONS.get(toolset.split(".")[0], "spark"), color=THEME.text_muted, size=14).pixmap(14, 14))
        card.add_header_widget(glyph)
        all_auto = button("All auto", "ghost", tooltip="Pre-approve the observe/act tools in this group on this Mac (outreach and destructive tools stay on Ask)", on_click=lambda: self._set_group(toolset, "approve"))
        all_ask = button("All ask", "ghost", tooltip="Ask before running any tool in this group", on_click=lambda: self._set_group(toolset, "ask"))
        card.add_header_widget(all_auto)
        card.add_header_widget(all_ask)
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
            control = SegmentedControl([("disabled", "Off"), ("approve", "Auto"), ("ask", "Ask")])
            default = str(item.get("policy_default") or "ask")
            control.set_tooltips(
                {
                    "disabled": "Never offered to the model",
                    "approve": "Pre-approved on this Mac" + (" · gateway default" if default == "approve" else ""),
                    "ask": "Prompt every time" + (" · gateway default" if default == "ask" else ""),
                }
            )
            control.set_value(str(item.get("selected_mode") or default))
            control.setEnabled(available)
            control.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            head_row.addWidget(control, 0)
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
                "toolset": toolset,
                "available": available,
                "rank": int(risk.get("rank") or 0),
                "search": f"{name}\n{full_description}\n{toolset}".lower(),
            }
        return card

    # "All auto" never reaches outreach (3) / destroy (4): those are set to
    # Auto one tool at a time, by name.
    ALL_AUTO_MAX_RANK = 2

    def _set_group(self, toolset: str, mode: str) -> None:
        skipped: List[str] = []
        hidden = 0
        for name, info in self._rows.items():
            if info["toolset"] != toolset or not info["available"]:
                continue
            # Only what the user can actually see: with a filter applied this
            # used to pre-approve mutating tools that were not on screen.
            row = info.get("row")
            if row is not None and not row.isVisibleTo(self):
                hidden += 1
                continue
            if mode == "approve" and int(info.get("rank") or 0) > self.ALL_AUTO_MAX_RANK:
                skipped.append(name)
                continue
            info["control"].set_value(mode)
        if skipped:
            self.say(
                "Left on Ask (outreach or destructive): " + ", ".join(sorted(skipped)) + ". Set them to Auto individually if you mean it.",
                tone="warning",
            )
        elif hidden:
            self.say(
                f"Applied to the {len(self._rows) - hidden} tool(s) shown; "
                f"{hidden} hidden by the filter were left alone.",
                tone="info",
            )

    def _apply_filter(self) -> None:
        query = str(self.search_edit.text() or "").strip().lower()
        for info in self._rows.values():
            info["row"].setVisible(not query or query in info["search"])

    def _reset_defaults(self) -> None:
        for info in self._rows.values():
            info["control"].set_value(info["default_mode"])
        self.say("Restored the gateway's approval defaults in this window; press Save to keep them.", tone="info")

    def _save(self) -> None:
        if not self._rows:
            self.say("Nothing to save: the gateway reported no tools.", tone="warning")
            return
        # Only rows that differ from the gateway's default are stored, so a
        # tool left on its default keeps following the gateway if that changes.
        # Start from what is already saved: the gateway's inventory varies with
        # what is connected, and rebuilding the map from this refresh alone
        # silently dropped saved modes for tools it did not list this time.
        statuses = dict(safe_attr(_prefs(self.controller), "tool_preferences", {}) or {})
        for name, info in self._rows.items():
            chosen = str(info["control"].value() or "ask")
            if chosen != str(info.get("default_mode") or "ask"):
                statuses[name] = chosen
            else:
                statuses.pop(name, None)
        saver = getattr(self.controller, "save_tool_preferences", None)
        if callable(saver):
            try:
                saver(statuses)
            except Exception as exc:
                self.say(f"Could not save: {exc}", tone="error")
                return
        self.say("Saved tool permissions on this device.")
        self.changed.emit()


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
        self.hotkey_enabled = QCheckBox("Summon the assistant from anywhere")
        summon.add_row("Summon", self.hotkey_enabled)
        self.hotkey_edit = QLineEdit()
        self.hotkey_edit.setPlaceholderText("cmd+shift+space")
        self.hotkey_edit.setMinimumWidth(160)
        summon.add_row(
            "Key combination",
            self.hotkey_edit,
            stretch_control=False,
            help_text="Works anywhere once macOS grants Accessibility access; otherwise use the menu bar icon.",
        )

        window = self.add_card(Card("Window size", "Limited by the screen. The chat takes whatever height remains after the header and composer."))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(*WINDOW_WIDTH_RANGE)
        self.width_spin.setSuffix(" px")
        window.add_row("Width", self.width_spin, stretch_control=False, help_text="Up to 62% of the screen the window is on.")
        self.height_spin = QSpinBox()
        # Must reach the app's own default (286): a floor above it meant
        # pressing Save on this page silently grew the window.
        self.height_spin.setRange(240, 880)
        self.height_spin.setSuffix(" px")
        window.add_row("Expanded height", self.height_spin, stretch_control=False, help_text="Height of the window once the chat opens fully.")
        self.bottom_offset_spin = QSpinBox()
        self.bottom_offset_spin.setRange(*SCREEN_EDGE_GAP_RANGE)
        self.bottom_offset_spin.setSuffix(" px")
        window.add_row("Screen edge gap", self.bottom_offset_spin, stretch_control=False, help_text="Space kept between the window and the edge of the screen (at most a quarter of the screen).")

        shortcuts = self.add_card(Card("Keyboard shortcuts"))
        shortcuts.add_widget(self._shortcut_grid(_SHORTCUTS))
        approval_title = QLabel("In the approval sheet")
        approval_title.setObjectName("rowLabel")
        approval_title.setContentsMargins(0, 6, 0, 0)
        shortcuts.add_widget(approval_title)
        shortcuts.add_widget(self._shortcut_grid(_APPROVAL_SHORTCUTS))

        self.save_button_window = button("Save", "primary", on_click=self._save_preferences)
        self.add_actions(self.save_button_window)

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
        self.say("Saved on this device." if ok else "Could not save the text settings.",
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
        self.width_spin.setValue(int(safe_attr(prefs, "window_width", DEFAULT_WINDOW_WIDTH) or DEFAULT_WINDOW_WIDTH))
        self.height_spin.setValue(int(safe_attr(prefs, "window_height", DEFAULT_WINDOW_HEIGHT) or DEFAULT_WINDOW_HEIGHT))
        # 0 is a real choice (flush with the screen edge): never `or` it away.
        gap = safe_attr(prefs, "bottom_offset", DEFAULT_SCREEN_EDGE_GAP)
        self.bottom_offset_spin.setValue(DEFAULT_SCREEN_EDGE_GAP if gap is None else int(gap))

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
            self.say("Could not save the window settings.", tone="error")
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
    at = f" @{version}" if version else ""
    source = str(getattr(workflow, "source", "") or "")
    if flow_id == WORKFLOW_GATEWAY_DEFAULT:
        return f"Gateway default \u2192 {label}{at} ({bundle_id})"
    if source == "built_in":
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
    at = f" @{version}" if version else ""
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

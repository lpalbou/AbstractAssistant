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
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...config import DEFAULT_GATEWAY_URL
from ...core.tool_risk import describe_tool_risk
from ...icons import symbol_icon
from ...preferences import (
    REASONING_EFFORT_LEVELS,
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
    subtitle = "The gateway's defaults apply unless this app overrides them. Overrides stay on this device and ride each request; the gateway's shared defaults are never changed."
    icon = "cpu"

    def __init__(self, controller: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(controller, parent)

        routes = self.add_card(
            Card(
                "Models",
                "Each entry shows the gateway's default and this app's override, if any. Chat and voice overrides are sent with each request; image, video, music and sound overrides are handed to the assistant's workflow.",
            )
        )
        self.route_editor = RouteOverrideEditor(controller, routes)
        self.route_editor.changed.connect(self._on_routes_changed)
        routes.add_widget(self.route_editor)

        reasoning = self.add_card(
            Card(
                "Reasoning effort",
                "How hard the chat model thinks before answering. “Gateway default” sends nothing and lets the gateway decide.",
            )
        )
        self.reasoning_control = SegmentedControl([("", "Gateway default")])
        self.reasoning_control.changed.connect(self._on_reasoning_changed)
        reasoning.add_widget(self.reasoning_control)
        self.reasoning_note = QLabel("")
        self.reasoning_note.setObjectName("cardHelp")
        self.reasoning_note.setWordWrap(True)
        reasoning.add_widget(self.reasoning_note)

    def refresh(self) -> None:
        self.route_editor.refresh()
        self._refresh_reasoning()

    def _on_routes_changed(self) -> None:
        self.changed.emit()
        self._refresh_reasoning()

    def _refresh_reasoning(self) -> None:
        levels = safe_call(self.controller, "reasoning_levels", default=None) or list(REASONING_EFFORT_LEVELS)
        options = [("", "Gateway default")] + [(lvl, _REASONING_LABELS.get(lvl, lvl)) for lvl in levels]
        self.reasoning_control.set_options(options)
        prefs = _prefs(self.controller)
        current = str(safe_attr(prefs, "reasoning_effort", "") or "")
        self.reasoning_control.set_value(current if current in dict(options) else "")
        supported = self._model_reasoning_levels()
        if supported is not None:
            # Levels the chat model's capability card does not list are greyed
            # out (a saved one stays selected so the caption can say it maps).
            for lvl in levels:
                ok = lvl in supported
                self.reasoning_control.set_option_enabled(
                    lvl,
                    ok or lvl == current,
                    "" if ok else f"Not reported by this model; AbstractCore maps it to the nearest level it can honor.",
                )
        self.reasoning_note.setText(self._reasoning_caption(current))

    def _model_reasoning_levels(self) -> Optional[set]:
        """The reasoning levels the effective chat model reports, or None when
        no capability card lists any (then every level stays selectable)."""
        route = safe_call(self.controller, "effective_chat_route", default=None) or {}
        model = str(route.get("model") or "").strip()
        card = safe_call(self.controller, "model_capabilities", model, default=None) if model else None
        if not isinstance(card, dict) or card.get("thinking_support") is not True:
            return None
        levels = {str(v).strip().lower() for v in (card.get("reasoning_levels") or []) if str(v).strip()}
        return levels or None

    def _reasoning_caption(self, current: str) -> str:
        route = safe_call(self.controller, "effective_chat_route", default=None) or {}
        provider = str(route.get("provider") or "").strip()
        model = str(route.get("model") or "").strip()
        source = "this app's override" if route.get("source") == "override" else "the gateway default"
        if not model:
            target = "the gateway's default chat model"
        else:
            target = f"{provider + ' / ' if provider else ''}{model} ({source})"
        card = safe_call(self.controller, "model_capabilities", model, default=None) if model else None
        lines = [f"Applies to {target}."]
        if isinstance(card, dict) and card:
            supports = card.get("thinking_support")
            levels = [str(v) for v in (card.get("reasoning_levels") or []) if str(v)]
            if supports is True and levels:
                lines.append(f"This model reports reasoning levels {', '.join(levels)}; other levels map to the nearest one AbstractCore can honor.")
            elif supports is True:
                lines.append("This model reports reasoning support; the level is passed as a best-effort hint.")
            elif supports is False:
                lines.append("This model does not report reasoning support — the setting is sent, but the model may ignore it.")
        elif model:
            lines.append("No capability card for this model; AbstractCore maps an unsupported level to the nearest one it can honor.")
        if current:
            lines.append(f"Currently sending: {_REASONING_LABELS.get(current, current)}.")
        return " ".join(lines)

    def _on_reasoning_changed(self, value: str) -> None:
        if _update_prefs(self.controller, reasoning_effort=value):
            self.say("Saved on this device." if value else "Following the gateway default.")
            self.changed.emit()
        else:
            self.say("Could not save the reasoning effort.", tone="error")
        prefs = _prefs(self.controller)
        self.reasoning_note.setText(self._reasoning_caption(str(safe_attr(prefs, "reasoning_effort", value) or "")))


# ================================================================== Voice


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
        self.device_summary = QLabel("")
        self.device_summary.setObjectName("rowValue")
        self.device_summary.setWordWrap(True)
        sound_button = button("Sound settings…", "secondary", on_click=self._open_sound_settings)
        routes.add_row(
            "Output device",
            self.device_summary,
            trailing=[sound_button],
            help_text="Playback follows the Mac's default output; a headset or a muted output makes a working voice inaudible.",
        )

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
        self.voice_mode_wait = QRadioButton("Pause the mic while the assistant speaks (speakers)")
        self.voice_mode_full = QRadioButton("Keep the mic open; say “stop” to interrupt (headphones)")
        modes = QVBoxLayout()
        modes.setContentsMargins(0, 0, 0, 0)
        modes.setSpacing(6)
        modes.addWidget(self.voice_mode_wait)
        modes.addWidget(self.voice_mode_full)
        host = QWidget()
        host.setLayout(modes)
        conversation.add_row(
            "Barge-in",
            host,
            help_text="With speakers, the open-mic option may transcribe the assistant's own voice.",
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
        self.voice_mode_full.setChecked(mode == "full")
        self.voice_mode_wait.setChecked(mode != "full")
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

    def _open_sound_settings(self) -> None:
        if platform.system().lower() == "darwin":
            QDesktopServices.openUrl(QUrl("x-apple.systempreferences:com.apple.Sound-Settings.extension"))

    def _save(self) -> None:
        ok = _update_prefs(
            self.controller,
            auto_speak=bool(self.auto_speak.isChecked()),
            voice_quality=str(self.voice_quality_combo.currentData() or "standard"),
            voice_auto_send=bool(self.voice_auto_send.isChecked()),
            voice_spoken_replies=bool(self.voice_spoken_replies.isChecked()),
            voice_mode="full" if self.voice_mode_full.isChecked() else "wait",
        )
        if ok:
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
        for name, info in self._rows.items():
            if info["toolset"] != toolset or not info["available"]:
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
        statuses = {
            name: str(info["control"].value() or "ask")
            for name, info in self._rows.items()
            if str(info["control"].value() or "ask") != str(info.get("default_mode") or "ask")
        }
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
    title = "Window & shortcuts"
    nav_title = "Window"
    subtitle = "Applies to this app on this Mac."
    icon = "keyboard"

    def __init__(self, controller: Any, apply_hotkey, parent: Optional[QWidget] = None) -> None:
        super().__init__(controller, parent)
        self._apply_hotkey = apply_hotkey

        summon = self.add_card(Card("Global shortcut"))
        self.hotkey_enabled = QCheckBox("Summon the assistant from anywhere")
        summon.add_row("Summon", self.hotkey_enabled)
        self.hotkey_edit = QLineEdit()
        self.hotkey_edit.setPlaceholderText("cmd+shift+space")
        self.hotkey_edit.setMinimumWidth(220)
        summon.add_row(
            "Key combination",
            self.hotkey_edit,
            stretch_control=False,
            help_text="Works anywhere once macOS grants Accessibility access; otherwise use the menu bar icon.",
        )

        window = self.add_card(Card("Window size", "Limited by the screen. The chat takes whatever height remains after the header and composer."))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(420, 960)
        self.width_spin.setSuffix(" px")
        window.add_row("Width", self.width_spin, stretch_control=False)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(320, 880)
        self.height_spin.setSuffix(" px")
        window.add_row("Expanded height", self.height_spin, stretch_control=False, help_text="Height of the window once the chat opens fully.")
        self.bottom_offset_spin = QSpinBox()
        self.bottom_offset_spin.setRange(0, 80)
        self.bottom_offset_spin.setSuffix(" px")
        window.add_row("Screen edge gap", self.bottom_offset_spin, stretch_control=False, help_text="Space kept between the window and the edge of the screen.")

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

    def refresh(self) -> None:
        prefs = _prefs(self.controller)
        self.hotkey_enabled.setChecked(bool(safe_attr(prefs, "hotkey_enabled", True)))
        self.hotkey_edit.setText(str(safe_attr(prefs, "hotkey_sequence", "cmd+shift+space") or "cmd+shift+space"))
        self.width_spin.setValue(int(safe_attr(prefs, "window_width", 500) or 500))
        self.height_spin.setValue(int(safe_attr(prefs, "window_height", 336) or 336))
        self.bottom_offset_spin.setValue(int(safe_attr(prefs, "bottom_offset", 18) or 18))

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


class AboutPage(SettingsPage):
    title = "About"
    subtitle = ""
    icon = "info"

    def __init__(self, controller: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(controller, parent)
        card = self.add_card(Card("AbstractAssistant"))
        self.version_label = QLabel("")
        self.version_label.setObjectName("rowValue")
        card.add_row("Version", self.version_label)
        self.stack_label = QLabel("")
        self.stack_label.setObjectName("rowValue")
        self.stack_label.setWordWrap(True)
        self.stack_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        card.add_row("Gateway packages", self.stack_label)
        self.workflow_label = QLabel("")
        self.workflow_label.setObjectName("rowValue")
        self.workflow_label.setWordWrap(True)
        card.add_row("Workflow", self.workflow_label)
        self.data_label = QLabel("")
        self.data_label.setObjectName("rowValue")
        self.data_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        reveal = button("Reveal in Finder", "secondary", on_click=self._reveal)
        card.add_row("Data folder", self.data_label, trailing=[reveal])
        links = self.add_card(Card("Links"))
        link_style = f'style="color: {THEME.accent}; text-decoration: none;"'
        self.links_label = QLabel(
            f'<a {link_style} href="https://github.com/lpalbou/abstractassistant">Source &amp; issues</a>'
            f' &nbsp;·&nbsp; <a {link_style} href="https://github.com/lpalbou/abstractgateway">AbstractGateway</a>'
            f' &nbsp;·&nbsp; <a {link_style} href="https://github.com/lpalbou/abstractassistant/blob/main/docs/README.md">Documentation</a>'
        )
        self.links_label.setOpenExternalLinks(True)
        links.add_widget(self.links_label)
        self.copy_button = button("Copy diagnostics", "secondary", tooltip="Versions, connection (no secrets), workflow and preferences", on_click=self._copy_diagnostics)
        self.add_actions(self.copy_button)

    def _diagnostics(self) -> Dict[str, Any]:
        try:
            from importlib import metadata

            version = metadata.version("abstractassistant")
        except Exception:
            version = "unknown"
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
        connection = safe_call(self.controller, "current_connection", default=None)
        prefs = _prefs(self.controller)
        return {
            "assistant": version,
            "stack": stack,
            "workflow": (
                f"{getattr(workflow, 'bundle_id', '')} {getattr(workflow, 'bundle_version', '')} ({getattr(workflow, 'registry_scope', '')})".strip()
                if workflow is not None
                else "not resolved"
            ),
            "gateway_url": str(getattr(connection, "base_url", "") or ""),
            "auth_mode": str(getattr(connection, "auth_mode", "") or ""),
            "data_dir": str(safe_attr(self.controller, "data_dir", "") or ""),
            "preferences": prefs.to_dict() if hasattr(prefs, "to_dict") else {},
        }

    def refresh(self) -> None:
        diag = self._diagnostics()
        self.version_label.setText(str(diag["assistant"]))
        stack = diag["stack"]
        self.stack_label.setText(" · ".join(f"{k} {v}" for k, v in stack.items()) if stack else "Not connected — versions unknown")
        self.workflow_label.setText(str(diag["workflow"]))
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

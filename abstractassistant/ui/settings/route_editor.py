"""Local model/voice route overrides — the editor extracted from the old Settings tabs.

Contract (unchanged): the gateway's capability defaults are READ here and never
written. A route is either "Use gateway default" (nothing stored, nothing
sent) or "Override for this app" (a provider AND model stored in
preferences.json and sent with each request). The editor shows both truths on
one state line and never pre-selects a catalog entry as if it were configured.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFontMetrics, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QSizePolicy,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ...gateway_service import ROUTE_SPECS, CapabilityRouteRow
from ...preferences import REASONING_EFFORT_LEVELS
from ...theme import THEME
from .common import LABEL_COLUMN_MIN, safe_attr, safe_call


def _prefs(controller: Any) -> Any:
    return safe_attr(controller, "preferences", None)


def _update_prefs(controller: Any, **updates: Any) -> bool:
    return safe_call(controller, "update_preferences", default=None, **updates) is not None

_REASONING_LABELS = {
    "none": "None",
    "minimal": "Minimal",
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "xhigh": "Extra high",
}


def json_dumps(value: Dict[str, Any]) -> str:
    if not value:
        return ""
    return json.dumps(value, ensure_ascii=False, indent=2)


# The routes the assistant actually drives AND can locally override, with
# app-facing labels. Media routes ride per-run input pins on the managed
# workflow; voice rides the TTS/STT calls; chat rides the run input. 3D is
# absent because the runtime has no scene3d workflow node yet.
OVERRIDE_ROUTE_LABELS = {
    "output.text": "Chat model",
    "output.voice": "Voice output (TTS)",
    "input.voice": "Voice input (STT)",
    "output.image.text_to_image": "Image generation",
    "output.image.image_to_image": "Image edit",
    "output.image.image_upscale": "Image upscale",
    "output.video.text_to_video": "Video generation",
    "output.video.image_to_video": "Image → video",
    "output.music": "Music generation",
    "output.sound": "Sound effects",
}

# Friendlier names for the gateway routes a default can be derived from.
_DERIVED_LABELS = {"input.text": "Text input", **OVERRIDE_ROUTE_LABELS}

# Help lines written for the assistant's user (the gateway's own route
# descriptions are engine-centric, e.g. "Read-only view derived from input.text").
_ROUTE_HELP = {
    "output.text": "The model that answers chat turns and drives tools. The gateway derives its default from the text-input route; override it here for this app only.",
    "output.voice": "The engine and voice that read replies aloud.",
    "input.voice": "The engine that transcribes your microphone.",
}

# Which advanced fields actually reach a request, per route. Everything else
# is hidden rather than saved-and-ignored.
_BASE_URL_ROUTES = {"output.text"}


class RouteOverrideEditor(QWidget):
    """Route list + override form. ``changed`` fires after a save or reset."""

    changed = pyqtSignal()

    _PLACEHOLDER_PROVIDER = "Choose a provider…"
    _PLACEHOLDER_MODEL = "Choose a model…"
    _loading_route = False

    def __init__(self, controller: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._route_rows: List[CapabilityRouteRow] = []
        self._gateway_default_by_key: Dict[str, CapabilityRouteRow] = {}

        panel = QHBoxLayout(self)
        panel.setContentsMargins(0, 0, 0, 0)
        panel.setSpacing(12)

        self.route_list = QListWidget()
        self.route_list.setObjectName("routeList")
        self.route_list.setMinimumWidth(180)
        self.route_list.setMaximumWidth(220)
        self.route_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.route_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.route_list.setWordWrap(True)
        self.route_list.currentRowChanged.connect(self._load_selected_route)
        panel.addWidget(self.route_list, 0, Qt.AlignTop)

        right = QVBoxLayout()
        right.setSpacing(8)
        panel.addLayout(right, 1)

        self.route_label = QLabel("")
        self.route_label.setObjectName("routeLabel")
        right.addWidget(self.route_label)

        self.route_help = QLabel("")
        self.route_help.setWordWrap(True)
        self.route_help.setObjectName("routeHelp")
        right.addWidget(self.route_help)

        # What actually applies right now — always visible, always honest.
        self.route_state = QLabel("")
        self.route_state.setWordWrap(True)
        self.route_state.setObjectName("statusNote")
        right.addWidget(self.route_state)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(14)
        self.route_mode_default = QRadioButton("Use gateway default")
        self.route_mode_default.setToolTip(
            "Follow whatever the gateway resolves for this route. No local "
            "override is stored; the gateway's shared default is not changed."
        )
        self.route_mode_custom = QRadioButton("Override for this app")
        self.route_mode_custom.setToolTip(
            "Pick a provider and model used by THIS app only. Stored locally and "
            "sent with each request — the gateway's shared default stays untouched."
        )
        self.route_mode_group = QButtonGroup(self)
        self.route_mode_group.addButton(self.route_mode_default)
        self.route_mode_group.addButton(self.route_mode_custom)
        self.route_mode_custom.toggled.connect(self._on_route_mode_toggled)
        mode_row.addWidget(self.route_mode_default)
        mode_row.addWidget(self.route_mode_custom)
        mode_row.addStretch(1)
        right.addLayout(mode_row)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        form.setColumnStretch(1, 1)
        # The same label column as every other settings page, so this form does
        # not read as a third indent level.
        form.setColumnMinimumWidth(0, LABEL_COLUMN_MIN)
        right.addLayout(form)

        form.addWidget(QLabel("Provider"), 0, 0)
        self.provider_combo = QComboBox()
        self.provider_combo.currentIndexChanged.connect(self._on_provider_combo_changed)
        form.addWidget(self.provider_combo, 0, 1)

        form.addWidget(QLabel("Model"), 1, 0)
        self.model_combo = QComboBox()
        form.addWidget(self.model_combo, 1, 1)

        self.voice_label = QLabel("Voice")
        form.addWidget(self.voice_label, 2, 0)
        self.voice_combo = QComboBox()
        form.addWidget(self.voice_combo, 2, 1)

        # Reasoning belongs to the model that reasons. It is a property of the
        # chat model, like its provider and its name — not of the page, and not
        # of a voice, image, video, music or sound-effect model, none of which
        # has anything to think about.
        self.reasoning_label = QLabel("Reasoning")
        form.addWidget(self.reasoning_label, 3, 0)
        # A combo, not a 7-button ladder: the ladder could not shrink below
        # 508px, which pushed Apply off the screen at the dialog's own default
        # size — and it makes provider/model/reasoning read as one unit.
        self.reasoning_combo = QComboBox()
        self.reasoning_combo.currentIndexChanged.connect(self._on_reasoning_combo_changed)
        form.addWidget(self.reasoning_combo, 3, 1)
        self.reasoning_note = QLabel("")
        self.reasoning_note.setObjectName("routeHelp")
        # One line, elided: the full sentence is three lines of small print and
        # it dominated the form (and ran off the bottom of the page).
        self.reasoning_note.setWordWrap(False)
        self.reasoning_note.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        form.addWidget(self.reasoning_note, 4, 1)

        # Hidden: the per-run override pins carry provider/model only, so an
        # upscale resolution would be saved and silently ignored.
        self.resolution_label = QLabel("Upscale resolution")
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItem("2x", "2x")
        self.resolution_combo.addItem("4x", "4x")
        self.resolution_combo.addItem("auto", "auto")
        self.resolution_label.hide()
        self.resolution_combo.hide()

        self.show_advanced = QCheckBox("Advanced (provider base URL)")
        self.show_advanced.stateChanged.connect(self._apply_advanced_visibility)
        right.addWidget(self.show_advanced)

        advanced_form = QGridLayout()
        advanced_form.setHorizontalSpacing(10)
        advanced_form.setVerticalSpacing(8)
        advanced_form.setColumnStretch(1, 1)
        right.addLayout(advanced_form)

        self.base_url_label = QLabel("Provider base URL")
        advanced_form.addWidget(self.base_url_label, 0, 0)
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("Optional, e.g. http://localhost:1234/v1 — rides the chat run only")
        self.base_url_edit.editingFinished.connect(self._reload_catalogs_for_base_url)
        advanced_form.addWidget(self.base_url_edit, 0, 1)

        # Raw options JSON is kept as a data field (the voice choice is stored
        # in options.voice) but no longer offered as free text: nothing except
        # the voice key is delivered to a request.
        self.options_label = QLabel("Options JSON")
        self.options_edit = QPlainTextEdit()
        self.options_label.hide()
        self.options_edit.hide()

        self.route_feedback = QLabel("")
        self.route_feedback.setWordWrap(True)
        self.route_feedback.setObjectName("feedbackNote")
        right.addWidget(self.route_feedback)

        self.refresh_button = QPushButton("Reload")
        self.refresh_button.setObjectName("secondaryButton")
        self.refresh_button.setAutoDefault(False)
        self.refresh_button.setToolTip("Reload the gateway defaults for these routes")
        self.refresh_button.clicked.connect(self.refresh)
        self.reset_route_button = QPushButton("Reset to gateway")
        self.reset_route_button.setObjectName("secondaryButton")
        self.reset_route_button.setAutoDefault(False)
        self.reset_route_button.setToolTip(
            "Drop this app's local override for the selected route and follow the "
            "gateway default again."
        )
        self.reset_route_button.clicked.connect(self._reset_route_to_gateway)
        self.save_button = QPushButton("Apply")
        self.save_button.setObjectName("primaryButton")
        self.save_button.setAutoDefault(False)
        self.save_button.setToolTip("Apply the selected mode for this app")
        self.save_button.clicked.connect(self._save_route)

    def action_buttons(self) -> List[QPushButton]:
        """The buttons this editor owns, for the page footer to host."""
        return [self.refresh_button, self.reset_route_button, self.save_button]

    # ------------------------------------------------------------------ data

    def refresh(self) -> None:
        selected_key = ""
        row = self._active_row()
        if row is not None:
            selected_key = row.key
        try:
            self._route_rows = self._build_override_rows()
        except Exception as exc:
            self._route_rows = []
            self.route_feedback.setText(str(exc))
        self.route_list.clear()
        for row in self._route_rows:
            item = QListWidgetItem(row.label)
            item.setIcon(self._route_dot_icon(configured=bool(row.configured)))
            item.setToolTip(self._route_state_text(row))
            self.route_list.addItem(item)
        self._sync_reasoning_options()
        self._fit_list_height()
        if self._route_rows:
            selected_index = 0
            if selected_key:
                for idx, item in enumerate(self._route_rows):
                    if item.key == selected_key:
                        selected_index = idx
                        break
            self.route_list.setCurrentRow(selected_index)
            if selected_index == 0:
                # currentRowChanged does not fire when the row is already 0.
                self._load_selected_route(0)
        else:
            self.route_label.setText("No gateway routes available")
            self.route_help.setText("Connect to a gateway account that can read capability defaults.")
            self.route_state.setText("")
            self._set_route_editor_enabled(False)

    def _fit_list_height(self) -> None:
        """Size the list to the rows it actually has.

        Every row is measured, not row 0 multiplied by the count: row 0 is the
        shortest label ("Chat model") and word wrap is on, so one wrapped name
        made the list a line too short per wrap — and with the scrollbar off,
        the routes at the bottom became unreachable. The height is fixed, not a
        minimum, so the list stops claiming the card's whole height.
        """
        count = self.route_list.count()
        if count <= 0:
            self.route_list.setFixedHeight(0)
            return
        # Width first, from the longest route name: at a fixed 180px "Voice
        # output (TTS)" wrapped onto two lines, which then made the measured
        # height wrong as well.
        content = int(self.route_list.sizeHintForColumn(0) or 0)
        frame = 2 * self.route_list.frameWidth()
        self.route_list.setFixedWidth(max(180, min(268, content + frame + 22)))
        total = sum(max(24, int(self.route_list.sizeHintForRow(i) or 0)) for i in range(count))
        self.route_list.setFixedHeight(total + frame + 10)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().resizeEvent(event)
        # The list narrows with the dialog, so a name that fits at one width
        # wraps at another: re-measure instead of trusting the first pass.
        self._fit_list_height()

    def rows(self) -> List[CapabilityRouteRow]:
        return list(self._route_rows)

    def route_summary(self, key: str) -> Dict[str, str]:
        """{value, source} for a route: the local override when set, else the
        gateway default; source in {"app", "gateway", ""}."""
        override = next((item for item in self._route_rows if item.key == key), None)
        if override is not None and override.configured:
            return {"value": self._route_value_summary(override), "source": "app"}
        gw = self._gateway_default_row(key)
        value = self._route_value_summary(gw) if gw is not None else ""
        return {"value": value, "source": "gateway" if value else ""}

    def _build_override_rows(self) -> List[CapabilityRouteRow]:
        gateway_map: Dict[str, CapabilityRouteRow] = {}
        try:
            gateway_map = self._controller.route_map()
        except Exception as exc:
            self.route_feedback.setText(str(exc))
        self._gateway_default_by_key = dict(gateway_map or {})
        rows: List[CapabilityRouteRow] = []
        for key, label in OVERRIDE_ROUTE_LABELS.items():
            gw = gateway_map.get(key) if gateway_map else None
            spec = ROUTE_SPECS.get(key)
            override = safe_call(self._controller, "route_override", key, default=None) or {}
            options = override.get("options") if isinstance(override.get("options"), dict) else {}
            rows.append(
                CapabilityRouteRow(
                    key=key,
                    label=label,
                    kind=str(getattr(gw, "kind", "") or ""),
                    modality=str(getattr(gw, "modality", "") or ""),
                    task=str(getattr(gw, "task", "") or (spec.task if spec else "")),
                    provider=str(override.get("provider") or ""),
                    model=str(override.get("model") or ""),
                    base_url=str(override.get("base_url") or ""),
                    options=dict(options or {}),
                    configured=bool(override),
                    derived_from=str(getattr(gw, "derived_from", "") or getattr(gw, "covered_by", "") or ""),
                    description=(spec.description if spec else str(getattr(gw, "description", "") or "")),
                )
            )
        return rows

    def _gateway_default_row(self, key: str) -> Optional[CapabilityRouteRow]:
        return dict(self._gateway_default_by_key or {}).get(str(key or "").strip())

    def _active_row(self) -> Optional[CapabilityRouteRow]:
        idx = int(self.route_list.currentRow())
        if idx < 0 or idx >= len(self._route_rows):
            return None
        return self._route_rows[idx]

    def _load_selected_route(self, _index: int) -> None:
        row = self._active_row()
        if row is None:
            self._set_route_editor_enabled(False)
            return
        self._loading_route = True
        try:
            self.route_feedback.clear()
            self.route_label.setText(row.label)
            self.route_help.setText(_ROUTE_HELP.get(row.key) or row.description or row.package_hint or "")
            self.route_state.setText(self._route_state_text(row))
            self.base_url_edit.setText(row.base_url)
            self.options_edit.setPlainText(json_dumps(row.options) if row.options else "")
            self.show_advanced.setChecked(bool(row.base_url))

            is_custom = bool(row.configured)
            self.route_mode_custom.setChecked(is_custom)
            self.route_mode_default.setChecked(not is_custom)

            self._populate_providers(row=row)
            self._refresh_models_for_provider(row=row)
            self._apply_route_specific_state(row)
            self._apply_advanced_visibility()
            self._apply_route_mode()
        finally:
            self._loading_route = False

    def _set_route_editor_enabled(self, enabled: bool) -> None:
        self.route_mode_default.setEnabled(enabled)
        self.route_mode_custom.setEnabled(enabled)
        self._set_editor_fields_enabled(enabled)
        self.save_button.setEnabled(enabled)

    def _set_editor_fields_enabled(self, enabled: bool) -> None:
        self.provider_combo.setEnabled(enabled)
        self.model_combo.setEnabled(enabled)
        self.base_url_edit.setEnabled(enabled)
        self.options_edit.setEnabled(enabled)
        self.voice_combo.setEnabled(enabled)
        self.resolution_combo.setEnabled(enabled)

    def _on_route_mode_toggled(self) -> None:
        if bool(getattr(self, "_loading_route", False)):
            return
        self._apply_route_mode()

    def _apply_route_mode(self) -> None:
        custom = self.route_mode_custom.isChecked()
        self._set_editor_fields_enabled(custom)
        self.save_button.setToolTip(
            "Save this provider/model as a local override for this app"
            if custom
            else "Follow the gateway default (drops any local override on Apply)"
        )
        active = self._active_row()
        self.reset_route_button.setEnabled(bool(active is not None and active.configured))

    def _route_dot_icon(self, *, configured: bool) -> QIcon:
        size = 10
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.setDevicePixelRatio(2.0)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(THEME.accent) if configured else QColor(255, 255, 255, 56))
        painter.drawEllipse(2, 2, size - 4, size - 4)
        painter.end()
        return QIcon(pixmap)

    def focus_route(self, route_key: str) -> None:
        target = str(route_key or "").strip()
        for idx, row in enumerate(self._route_rows):
            if row.key == target:
                self.route_list.setCurrentRow(idx)
                break

    # alias kept for callers of the old dialog method
    _focus_route = focus_route

    def _route_value_summary(self, row: Optional[CapabilityRouteRow]) -> str:
        if row is None:
            return ""
        provider = str(row.provider or "").strip()
        model = str(row.model or "").strip()
        if not provider and not model:
            return ""
        value = " / ".join(part for part in (provider, model) if part)
        voice = str((row.options or {}).get("voice") or (row.options or {}).get("profile") or "").strip()
        if voice:
            value += f" · voice {voice}"
        return value

    def _route_state_text(self, row: CapabilityRouteRow) -> str:
        """Two honest lines: the gateway's own default, then what THIS app uses."""
        gw = self._gateway_default_row(row.key)
        gw_value = self._route_value_summary(gw) if gw is not None else ""
        derived = str(getattr(gw, "derived_from", "") or getattr(gw, "covered_by", "") or "").strip() if gw is not None else ""
        if gw_value:
            origin = f" (derived from {_DERIVED_LABELS.get(derived, derived)})" if derived and derived != row.key else ""
            gw_line = f"Gateway default{origin}: {gw_value}."
        else:
            gw_line = (
                "Gateway default: not configured — the gateway's engine picks "
                "its own default at call time."
            )
        override_value = self._route_value_summary(row)
        if override_value:
            app_line = f"This app: {override_value} (local override)."
        else:
            app_line = "This app: using the gateway default."
        return f"{gw_line}\n{app_line}"

    # ---------------------------------------------------------------- catalogs

    def _populate_providers(self, *, row: CapabilityRouteRow) -> None:
        self.provider_combo.blockSignals(True)
        try:
            self.provider_combo.clear()
            self.provider_combo.addItem(self._PLACEHOLDER_PROVIDER, "")
            try:
                choices = self._controller.provider_choices(route_key=row.key, base_url=self.base_url_edit.text().strip())
            except Exception as exc:
                self.route_feedback.setText(str(exc))
                choices = []
            for choice in choices or []:
                self.provider_combo.addItem(choice.label, choice.id)
            saved = str(row.provider or "").strip()
            if saved:
                if self.provider_combo.findData(saved) < 0:
                    self.provider_combo.addItem(f"{saved} (saved)", saved)
                self._set_combo_value(self.provider_combo, saved)
            else:
                self.provider_combo.setCurrentIndex(0)
        finally:
            self.provider_combo.blockSignals(False)

    def _on_provider_combo_changed(self) -> None:
        if bool(getattr(self, "_loading_route", False)):
            return
        self._refresh_models_for_provider()

    def _refresh_models_for_provider(self, *, row: Optional[CapabilityRouteRow] = None) -> None:
        active = row if row is not None else self._active_row()
        if active is None:
            return
        provider = str(self.provider_combo.currentData() or "").strip()
        self.model_combo.blockSignals(True)
        try:
            self.model_combo.clear()
            self.model_combo.addItem(self._PLACEHOLDER_MODEL, "")
            choices = []
            if provider:
                try:
                    choices = self._controller.model_choices(
                        route_key=active.key, provider=provider, base_url=self.base_url_edit.text().strip()
                    )
                except Exception as exc:
                    self.route_feedback.setText(str(exc))
                    choices = []
            for choice in choices or []:
                self.model_combo.addItem(choice.label, choice.id)
            saved_model = str(active.model or "").strip()
            saved_provider = str(active.provider or "").strip()
            if saved_model and provider and provider == saved_provider:
                if self.model_combo.findData(saved_model) < 0:
                    self.model_combo.addItem(f"{saved_model} (saved)", saved_model)
                self._set_combo_value(self.model_combo, saved_model)
            else:
                self.model_combo.setCurrentIndex(0)
        finally:
            self.model_combo.blockSignals(False)
        self._refresh_voice_choices()

    def _reload_catalogs_for_base_url(self) -> None:
        row = self._active_row()
        if row is None:
            return
        current_provider = str(self.provider_combo.currentData() or self.provider_combo.currentText() or "").strip()
        current_model = str(self.model_combo.currentData() or self.model_combo.currentText() or "").strip()
        self._populate_providers(row=row)
        if current_provider:
            if self.provider_combo.findData(current_provider) < 0:
                self.provider_combo.addItem(current_provider, current_provider)
            self._set_combo_value(self.provider_combo, current_provider)
        self._refresh_models_for_provider()
        if current_model:
            if self.model_combo.findData(current_model) < 0:
                self.model_combo.addItem(current_model, current_model)
            self._set_combo_value(self.model_combo, current_model)

    def _refresh_voice_choices(self) -> None:
        row = self._active_row()
        self.voice_combo.blockSignals(True)
        try:
            self.voice_combo.clear()
            if row is None or row.key != "output.voice":
                return
            self.voice_combo.addItem("Engine default voice", "")
            provider = str(self.provider_combo.currentData() or "").strip()
            model = str(self.model_combo.currentData() or "").strip()
            choices = []
            if provider and model:
                try:
                    choices = self._controller.voice_choices(
                        provider=provider, model=model, base_url=self.base_url_edit.text().strip()
                    )
                except Exception as exc:
                    self.route_feedback.setText(str(exc))
                    choices = []
            for choice in choices or []:
                self.voice_combo.addItem(choice.label, choice.id)
            saved_voice = str((row.options or {}).get("voice") or (row.options or {}).get("profile") or "").strip()
            if saved_voice and provider and provider == str(row.provider or "").strip():
                if self.voice_combo.findData(saved_voice) < 0:
                    self.voice_combo.addItem(f"{saved_voice} (saved)", saved_voice)
                self._set_combo_value(self.voice_combo, saved_voice)
            else:
                self.voice_combo.setCurrentIndex(0)
        finally:
            self.voice_combo.blockSignals(False)

    def _sync_reasoning_options(self) -> None:
        """Build the level buttons once per refresh.

        Never while a route is being selected: rebuilding these widgets inside
        the list's `currentRowChanged` handler aborts the process.
        """
        levels = safe_call(self._controller, "reasoning_levels", default=None) or list(REASONING_EFFORT_LEVELS)
        self._reasoning_options = [("", "Gateway default")] + [
            (lvl, _REASONING_LABELS.get(lvl, lvl)) for lvl in levels
        ]
        self.reasoning_combo.blockSignals(True)
        self.reasoning_combo.clear()
        for value, label in self._reasoning_options:
            self.reasoning_combo.addItem(label, value)
        self.reasoning_combo.blockSignals(False)

    def _refresh_reasoning(self) -> None:
        options = list(getattr(self, "_reasoning_options", None) or [("", "Gateway default")])
        levels = [value for value, _label in options if value]
        prefs = _prefs(self._controller)
        current = str(safe_attr(prefs, "reasoning_effort", "") or "")
        if current not in dict(options):
            current = ""
        supported = self._model_reasoning_levels()
        model = self.reasoning_combo.model()
        self.reasoning_combo.blockSignals(True)
        for index in range(self.reasoning_combo.count()):
            value = str(self.reasoning_combo.itemData(index) or "")
            # A level this model does not report stays listed but unselectable
            # — except the one already saved, so the caption can explain that
            # AbstractCore maps it to the nearest level it can honor.
            usable = (
                not value
                or supported is None
                or value in supported
                or value == current
            )
            item = model.item(index) if hasattr(model, "item") else None
            if item is not None:
                item.setEnabled(usable)
            self.reasoning_combo.setItemData(
                index,
                ""
                if usable
                else "Not reported by this model; AbstractCore maps it to the nearest level it can honor.",
                Qt.ToolTipRole,
            )
        self.reasoning_combo.setCurrentIndex(max(0, self.reasoning_combo.findData(current)))
        self.reasoning_combo.blockSignals(False)
        self._set_reasoning_note(self._reasoning_caption(current))

    def _set_reasoning_note(self, text: str) -> None:
        """One elided line on screen, the whole sentence in the tooltip."""
        full = str(text or "")
        self.reasoning_note.setToolTip(full)
        metrics = QFontMetrics(self.reasoning_note.font())
        width = max(120, self.reasoning_note.width() or 320)
        self.reasoning_note.setText(metrics.elidedText(full, Qt.ElideRight, width))

    def _model_reasoning_levels(self) -> Optional[set]:
        """The reasoning levels the effective chat model reports, or None when
        no capability card lists any (then every level stays selectable)."""
        route = safe_call(self._controller, "effective_chat_route", default=None) or {}
        model = str(route.get("model") or "").strip()
        card = safe_call(self._controller, "model_capabilities", model, default=None) if model else None
        if not isinstance(card, dict) or card.get("thinking_support") is not True:
            return None
        levels = {str(v).strip().lower() for v in (card.get("reasoning_levels") or []) if str(v).strip()}
        return levels or None

    def _reasoning_caption(self, current: str) -> str:
        route = safe_call(self._controller, "effective_chat_route", default=None) or {}
        provider = str(route.get("provider") or "").strip()
        model = str(route.get("model") or "").strip()
        source = "this app's override" if route.get("source") == "override" else "the gateway default"
        if not model:
            target = "the gateway's default chat model"
        else:
            target = f"{provider + ' / ' if provider else ''}{model} ({source})"
        card = safe_call(self._controller, "model_capabilities", model, default=None) if model else None
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

    def _on_reasoning_combo_changed(self, _index: int) -> None:
        if bool(getattr(self, "_loading_route", False)):
            return
        self._on_reasoning_changed(str(self.reasoning_combo.currentData() or ""))

    def _on_reasoning_changed(self, value: str) -> None:
        if _update_prefs(self._controller, reasoning_effort=value):
            self._feedback("Saved on this device." if value else "Following the gateway default.")
            self.changed.emit()
        else:
            self._feedback("Could not save the reasoning effort.", tone="error")
        prefs = _prefs(self._controller)
        self.reasoning_note.setText(self._reasoning_caption(str(safe_attr(prefs, "reasoning_effort", value) or "")))

    def _feedback(self, text: str, *, tone: str = "") -> None:
        self.route_feedback.setText(str(text or ""))
        self.route_feedback.setProperty("tone", tone or "")
        self.route_feedback.style().unpolish(self.route_feedback)
        self.route_feedback.style().polish(self.route_feedback)

    def _apply_route_specific_state(self, row: CapabilityRouteRow) -> None:
        is_chat = row.key == "output.text"
        for widget in (self.reasoning_label, self.reasoning_combo, self.reasoning_note):
            widget.setVisible(is_chat)
        if is_chat:
            self._refresh_reasoning()
        is_voice = row.key == "output.voice"
        self.voice_label.setVisible(is_voice)
        self.voice_combo.setVisible(is_voice)
        if is_voice:
            self._refresh_voice_choices()
        supports_base_url = row.key in _BASE_URL_ROUTES
        self.show_advanced.setVisible(supports_base_url)
        if not supports_base_url:
            self.show_advanced.setChecked(False)

    def _apply_advanced_visibility(self) -> None:
        visible = bool(self.show_advanced.isChecked()) and bool(self.show_advanced.isVisible() or self.show_advanced.isVisibleTo(self))
        self.base_url_label.setVisible(visible)
        self.base_url_edit.setVisible(visible)

    def _merged_options(self) -> Dict[str, Any]:
        row = self._active_row()
        if row is None:
            return {}
        options: Dict[str, Any] = {}
        try:
            parsed = safe_call(self._controller, "parse_options", self.options_edit.toPlainText(), default=None)
            if isinstance(parsed, dict):
                options = dict(parsed)
        except Exception:
            options = {}
        if row.key == "output.voice":
            voice = str(self.voice_combo.currentData() or "").strip()
            if voice:
                options["voice"] = voice
            else:
                options.pop("voice", None)
                options.pop("profile", None)
        return options

    # ------------------------------------------------------------------ actions

    def _save_route(self) -> None:
        row = self._active_row()
        if row is None:
            return
        if self.route_mode_default.isChecked():
            self._clear_route_override(row, already_note="Already using the gateway default.")
            return
        provider = str(self.provider_combo.currentData() or "").strip()
        model = str(self.model_combo.currentData() or "").strip()
        if not provider or not model:
            self.route_feedback.setText("Choose a provider and a model first (or switch back to the gateway default).")
            return
        try:
            self._controller.save_route_override(
                route_key=row.key,
                provider=provider,
                model=model,
                base_url=self.base_url_edit.text().strip() if row.key in _BASE_URL_ROUTES else "",
                options=self._merged_options(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self.changed.emit()
        self.refresh()
        self.route_feedback.setText(f"Override saved for this app: {provider} / {model}.")

    def _reset_route_to_gateway(self) -> None:
        row = self._active_row()
        if row is None:
            return
        self.route_mode_default.setChecked(True)
        self._clear_route_override(row, already_note="No local override to reset — already using the gateway default.")

    def _clear_route_override(self, row: CapabilityRouteRow, *, already_note: str) -> None:
        if not row.configured:
            self.route_feedback.setText(already_note)
            return
        try:
            self._controller.clear_route_override(route_key=row.key)
        except Exception as exc:
            QMessageBox.critical(self, "Reset failed", str(exc))
            return
        self.changed.emit()
        self.refresh()
        self.route_feedback.setText("Reset — this app now follows the gateway default.")

    def _set_combo_value(self, combo: QComboBox, value: str) -> None:
        target = str(value or "").strip()
        if not target:
            return
        idx = combo.findData(target)
        if idx < 0:
            idx = combo.findText(target)
        if idx >= 0:
            combo.setCurrentIndex(idx)


__all__ = ["OVERRIDE_ROUTE_LABELS", "RouteOverrideEditor", "json_dumps"]

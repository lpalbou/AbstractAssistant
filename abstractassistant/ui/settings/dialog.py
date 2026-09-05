"""The Settings window: a sidebar of sections and one page at a time.

The dialog keeps the attribute names older code and tests reach for
(`route_list`, `provider_combo`, `save_button`, `hotkey_enabled`, …) as
aliases onto the page widgets, and the three route methods delegate to the
route editor, so `test_settings_routes.py` runs unchanged.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...icons import symbol_icon
from ...theme import METRICS, THEME
from ..styles import alpha, dialog_stylesheet
from .pages import AboutPage, ConnectionPage, ModelsPage, ToolsPage, VoicePage, WindowPage, WorkspacePage


SETTINGS_QSS = f"""
    QListWidget#navList {{
        background: {alpha(THEME.text_strong, 0.02)};
        border: none;
        border-right: 1px solid {THEME.border_subtle};
        padding: 12px 8px;
        outline: none;
    }}
    QListWidget#navList::item {{
        padding: 8px 10px;
        margin-bottom: 2px;
        border-radius: {METRICS.radius_control - 1}px;
        color: {THEME.text_secondary};
        font-weight: 600;
    }}
    QListWidget#navList::item:hover {{
        background: {THEME.overlay_faint};
        color: {THEME.text_strong};
    }}
    QListWidget#navList::item:selected {{
        background: {THEME.accent_bg};
        border: 1px solid {THEME.accent_border};
        color: {THEME.text_strong};
    }}
    QWidget#settingsPageHost {{ background: transparent; }}
    QFrame#pageFooter {{
        background: transparent;
        border: none;
        border-top: 1px solid {THEME.border_subtle};
    }}
    QFrame#segmented {{ background: transparent; border: none; }}
    QPushButton#segment {{
        min-height: {METRICS.control_sm}px; max-height: {METRICS.control_sm}px;
        padding: 0 12px;
        border-radius: 0px;
        border: 1px solid {THEME.border_strong};
        background: {THEME.overlay_faint};
        color: {THEME.text_secondary};
        font-weight: 600;
        font-size: {METRICS.font_caption}px;
    }}
    QPushButton#segment[segment="first"] {{
        border-top-left-radius: {METRICS.radius_chip + 1}px;
        border-bottom-left-radius: {METRICS.radius_chip + 1}px;
    }}
    QPushButton#segment[segment="last"] {{
        border-top-right-radius: {METRICS.radius_chip + 1}px;
        border-bottom-right-radius: {METRICS.radius_chip + 1}px;
        border-left: none;
    }}
    QPushButton#segment[segment="mid"] {{ border-left: none; }}
    QPushButton#segment[segment="only"] {{ border-radius: {METRICS.radius_chip + 1}px; }}
    QPushButton#segment:hover {{ background: {THEME.overlay_hover}; color: {THEME.text_strong}; }}
    QPushButton#segment:checked {{
        background: {THEME.accent_bg};
        border-color: {THEME.accent_border};
        color: {THEME.text_strong};
    }}
    QPushButton#segment:disabled {{ color: {THEME.text_faint}; }}
    QLabel#routeLabel {{ font-size: {METRICS.font_body}px; font-weight: 700; color: {THEME.text_strong}; }}
    QLabel#routeHelp {{ color: {THEME.text_muted}; font-size: {METRICS.font_caption}px; }}
    QListWidget#routeList {{ background: {alpha(THEME.text_strong, 0.025)}; }}
"""


class SettingsDialog(QDialog):
    settings_saved = pyqtSignal()

    SECTIONS = ("connection", "models", "voice", "workspace", "tools", "window", "about")

    def __init__(self, *, controller: Any, apply_hotkey, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._apply_hotkey = apply_hotkey
        self.setWindowTitle("Settings")
        self.setMinimumSize(720, 520)
        self.resize(840, 600)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.nav = QListWidget()
        self.nav.setObjectName("navList")
        self.nav.setFixedWidth(160)
        self.nav.setIconSize(QSize(14, 14))
        self.nav.setFocusPolicy(Qt.NoFocus)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(self.nav)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self.pages: Dict[str, QWidget] = {}
        self.page_connection = ConnectionPage(controller, self)
        self.page_models = ModelsPage(controller, self)
        self.page_voice = VoicePage(controller, self.page_models.route_editor, self)
        self.page_workspace = WorkspacePage(controller, self)
        self.page_tools = ToolsPage(controller, self)
        self.page_window = WindowPage(controller, apply_hotkey, self)
        self.page_about = AboutPage(controller, self)
        for key, page in (
            ("connection", self.page_connection),
            ("models", self.page_models),
            ("voice", self.page_voice),
            ("workspace", self.page_workspace),
            ("tools", self.page_tools),
            ("window", self.page_window),
            ("about", self.page_about),
        ):
            self.pages[key] = page
            item = QListWidgetItem(symbol_icon(page.icon, color=THEME.text_secondary, size=14), getattr(page, "nav_title", "") or page.title)
            item.setData(Qt.UserRole, key)
            self.nav.addItem(item)
            self.stack.addWidget(page)
            page.changed.connect(self._on_page_changed)
        self.page_voice.navigate.connect(self.show_section)
        self.page_connection._status_ready.connect(self.page_connection._apply_status)
        self.nav.currentRowChanged.connect(self._on_nav_changed)

        # ---- compatibility aliases (tests + older callers)
        editor = self.page_models.route_editor
        self.route_editor = editor
        for name in (
            "route_list", "route_label", "route_help", "route_state", "route_feedback",
            "route_mode_default", "route_mode_custom", "route_mode_group",
            "provider_combo", "model_combo", "voice_combo", "voice_label",
            "resolution_combo", "resolution_label", "show_advanced",
            "base_url_edit", "base_url_label", "options_edit", "options_label",
            "refresh_button", "reset_route_button", "save_button",
        ):
            setattr(self, name, getattr(editor, name))
        conn = self.page_connection
        for name in (
            "gateway_url_edit", "auth_mode_combo", "bearer_token_edit", "bearer_token_label",
            "gateway_user_edit", "gateway_user_label", "gateway_user_token_edit", "gateway_user_token_label",
            "remember_session", "connection_status", "connection_feedback",
            "connection_refresh_button", "connection_logout_button", "connection_save_button",
        ):
            setattr(self, name, getattr(conn, name))
        voice = self.page_voice
        self.auto_speak = voice.auto_speak
        self.voice_quality_combo = voice.voice_quality_combo
        window = self.page_window
        self.hotkey_enabled = window.hotkey_enabled
        self.hotkey_edit = window.hotkey_edit
        self.width_spin = window.width_spin
        self.height_spin = window.height_spin
        self.bottom_offset_spin = window.bottom_offset_spin
        self.settings_tabs = self.stack  # older name

        self.setStyleSheet(dialog_stylesheet() + SETTINGS_QSS)
        self.nav.setCurrentRow(0)
        self.refresh()

    # ---- routing
    @property
    def _route_rows(self) -> List[Any]:
        return self.route_editor.rows()

    def _save_route(self) -> None:
        self.route_editor._save_route()

    def _reset_route_to_gateway(self) -> None:
        self.route_editor._reset_route_to_gateway()

    def _refresh_models_for_provider(self, *, row=None) -> None:
        self.route_editor._refresh_models_for_provider(row=row)

    def _load_selected_route(self, index: int) -> None:
        self.route_editor._load_selected_route(index)

    def _focus_route(self, route_key: str) -> None:
        self.show_section("models", route_key)

    def _save_preferences(self) -> None:
        self.page_window._save_preferences()

    # ---- navigation
    def show_section(self, section: str, route_key: str = "") -> None:
        key = str(section or "").strip().lower()
        for row in range(self.nav.count()):
            if self.nav.item(row).data(Qt.UserRole) == key:
                self.nav.setCurrentRow(row)
                break
        if route_key:
            self.route_editor.focus_route(route_key)

    def current_section(self) -> str:
        item = self.nav.currentItem()
        return str(item.data(Qt.UserRole)) if item is not None else ""

    def _on_nav_changed(self, row: int) -> None:
        if row < 0:
            return
        self.stack.setCurrentIndex(row)
        page = self.stack.widget(row)
        if page is not None and page is not self.page_models:
            try:
                page.refresh()
            except Exception:
                pass

    def _on_page_changed(self) -> None:
        self.settings_saved.emit()
        # A route change updates what the voice page summarizes.
        try:
            self.page_voice._refresh_summaries()
        except Exception:
            pass

    def refresh(self) -> None:
        for page in self.pages.values():
            try:
                page.refresh()
            except Exception:
                continue


class ToolSettingsDialog(SettingsDialog):
    """Compatibility shim: the Tools window is now the Tools page of Settings."""

    def __init__(self, *, controller: Any, parent: Optional[QWidget] = None, apply_hotkey=None) -> None:
        super().__init__(controller=controller, apply_hotkey=apply_hotkey or (lambda: None), parent=parent)
        self.show_section("tools")


__all__ = ["SETTINGS_QSS", "SettingsDialog", "ToolSettingsDialog"]

"""The Settings window: a sidebar of sections and one page at a time.

The dialog keeps the attribute names older code and tests reach for
(`route_list`, `provider_combo`, `hotkey_enabled`, …) as aliases onto the page
widgets.

Deliberately NOT aliased any more: `route_mode_default` / `route_mode_custom`
(the radio pair is gone — the provider list's first item is "Gateway default")
and `save_button` / `reset_route_button` / `refresh_button` (a choice applies
when it is made). An alias for a control that no longer exists would let a test
pass against a UI the user cannot operate.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...icons import symbol_icon
from ...theme import METRICS, THEME
from ..styles import alpha, dialog_stylesheet
from .pages import AboutPage, ConnectionPage, ModelsPage, ToolsPage, VoicePage, WindowPage, WorkflowPage, WorkspacePage


def build_settings_qss() -> str:
    """Rebuilt on demand: frozen at import, Settings kept the palette it was
    born with and never followed a theme switch."""
    return f"""
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


SETTINGS_QSS: str = build_settings_qss()


class SettingsDialog(QDialog):
    settings_saved = pyqtSignal()
    #: Emitted after `_fit_to_content` set the window's size (it can change
    #: after the window was placed on screen).
    fitted = pyqtSignal()

    SECTIONS = ("connection", "models", "workflow", "voice", "workspace", "tools", "window", "about")

    def __init__(self, *, controller: Any, apply_hotkey, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._apply_hotkey = apply_hotkey
        self.setWindowTitle("Settings")
        # Sized to the settings, and not resizable: there is nothing here that
        # benefits from being dragged, and every size the user could pick was a
        # size some page did not fit (Apply and half the reasoning levels used
        # to sit off the right edge, with no horizontal scrollbar to reach
        # them). `_fit_to_content` sets the real size once the pages exist.
        self.setSizeGripEnabled(False)

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
        self.page_workflow = WorkflowPage(controller, self)
        self.page_voice = VoicePage(controller, self.page_models.route_editor, self)
        self.page_workspace = WorkspacePage(controller, self)
        self.page_tools = ToolsPage(controller, self)
        self.page_window = WindowPage(controller, apply_hotkey, self)
        self.page_about = AboutPage(controller, self)
        for key, page in (
            ("connection", self.page_connection),
            ("models", self.page_models),
            ("workflow", self.page_workflow),
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
            "provider_combo", "model_combo", "voice_combo", "voice_label",
            "reasoning_combo", "resolution_combo", "resolution_label",
            "base_url_edit", "base_url_label", "options_edit", "options_label",
        ):
            setattr(self, name, getattr(editor, name))
        conn = self.page_connection
        for name in (
            "gateway_url_edit", "auth_mode_combo", "bearer_token_edit", "bearer_token_label",
            "gateway_user_edit", "gateway_user_label", "gateway_user_token_edit", "gateway_user_token_label",
            "connection_status", "connection_feedback",
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

        self.restyle()
        self.nav.setCurrentRow(0)
        self.refresh()
        self.resize(880, 640)  # provisional; the real size is set on first show

    def restyle(self) -> None:
        """Re-read the palette (the theme changed, or this is the first paint)."""
        self.setStyleSheet(dialog_stylesheet() + build_settings_qss())
        # Nav icons are QListWidgetItem icons, not widget icons, so the
        # palette's icon sweep cannot reach them — they kept the tint they
        # were built with and washed out on a light theme.
        for row in range(self.nav.count()):
            item = self.nav.item(row)
            page = self.pages.get(str(item.data(Qt.UserRole) or ""))
            if page is not None:
                item.setIcon(symbol_icon(page.icon, color=THEME.text_secondary, size=14))
        # The type scale follows the user's text size, so control heights and
        # label widths move with it — a window fixed to the old scale would
        # clip the new one. Re-fit, but only once the first fit has happened
        # (before that the pages have no usable hints).
        if getattr(self, "_sized", False):
            # Deferred: the sheet was set a moment ago and the widgets have not
            # re-polished yet, so measuring now reads the OLD control sizes and
            # comes out a few pixels short.
            QTimer.singleShot(0, self._refit)

    # ---- routing
    @property
    def _route_rows(self) -> List[Any]:
        return self.route_editor.rows()

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

    def showEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().showEvent(event)
        # Size on the first show, not at construction: before the pages are
        # laid out their hints are inflated, and the window came out 180px
        # wider than anything in it needed.
        if not getattr(self, "_sized", False):
            self._sized = True
            self._fit_to_content()

    def _refit(self) -> None:
        """Re-measure after the type scale changed."""
        # A fixed window cannot grow into new content hints, so release the
        # constraint before measuring.
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self._fit_to_content()

    def _fit_to_content(self) -> None:
        """Fix the window to the largest page.

        The chrome (nav rail, header, footer, margins) is MEASURED — the
        difference between the window and a page's viewport at the current
        size — rather than guessed from constants that drift.
        """
        page = self.stack.currentWidget()
        if page is None or not hasattr(page, "scroll"):
            return
        chrome_h = max(0, self.height() - page.scroll.viewport().height())
        # A wrapped label reports the width of its longest UNWRAPPED line as a
        # minimum — one help sentence demanded 638px while rendering at 249px,
        # which is what pushed the Models page past the viewport. Wrapping is
        # exactly the licence to be narrower, so give them a real floor first.
        for label in self.findChildren(QLabel):
            if label.wordWrap() and label.minimumWidth() == 0:
                label.setMinimumWidth(min(label.minimumSizeHint().width(), 240))

        # Width: the widest page, so nothing is ever cut off horizontally —
        # there is no horizontal scrollbar to reach anything that overflows.
        # A page still parked at the stack's placeholder size reports a stale
        # hint (the route list re-measures its own width on resize), so each
        # page is brought to the front and laid out before it is measured.
        # This runs before the first paint, so nothing flickers.
        # Chrome (nav rail, margins, and the vertical scrollbar when a page
        # has one) is MEASURED per page rather than guessed from constants,
        # and the WIDEST wins: measuring it once on whichever page happened to
        # be current sized the window for a page without a scrollbar and then
        # clipped every page that has one.
        restore = self.stack.currentWidget()
        widths = []
        chromes = []
        for candidate in self.pages.values():
            self.stack.setCurrentWidget(candidate)
            host = candidate.scroll.widget()
            for target in (self, candidate, host):
                layout = target.layout()
                if layout is not None:
                    layout.activate()
            widths.append(host.minimumSizeHint().width())
            chromes.append(max(0, self.width() - candidate.scroll.viewport().width()))
        if restore is not None:
            self.stack.setCurrentWidget(restore)
        width = max(widths, default=640)
        chrome_w = max(chromes, default=0)
        # Height: a comfortable window, not the tallest page — Tools lists every
        # tool the gateway offers and is thousands of pixels long, so that one
        # scrolls by design.
        screen = QApplication.primaryScreen()
        room = int(screen.availableGeometry().height() * 0.82) if screen else 760
        # 20% shorter than the first cut, which was taller than anything here
        # needed. Long pages (Tools lists every tool the gateway offers) scroll.
        #
        # The width is deliberately NOT capped to the screen. Capping it was
        # tried and reverted: the pages have no horizontal scrollbar (see the
        # width comment above), so a window narrower than its widest page puts
        # content permanently out of reach — `test_the_fit_measures_pages_that
        # _have_never_been_laid_out` catches exactly that. On a screen narrower
        # than ~852px this window therefore cannot fit, and `_place_aux_dialog`
        # shrinks it into the screen (2026-09-27: fully visible beats complete). Making it fit needs horizontal
        # scrolling on the pages, which is a layout decision, not a sizing one.
        self.setFixedSize(
            max(820, min(width + chrome_w, 1000)),
            max(496, min(576, room)),
        )
        self.fitted.emit()

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

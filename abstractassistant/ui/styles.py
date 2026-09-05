"""Shared Qt stylesheets built from the design tokens in ``theme.py``.

Every secondary window (Settings, tool approval, run activity, tools used,
files affected, ask-user) applies ``dialog_stylesheet()`` so they read as one
application: the same surface, type scale, control heights, radii and accent.
Widgets opt into roles through ``objectName`` and the ``tone`` / ``kind``
dynamic properties listed below; they never carry their own hex literals, and
neither does this module: every colour is a ``THEME`` token or an alpha
variant of one (``alpha()``).

Roles (objectName)                     Tones (property "tone")
- dialogTitle / dialogSubtitle          info | success | warning | error
- sectionTitle / sectionHelp            attention | paused | offline
- settingsCard / cardTitle / cardHelp   observe | act | outreach | destroy | unknown
- statusNote / feedbackNote / banner    thinking | tool | waiting | idle
- primaryButton / secondaryButton / dangerButton / ghostButton / linkButton / iconButton
- chip (small pill label) · keyHint (keyboard key cap)
- monoPanel (read-only monospace well) · askPrompt (rich-text question)

Type floor: nothing here is set below ``METRICS.font_caption`` (11 px).
"""

from __future__ import annotations

from typing import Dict, Tuple

from abstractassistant.theme import METRICS, THEME


FONT_STACK = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", "Segoe UI", Roboto, Arial'
MONO_STACK = '"SF Mono", Menlo, Monaco, Consolas, monospace'


def alpha(color: str, value: float) -> str:
    """``rgba(...)`` derived from a ``#rrggbb`` theme token (no new literals).

    Non-hex inputs (already ``rgba``) are returned unchanged so callers can
    pass any token.
    """
    text = str(color or "").strip()
    if text.startswith("#") and len(text) == 7:
        r, g, b = (int(text[i : i + 2], 16) for i in (1, 3, 5))
        return f"rgba({r}, {g}, {b}, {max(0.0, min(1.0, float(value))):.2f})"
    return text


def tone_colors() -> Dict[str, Tuple[str, str, str]]:
    """``tone -> (foreground, background, border)`` for chips, notes, banners.

    One table feeds every toned surface so a "warning" chip, note and banner
    always agree. Risk tiers run calm → loud: observe is neutral on purpose
    (spec §1.2) so the tiers that matter stand out.
    """
    t = THEME
    neutral = (t.text_secondary, t.overlay_faint, t.border_subtle)
    success = (t.positive, t.positive_bg, alpha(t.positive, 0.30))
    warning = (t.warning, t.warning_bg, alpha(t.warning, 0.30))
    error = (t.danger_text, t.danger_bg, alpha(t.danger, 0.35))
    attention = (t.attention_text, t.attention_bg, t.attention_border)
    return {
        "neutral": neutral,
        "info": (t.accent_text, t.accent_bg, t.accent_border),
        "success": success,
        "ok": success,
        "warning": warning,
        "warn": warning,
        "error": error,
        "danger": error,
        # Needs-you states (approval / input waits, tray badge).
        "attention": attention,
        "paused": neutral,
        "offline": warning,
        # Tool risk tiers (gateway `risk_tier`): calm → loud.
        "observe": neutral,
        "act": (t.warning, alpha(t.warning, 0.12), alpha(t.warning, 0.30)),
        "outreach": (t.attention_text, t.attention_bg, alpha(t.attention, 0.36)),
        "destroy": (t.danger_text, alpha(t.danger, 0.14), alpha(t.danger, 0.36)),
        "unknown": (t.text_muted, t.overlay_faint, t.border_subtle),
        # Live-activity phases.
        "thinking": (t.accent, alpha(t.accent, 0.10), alpha(t.accent, 0.30)),
        "tool": (t.warning, alpha(t.warning, 0.10), alpha(t.warning, 0.32)),
        "waiting": (t.attention, t.attention_bg, t.attention_border),
        "idle": (t.text_muted, t.overlay_faint, t.border_subtle),
    }


def _tone_rules() -> str:
    rules = []
    for tone, (fg, bg, border) in tone_colors().items():
        rules.append(
            f'QLabel#chip[tone="{tone}"] {{ color: {fg}; background: {bg}; border: 1px solid {border}; }}'
        )
        rules.append(
            f'QLabel#statusNote[tone="{tone}"], QLabel#banner[tone="{tone}"] '
            f'{{ color: {fg}; background: {bg}; border: 1px solid {border}; }}'
        )
    return "\n".join(rules)


def dialog_stylesheet() -> str:
    """The one stylesheet every secondary window applies."""
    t = THEME
    m = METRICS
    return f"""
        QDialog, QWidget#dialogRoot {{
            background: {t.surface_sunken};
            color: {t.text_primary};
            font-family: {FONT_STACK};
            font-size: {m.font_ui}px;
        }}
        QLabel {{
            color: {t.text_secondary};
            font-size: {m.font_ui}px;
            background: transparent;
        }}
        QLabel#dialogTitle, QLabel#sectionTitle {{
            color: {t.text_strong};
            font-size: {m.font_title}px;
            font-weight: 700;
        }}
        QLabel#dialogSubtitle, QLabel#sectionHelp, QLabel#cardHelp, QLabel#rowHelp {{
            color: {t.text_muted};
            font-size: {m.font_caption}px;
        }}
        QLabel#cardTitle, QLabel#routeLabel {{
            color: {t.text_strong};
            font-size: {m.font_body}px;
            font-weight: 700;
        }}
        QLabel#rowLabel {{
            color: {t.text_primary};
            font-size: {m.font_ui}px;
            font-weight: 600;
        }}
        QLabel#rowValue {{
            color: {t.text_secondary};
            font-size: {m.font_ui}px;
        }}
        QLabel#mono, QLabel#activityMono {{
            font-family: {MONO_STACK};
            font-size: {m.font_caption}px;
            color: {t.text_secondary};
        }}
        QLabel#keyHint {{
            color: {t.text_faint};
            font-size: {m.font_caption}px;
            font-weight: 600;
            background: {t.overlay_faint};
            border: 1px solid {t.border_subtle};
            border-radius: 4px;
            padding: 0px 5px;
            min-height: 16px;
            max-height: 16px;
        }}
        QFrame#settingsCard, QFrame#card {{
            background: {t.overlay_faint};
            border: 1px solid {t.border_subtle};
            border-radius: {m.radius_control + 3}px;
        }}
        QFrame#cardRow {{
            background: transparent;
            border: none;
            border-top: 1px solid {alpha(t.text_secondary, 0.08)};
        }}
        QFrame#cardRow[first="true"] {{
            border-top: none;
        }}
        QFrame#divider {{
            background: {t.border_subtle};
            max-height: 1px;
            min-height: 1px;
            border: none;
        }}
        QLabel#statusNote, QLabel#banner {{
            color: {t.accent_text};
            background: {t.accent_bg};
            border: 1px solid {t.accent_border};
            border-radius: {m.radius_control}px;
            padding: 7px 10px;
            font-size: {m.font_caption}px;
        }}
        QLabel#feedbackNote {{
            color: {t.positive};
            font-size: {m.font_caption}px;
            font-weight: 600;
        }}
        QLabel#feedbackNote[tone="error"] {{
            color: {t.danger_text};
        }}
        QLabel#feedbackNote[tone="warning"] {{
            color: {t.warning};
        }}
        QLabel#feedbackNote[tone="info"] {{
            color: {t.text_muted};
        }}
        QLabel#chip {{
            padding: 1px 8px;
            border-radius: 8px;
            font-size: {m.font_caption}px;
            font-weight: 700;
            letter-spacing: 0.02em;
            color: {t.text_secondary};
            background: {t.overlay_faint};
            border: 1px solid {t.border_subtle};
        }}
        {_tone_rules()}
        QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QListWidget, QSpinBox, QDoubleSpinBox {{
            background: {t.surface_raised};
            color: {t.text_primary};
            border: 1px solid {t.border_subtle};
            border-radius: {m.radius_control - 2}px;
            padding: 3px 9px;
            font-size: {m.font_ui}px;
            selection-background-color: {alpha(t.accent, 0.35)};
        }}
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
            min-height: {m.control_sm}px;
            max-height: {m.control_sm}px;
        }}
        QPlainTextEdit, QTextEdit {{
            padding: 6px 9px;
        }}
        QLineEdit:hover, QComboBox:hover, QPlainTextEdit:hover, QTextEdit:hover, QListWidget:hover, QSpinBox:hover {{
            border-color: {t.accent_border};
        }}
        QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus, QListWidget:focus, QSpinBox:focus {{
            border-color: {t.accent};
            background: {t.overlay_hover};
        }}
        QLineEdit:disabled, QComboBox:disabled, QPlainTextEdit:disabled, QSpinBox:disabled {{
            color: {t.text_faint};
            background: transparent;
            border-color: {alpha(t.text_faint, 0.18)};
        }}
        QLineEdit[invalid="true"], QPlainTextEdit[invalid="true"] {{
            border-color: {t.danger};
        }}
        QLineEdit[readOnly="true"] {{
            color: {t.text_secondary};
        }}
        QComboBox {{
            padding-right: 24px;
        }}
        QComboBox::drop-down {{
            border: none;
            width: 22px;
        }}
        QComboBox QAbstractItemView {{
            background: {t.surface_raised};
            color: {t.text_primary};
            border: 1px solid {t.border_strong};
            selection-background-color: {alpha(t.accent, 0.28)};
            selection-color: {t.text_strong};
            border-radius: {m.radius_control - 2}px;
            padding: 3px;
            outline: none;
        }}
        QSpinBox::up-button, QSpinBox::down-button {{
            width: 14px;
            border: none;
            background: transparent;
        }}
        QCheckBox, QRadioButton {{
            spacing: 7px;
            font-size: {m.font_ui}px;
            color: {t.text_primary};
            background: transparent;
        }}
        QCheckBox::indicator, QRadioButton::indicator {{
            width: 15px;
            height: 15px;
            border: 1px solid {t.border_strong};
            background: {t.overlay_faint};
        }}
        QCheckBox::indicator {{
            border-radius: 4px;
        }}
        QRadioButton::indicator {{
            border-radius: 8px;
        }}
        QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
            border-color: {t.accent_border};
        }}
        QCheckBox::indicator:checked {{
            background: {t.accent};
            border-color: {t.accent};
            image: none;
        }}
        QRadioButton::indicator:checked {{
            /* Solid accent disc (the checkbox is the same fill, squared):
               no gradient, no image resource. */
            background: {t.accent};
            border-color: {t.accent};
            image: none;
        }}
        QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
            border-color: {alpha(t.text_faint, 0.30)};
            background: transparent;
        }}
        QCheckBox:disabled, QRadioButton:disabled {{
            color: {t.text_faint};
        }}
        QPushButton {{
            min-height: {m.control_sm}px;
            border-radius: {m.radius_control - 2}px;
            padding: 3px 14px;
            border: 1px solid {t.border_strong};
            background: {t.surface_control};
            color: {t.text_primary};
            font-weight: 600;
            font-size: {m.font_ui}px;
        }}
        QPushButton:hover {{
            background: {t.surface_control_hover};
            border-color: {t.accent_border};
        }}
        QPushButton:pressed {{
            background: {t.surface_control_pressed};
        }}
        QPushButton:disabled {{
            color: {t.text_faint};
            background: transparent;
            border-color: {alpha(t.text_faint, 0.18)};
        }}
        QPushButton#primaryButton {{
            background: {t.primary};
            border-color: {t.primary};
            color: {t.text_strong};
        }}
        QPushButton#primaryButton:hover {{
            background: {t.primary_hover};
            border-color: {t.primary_hover};
        }}
        QPushButton#primaryButton:pressed {{
            background: {t.primary_pressed};
        }}
        QPushButton#primaryButton:disabled {{
            background: {alpha(t.primary, 0.35)};
            border-color: transparent;
            color: {alpha(t.text_strong, 0.55)};
        }}
        QPushButton#secondaryButton, QPushButton#ghostButton {{
            background: {t.overlay_faint};
            color: {t.text_secondary};
            border: 1px solid {t.border_subtle};
        }}
        QPushButton#ghostButton {{
            background: transparent;
            border-color: transparent;
        }}
        QPushButton#secondaryButton:hover, QPushButton#ghostButton:hover {{
            background: {t.overlay_hover};
            border-color: {t.border_strong};
            color: {t.text_strong};
        }}
        QPushButton#dangerButton {{
            background: {t.danger_bg};
            border: 1px solid {alpha(t.danger, 0.35)};
            color: {t.danger_text};
        }}
        QPushButton#dangerButton:hover {{
            background: {alpha(t.danger, 0.22)};
            border-color: {alpha(t.danger, 0.55)};
        }}
        QPushButton#linkButton {{
            background: transparent;
            border: none;
            color: {t.accent};
            padding: 0px 2px;
            min-height: 0px;
            font-weight: 600;
            text-align: left;
        }}
        QPushButton#linkButton:hover {{
            text-decoration: underline;
        }}
        QPushButton#iconButton {{
            min-height: {m.control_sm}px;
            max-height: {m.control_sm}px;
            min-width: {m.control_sm}px;
            max-width: {m.control_sm}px;
            padding: 0px;
            border-radius: {m.radius_control - 2}px;
            background: {t.overlay_faint};
            border: 1px solid {t.border_subtle};
        }}
        QPushButton#iconButton:hover {{
            background: {t.overlay_hover};
        }}
        QPushButton#iconButton:checked {{
            background: {t.accent_bg};
            border-color: {t.accent_border};
        }}
        QListWidget {{
            padding: 4px;
            outline: none;
        }}
        QListWidget::item {{
            background: transparent;
            border: 1px solid transparent;
            border-radius: {m.radius_chip}px;
            padding: 5px 8px;
            margin-bottom: 1px;
            color: {t.text_secondary};
        }}
        QListWidget::item:hover {{
            background: {t.overlay_faint};
            color: {t.text_strong};
        }}
        QListWidget::item:selected {{
            background: {t.accent_bg};
            border-color: {t.accent_border};
            color: {t.text_strong};
        }}
        QListWidget#navList {{
            background: transparent;
            border: none;
            padding: 0px;
        }}
        QListWidget#navList::item {{
            padding: 7px 10px;
            font-weight: 600;
        }}
        QPlainTextEdit#monoPanel, QPlainTextEdit#toolApprovalRawPanel {{
            background: {t.code.background};
            color: {t.code.text};
            border: 1px solid {t.code.border};
            border-radius: {m.radius_control - 1}px;
            padding: 8px;
            font-family: {MONO_STACK};
            font-size: {m.font_caption}px;
        }}
        QTextBrowser#askPrompt {{
            background: transparent;
            border: none;
            padding: 0px;
            color: {t.text_primary};
            font-size: {m.font_body}px;
        }}
        QScrollArea {{
            border: none;
            background: transparent;
        }}
        QScrollArea > QWidget > QWidget {{
            background: transparent;
        }}
        QScrollBar:vertical {{
            width: 8px;
            background: transparent;
            margin: 4px 0 4px 0;
        }}
        QScrollBar::handle:vertical {{
            background: {alpha(t.text_strong, 0.14)};
            border-radius: 4px;
            min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {alpha(t.text_strong, 0.24)};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
        QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical,
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: transparent;
            border: none;
            height: 0px;
        }}
        QScrollBar:horizontal {{
            height: 8px;
            background: transparent;
            margin: 0 4px 0 4px;
        }}
        QScrollBar::handle:horizontal {{
            background: {alpha(t.text_strong, 0.14)};
            border-radius: 4px;
            min-width: 24px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: transparent;
            border: none;
            width: 0px;
        }}
        QToolTip {{
            background: {t.surface_raised};
            color: {t.text_primary};
            border: 1px solid {t.border_strong};
            padding: 6px 8px;
            font-size: {m.font_caption}px;
        }}
    """


def refresh_style(widget) -> None:
    """Re-polish a widget after a dynamic property (tone/kind) changed."""
    try:
        style = widget.style()
        if style is not None:
            style.unpolish(widget)
            style.polish(widget)
        widget.update()
    except Exception:
        pass


__all__ = ["FONT_STACK", "MONO_STACK", "alpha", "dialog_stylesheet", "refresh_style", "tone_colors"]

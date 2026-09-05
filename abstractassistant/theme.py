"""Single source of truth for the assistant's visual design tokens.

Historically colors/spacing were hardcoded at ~440 call sites across the UI,
which made the look inconsistent and impossible to retune. This module holds
the semantic palette + metric scale; UI code should reference these tokens
rather than raw literals. The app ships a dark glass theme; the token system
is instance-based so a light theme is a second `Theme(...)` later (blockers
recorded below) rather than new plumbing.

Light-mode blockers (deliberately deferred):
- markdown CSS is embedded per-message HTML → needs renderer re-instantiation
  on a theme switch;
- a couple of markdown tests pin exact hex values;
- pygments token colors are dark-tuned (see CodePalette).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
class CodePalette:
    """Colors for rendered code blocks / inline code (dark-tuned)."""

    background: str = "#101722"
    border: str = "#2a3444"
    inline_bg: str = "rgba(255, 255, 255, 0.07)"
    text: str = "#e6edf6"
    accent_spine: str = "#4b7bb5"
    keyword: str = "#ff6fae"
    string: str = "#8fd08a"
    comment: str = "#7d8aa0"
    number: str = "#f0b072"


@dataclass(frozen=True)
class Theme:
    """Semantic dark-glass palette. Reference these, never raw hex."""

    # Surfaces
    surface_card: str = "rgba(16, 22, 31, 0.98)"     # top bar / history / composer cards
    surface_sunken: str = "#0b0f16"                  # dialogs, raw wells
    surface_raised: str = "#181e27"                  # inputs, popup lists
    surface_control: str = "#1c2430"                 # solid buttons
    surface_control_hover: str = "#243041"
    surface_control_pressed: str = "#131922"
    overlay_faint: str = "rgba(255, 255, 255, 0.04)"    # ghost buttons at rest
    overlay_hover: str = "rgba(255, 255, 255, 0.09)"
    overlay_active: str = "rgba(255, 255, 255, 0.12)"

    # Text
    text_strong: str = "#f8fafc"
    text_primary: str = "#edf2f8"
    text_secondary: str = "#b9c7d7"
    text_muted: str = "#8fa1b5"
    text_faint: str = "#71839a"

    # Borders
    border_subtle: str = "rgba(166, 187, 214, 0.14)"
    border_strong: str = "rgba(130, 150, 178, 0.28)"

    # One blue accent family (informational, links, focus)
    accent: str = "#79c7ff"
    accent_text: str = "#b9dcff"
    accent_bg: str = "rgba(121, 199, 255, 0.12)"
    accent_border: str = "rgba(121, 199, 255, 0.30)"

    # One action-green family (send, primary CTAs)
    primary: str = "#2e8b63"
    primary_hover: str = "#37a272"
    primary_pressed: str = "#236749"
    positive: str = "#5ed2a1"
    positive_bg: str = "rgba(94, 210, 161, 0.14)"

    # Status
    warning: str = "#f0c979"
    warning_bg: str = "rgba(181, 123, 22, 0.12)"
    danger: str = "#ff6b6e"
    danger_text: str = "#ffb4b4"
    danger_bg: str = "rgba(145, 39, 39, 0.14)"
    # Attention ("needs YOU"): approval / input waits, tray "waiting" badge.
    # Distinct from warning (something is off) and from primary (go).
    attention: str = "#fb923c"
    attention_text: str = "#ffd0a8"
    attention_bg: str = "rgba(251, 146, 60, 0.14)"
    attention_border: str = "rgba(251, 146, 60, 0.42)"

    # User-message identity (indigo, distinct from the blue UI accent)
    user_bg: str = "rgba(99, 102, 241, 0.20)"
    user_border: str = "rgba(99, 102, 241, 0.40)"

    code: CodePalette = field(default_factory=CodePalette)


@dataclass(frozen=True)
class Metrics:
    """Spacing / radius / size / type scale. 4-based spacing."""

    space: Tuple[int, ...] = (4, 8, 12, 16, 20, 24)
    radius_chip: int = 6
    radius_control: int = 9
    radius_pill: int = 14
    radius_card: int = 16
    control_sm: int = 28
    control_md: int = 36
    control_lg: int = 38
    icon_sm: int = 16
    icon_md: int = 18
    icon_lg: int = 21
    font_caption: int = 11
    font_ui: int = 12
    font_body: int = 13
    font_title: int = 15
    font_display: int = 20


# Module-level singletons (the app is single-theme today).
THEME = Theme()
METRICS = Metrics()

"""Translating a stylesheet from one palette to another.

The app's chrome is 22k characters of colour literals rather than tokens, so a
theme switch translates them instead of rewriting them. Three invariants make
that safe, and all three were violated by the first cut:

* with no theme selected the sheet must come back byte-identical;
* an opaque colour must stay opaque — answering solid text with a 4%-alpha
  wash took an 8:1 contrast to 1.3:1 on the app's OWN palette;
* black, white and the macOS traffic lights are not palette colours.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from abstractassistant.retint import (
    MAX_MATCH_DISTANCE,
    coverage,
    parse_color,
    retint_stylesheet,
)
from abstractassistant.theme import DEFAULT_THEME, Theme
from abstractassistant.ui_themes import build_theme


def _palette_qss() -> str:
    text = (Path(__file__).resolve().parents[2] / "abstractassistant" / "app.py").read_text()
    start = text.rindex("def _apply_styles")
    open_at = text.index('_themed("""', start) + len('_themed("""')
    return text[open_at : text.index('"""', open_at)]


@pytest.mark.basic
def test_the_default_palette_is_left_exactly_alone() -> None:
    qss = _palette_qss()
    # Same object, and an equal-but-distinct palette: both are identity.
    assert retint_stylesheet(qss, source=DEFAULT_THEME, target=DEFAULT_THEME) == qss
    assert retint_stylesheet(qss, source=DEFAULT_THEME, target=Theme()) == qss


@pytest.mark.basic
def test_an_opaque_colour_never_becomes_translucent() -> None:
    """Text is opaque. Handing it a token that means "a faint wash" made it a
    ghost — on the shipped theme, before anyone picked one."""
    latte = build_theme("catppuccin-latte")
    for literal in ("#9fb0c4", "#9dd6bc", "#edf2f8", "#f8fafc"):
        out = retint_stylesheet(f"QLabel {{ color: {literal}; }}", source=DEFAULT_THEME, target=latte)
        assert "rgba" not in out, f"{literal} -> {out}"
        assert re.search(r"#[0-9a-f]{6}", out), out

    # A translucent literal keeps its own alpha.
    out = retint_stylesheet(
        "QFrame { background: rgba(121, 199, 255, 0.36); }", source=DEFAULT_THEME, target=latte
    )
    assert "0.36" in out


@pytest.mark.basic
def test_structural_and_system_colours_are_left_alone() -> None:
    latte = build_theme("catppuccin-latte")
    # Shadows are dark under every palette: re-tinting them turns a dark rim
    # into a light-on-light one.
    for literal in ("rgba(0, 0, 0, 0.16)", "#000000"):
        css = f"QFrame {{ border-color: {literal}; }}"
        assert retint_stylesheet(css, source=DEFAULT_THEME, target=latte) == css

    # White is the opposite: `rgba(255,255,255,0.05)` IS the overlay token, so
    # on a light theme it must become a DARK wash, not stay white.
    out = retint_stylesheet(
        "QFrame { background: rgba(255, 255, 255, 0.05); }", source=DEFAULT_THEME, target=latte
    )
    assert "255, 255, 255" not in out, out
    assert "0.05" in out

    # The macOS traffic lights mean close/minimise/zoom everywhere.
    for literal in ("#ff5f57", "#febc2e", "#dea123", "#28c840", "#1fa332"):
        css = f"QPushButton {{ background: {literal}; }}"
        assert retint_stylesheet(css, source=DEFAULT_THEME, target=latte) == css


@pytest.mark.basic
def test_the_translation_reaches_almost_everything() -> None:
    qss = _palette_qss()
    done, total, missed = coverage(qss, source=DEFAULT_THEME)
    assert total > 100
    assert done / total >= 0.85, f"only {done}/{total} translated; missed {missed[:8]}"
    # Whatever is left is deliberate: a shadow, a traffic light, or a colour
    # far enough from every token that guessing would be worse than leaving it.
    from dataclasses import fields

    from abstractassistant.retint import _FIXED_COLORS, _STRUCTURAL

    anchors = []
    for field in fields(Theme):
        if field.name == "code":
            continue
        parsed = parse_color(str(getattr(DEFAULT_THEME, field.name)))
        if parsed:
            anchors.append(parsed[0])

    for literal in missed:
        rgb = parse_color(literal)[0]
        if rgb in _STRUCTURAL or rgb in _FIXED_COLORS:
            continue
        nearest = min(
            sum((a - b) ** 2 for a, b in zip(rgb, anchor)) ** 0.5 for anchor in anchors
        )
        assert nearest > MAX_MATCH_DISTANCE, (
            f"{literal} is {nearest:.0f} from a token but was not translated"
        )


@pytest.mark.basic
def test_a_light_theme_actually_inverts_the_text() -> None:
    latte = build_theme("catppuccin-latte")

    def _luma(color: str) -> float:
        rgb = parse_color(color)[0]
        return sum(rgb) / 3.0

    out = retint_stylesheet(
        "QLabel { color: #edf2f8; background: rgba(16, 22, 31, 0.98); }",
        source=DEFAULT_THEME,
        target=latte,
    )
    colors = re.findall(r"color:\s*(#[0-9a-f]{6})", out)
    assert colors and _luma(colors[0]) < 128, f"text stayed light: {out}"


@pytest.mark.basic
def test_the_match_threshold_is_documented_and_bounded() -> None:
    # A colour far from every token is not "close enough" to anything.
    assert 0 < MAX_MATCH_DISTANCE < 120
    css = "QLabel { color: #7f00ff; }"  # vivid violet, nothing like a token
    assert retint_stylesheet(css, source=DEFAULT_THEME, target=build_theme("nord")) == css

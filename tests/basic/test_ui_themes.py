"""Shared framework palettes, and the preference that remembers one.

The web clients theme themselves from abstractuic's `theme.css`, and so does
this app: the stylesheet is READ, not copied, so a palette added upstream shows
up here without a code change. Each palette's eleven semantic colours are
widened into the app's full token set; a vendored snapshot is the fallback for
when neither a checkout nor the bundled copy can be found.
"""

from __future__ import annotations

import re

import pytest

from abstractassistant.preferences import AssistantPreferences, normalize_ui_theme
from abstractassistant.theme import Theme
from abstractassistant.ui_themes import (
    DEFAULT_THEME_ID,
    THEME_SPECS,
    build_theme,
    is_light,
    theme_options,
)

_COLOR = re.compile(r"^(#[0-9a-fA-F]{6}|rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*(,\s*[\d.]+\s*)?\))$")


@pytest.mark.basic
def test_every_palette_is_complete_and_grouped() -> None:
    assert len(THEME_SPECS) >= 20
    for theme_id, spec in THEME_SPECS.items():
        assert spec.label.strip(), theme_id
        assert spec.group in {"dark", "light"}, theme_id
        # Eleven colours per palette; everything else is derived from them.
        for key in (
            "bg", "bg2", "bg3", "text", "text2", "muted",
            "accent", "success", "warning", "error", "info",
        ):
            value = spec.vars.get(key, "")
            # Shorthand hex is allowed in the source palettes (the base theme
            # uses `#eee`); `build_theme` is what must widen it.
            assert re.match(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$", value or ""), (
                f"{theme_id}.{key} = {value!r}"
            )

    options = theme_options()
    # The app's own palette is offered first and is not one of the shared ones.
    assert options[0][0] == DEFAULT_THEME_ID
    assert DEFAULT_THEME_ID not in THEME_SPECS
    assert len(options) == len(THEME_SPECS) + 1
    assert len({tid for tid, _l, _g in options}) == len(options)
    assert any(group == "light" for _t, _l, group in options)


@pytest.mark.basic
def test_building_a_palette_fills_every_token_with_a_real_colour() -> None:
    from dataclasses import fields

    # The app's own theme is not rebuilt: it IS the default.
    assert build_theme(DEFAULT_THEME_ID) is None
    assert build_theme("no-such-theme") is None
    assert build_theme("") is None

    for theme_id in THEME_SPECS:
        theme = build_theme(theme_id)
        assert isinstance(theme, Theme), theme_id
        for f in fields(Theme):
            if f.name == "code":
                continue
            value = getattr(theme, f.name)
            assert _COLOR.match(str(value)), f"{theme_id}.{f.name} = {value!r}"
        for f in fields(theme.code):
            assert _COLOR.match(str(getattr(theme.code, f.name))), f"{theme_id}.code.{f.name}"


@pytest.mark.basic
def test_a_palette_keeps_its_own_identity() -> None:
    tokyo = build_theme("tokyo-night")
    spec = THEME_SPECS["tokyo-night"]
    # The palette's own colours are used, not approximated.
    assert tokyo.accent == spec.vars["accent"]
    assert tokyo.text_primary == spec.vars["text"]
    assert tokyo.positive == spec.vars["success"]
    assert tokyo.danger == spec.vars["error"]
    assert tokyo.surface_raised == spec.vars["bg2"]
    # Tinted backgrounds are alphas of the colour they tint.
    assert tokyo.accent_bg.startswith("rgba(") and "0.12" in tokyo.accent_bg
    # Two different palettes are actually different.
    assert build_theme("dracula").accent != tokyo.accent


@pytest.mark.basic
def test_light_palettes_derive_contrast_downward() -> None:
    """On a light palette the derived surfaces must get DARKER, not lighter —
    the same mix toward white that separates surfaces on a dark theme would
    erase them here."""
    assert is_light("catppuccin-latte") and is_light("light")
    assert not is_light("tokyo-night") and not is_light("nord")
    assert not is_light("no-such-theme")

    def _luma(color: str) -> float:
        body = color.lstrip("#")
        return sum(int(body[i : i + 2], 16) for i in (0, 2, 4)) / 3.0

    light = build_theme("catppuccin-latte")
    dark = build_theme("tokyo-night")
    assert _luma(light.surface_sunken) < _luma(THEME_SPECS["catppuccin-latte"].vars["bg"])
    assert _luma(dark.surface_sunken) > _luma(THEME_SPECS["tokyo-night"].vars["bg"])
    # Its text stays dark-on-light, so it is readable at all.
    assert _luma(light.text_primary) < 128 < _luma(dark.text_primary)


@pytest.mark.basic
def test_the_choice_survives_a_relaunch_and_a_deleted_theme() -> None:
    prefs = AssistantPreferences.from_dict({"ui_theme": "gruvbox"})
    assert prefs.ui_theme == "gruvbox"
    # Saved and reloaded, as a relaunch does.
    assert AssistantPreferences.from_dict(prefs.to_dict()).ui_theme == "gruvbox"
    assert "ui_theme" in prefs.to_dict()

    # A theme renamed or dropped upstream must not brick the UI.
    assert normalize_ui_theme("no-such-theme") == DEFAULT_THEME_ID
    assert normalize_ui_theme("") == DEFAULT_THEME_ID
    assert normalize_ui_theme(None) == DEFAULT_THEME_ID
    assert AssistantPreferences.from_dict({}).ui_theme == DEFAULT_THEME_ID
    # Case and padding are forgiven.
    assert normalize_ui_theme("  Tokyo-Night ") == "tokyo-night"


@pytest.mark.basic
def test_a_theme_added_upstream_appears_with_no_code_change(tmp_path) -> None:
    """The point of reading abstractuic's stylesheet instead of copying it."""
    from abstractassistant.ui_themes import _specs_from_css

    css = tmp_path / "theme.css"
    css.write_text(
        """
:root { --bg-primary: #101010; --bg-secondary: #181818; --bg-tertiary: #222222;
  --text-primary: #eee; --text-secondary: #ccc; --text-muted: #888;
  --accent: #ff8800; --success: #33cc66; --warning: #ffcc33;
  --error: #ff4444; --info: #4488ff; }
:root.theme-solar-flare { --bg-primary: #1b1206; --accent: #ff9d2e; }
:root.theme-paper { --bg-primary: #fdfdf7; --text-primary: #202020; }
:root.theme-broken { --accent: not-a-colour; --bg-primary: also-not; }
""",
        encoding="utf-8",
    )
    specs = _specs_from_css(css)

    # A palette declared upstream is picked up, named from its id...
    assert specs["solar-flare"].label == "Solar Flare"
    assert specs["solar-flare"].vars["accent"] == "#ff9d2e"
    # ...inherits what it does not override...
    assert specs["solar-flare"].vars["success"] == "#33cc66"
    # ...and is grouped by measuring its own background, not by a hand-kept list.
    assert specs["solar-flare"].group == "dark"
    assert specs["paper"].group == "light"
    # Shorthand hex is widened on the way in, so `styles.alpha()` can never
    # be handed a `#eee` it would silently pass through opaque.
    assert specs["solar-flare"].vars["text"] == "#eeeeee"
    # A palette with an unusable colour is skipped, not half-loaded.
    assert "broken" not in specs
    # Every one of them builds a complete Theme.
    for theme_id in specs:
        assert build_theme(theme_id) is not None or theme_id not in THEME_SPECS


@pytest.mark.basic
def test_the_vendored_copy_can_be_checked_against_abstractuic() -> None:
    """The palettes are a snapshot of another repo: there has to be a way to
    tell when it has drifted."""
    from pathlib import Path

    from abstractassistant.ui_themes import _resolve_css

    css = (
        Path(__file__).resolve().parents[2].parent
        / "abstractuic"
        / "ui-kit"
        / "src"
        / "theme.css"
    )
    if not css.exists():
        pytest.skip("abstractuic checkout not present")

    resolved = _resolve_css(css.read_text(encoding="utf-8"))
    assert set(THEME_SPECS) <= set(resolved), set(THEME_SPECS) - set(resolved)
    for theme_id, spec in THEME_SPECS.items():
        assert resolved[theme_id].get("--accent") == spec.vars["accent"], theme_id
        assert resolved[theme_id].get("--bg-primary") == spec.vars["bg"], theme_id

"""Named colour themes, shared with the rest of AbstractFramework.

The framework's web clients theme themselves from `abstractuic`'s
`ui-kit/src/theme.css`, which defines each palette as a block of CSS custom
properties. That file is the SOURCE OF TRUTH here too: it is parsed at import,
so a palette added or retuned in abstractuic shows up in this app without
anyone editing Python. It is looked for in order:

1. the sibling checkout (`../abstractuic/ui-kit/src/theme.css`) — a dev machine
   always sees the live file;
2. `assets/uic-theme.css`, which the macOS build copies in, so a packaged .app
   carries the palettes as of the build that made it;
3. the vendored snapshot below, if neither is readable.

`build_theme()` widens each palette's eleven semantic colours into the ~40
tokens `theme.Theme` needs by deriving the rest — surfaces are mixes toward the
background, overlays and borders are alpha ramps — so a palette stays
internally consistent and a NEW one costs nothing but its eleven values.
Whether it is dark or light is measured from its own background, and its label
is derived from its id, so neither has to be maintained by hand.

To see whether the vendored fallback has drifted from a checkout:
    python -m abstractassistant.ui_themes --refresh ../abstractuic/ui-kit/src/theme.css
"""

from __future__ import annotations

import re
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .theme import CodePalette, Theme

__all__ = [
    "THEME_SPECS",
    "ThemeSpec",
    "build_theme",
    "theme_options",
    "is_light",
    "DEFAULT_THEME_ID",
]

# The app's own hand-tuned dark glass, which is not one of the shared palettes.
DEFAULT_THEME_ID = "abstract-glass"

# Ids whose derived label would read wrong.
_LABEL_OVERRIDES = {"dark": "Dark (Abstract)", "light": "Light"}


@dataclass(frozen=True)
class ThemeSpec:
    """One palette: its name, whether it is dark or light, and its colours."""

    label: str
    group: str
    vars: Dict[str, str]


_VENDORED_SPECS: Dict[str, ThemeSpec] = {

    "dark": ThemeSpec(
        label="Dark (Abstract)", group="dark",
        vars={"bg": "#1a1a2e", "bg2": "#16213e", "bg3": "#0f3460", "text": "#eee", "text2": "#aaa", "muted": "#666", "accent": "#e94560", "success": "#27ae60", "warning": "#f39c12", "error": "#e74c3c", "info": "#60a5fa"},
    ),
    "observer-night": ThemeSpec(
        label="Observer Night", group="dark",
        vars={"bg": "#0b0f14", "bg2": "#10161e", "bg3": "#161e28", "text": "#d7dee8", "text2": "#8593a5", "muted": "#748096", "accent": "#e8a54a", "success": "#7bc98c", "warning": "#e0af68", "error": "#d9705a", "info": "#6ea8d8"},
    ),
    "tokyo-night": ThemeSpec(
        label="Tokyo Night", group="dark",
        vars={"bg": "#1a1b26", "bg2": "#24283b", "bg3": "#414868", "text": "#c0caf5", "text2": "#a9b1d6", "muted": "#878fb4", "accent": "#7aa2f7", "success": "#9ece6a", "warning": "#e0af68", "error": "#f7768e", "info": "#2ac3de"},
    ),
    "nord": ThemeSpec(
        label="Nord", group="dark",
        vars={"bg": "#2e3440", "bg2": "#3b4252", "bg3": "#434c5e", "text": "#eceff4", "text2": "#d8dee9", "muted": "#99b3cd", "accent": "#88c0d0", "success": "#a3be8c", "warning": "#ebcb8b", "error": "#d89fa4", "info": "#9bb0cb"},
    ),
    "one-dark": ThemeSpec(
        label="One Dark", group="dark",
        vars={"bg": "#282c34", "bg2": "#21252b", "bg3": "#3a3f4b", "text": "#abb2bf", "text2": "#9da5b4", "muted": "#848c9a", "accent": "#61afef", "success": "#98c379", "warning": "#e5c07b", "error": "#e06c75", "info": "#c678dd"},
    ),
    "catppuccin-mocha": ThemeSpec(
        label="Catppuccin Mocha", group="dark",
        vars={"bg": "#1e1e2e", "bg2": "#181825", "bg3": "#313244", "text": "#cdd6f4", "text2": "#bac2de", "muted": "#7e8297", "accent": "#cba6f7", "success": "#a6e3a1", "warning": "#f9e2af", "error": "#f38ba8", "info": "#89b4fa"},
    ),
    "catppuccin-macchiato": ThemeSpec(
        label="Catppuccin Macchiato", group="dark",
        vars={"bg": "#24273a", "bg2": "#1e2030", "bg3": "#363a4f", "text": "#cad3f5", "text2": "#b8c0e0", "muted": "#8087a2", "accent": "#c6a0f6", "success": "#a6da95", "warning": "#eed49f", "error": "#ed8796", "info": "#8aadf4"},
    ),
    "catppuccin-frappe": ThemeSpec(
        label="Catppuccin Frappe", group="dark",
        vars={"bg": "#303446", "bg2": "#292c3c", "bg3": "#414559", "text": "#c6d0f5", "text2": "#b5bfe2", "muted": "#8c93ad", "accent": "#ca9ee6", "success": "#a6d189", "warning": "#e5c890", "error": "#e78284", "info": "#8caaee"},
    ),
    "rose-pine": ThemeSpec(
        label="Rose Pine", group="dark",
        vars={"bg": "#191724", "bg2": "#1f1d2e", "bg3": "#26233a", "text": "#e0def4", "text2": "#908caa", "muted": "#88859e", "accent": "#c4a7e7", "success": "#9ccfd8", "warning": "#f6c177", "error": "#eb6f92", "info": "#3d90b1"},
    ),
    "rose-pine-moon": ThemeSpec(
        label="Rose Pine Moon", group="dark",
        vars={"bg": "#232136", "bg2": "#2a273f", "bg3": "#393552", "text": "#e0def4", "text2": "#938fac", "muted": "#9390a7", "accent": "#c4a7e7", "success": "#9ccfd8", "warning": "#f6c177", "error": "#eb6f92", "info": "#459bbd"},
    ),
    "dracula": ThemeSpec(
        label="Dracula", group="dark",
        vars={"bg": "#282a36", "bg2": "#343746", "bg3": "#44475a", "text": "#f8f8f2", "text2": "#d4d4de", "muted": "#96a0c2", "accent": "#ff79c6", "success": "#50fa7b", "warning": "#f1fa8c", "error": "#ff7979", "info": "#8be9fd"},
    ),
    "monokai": ThemeSpec(
        label="Monokai", group="dark",
        vars={"bg": "#272822", "bg2": "#2d2e27", "bg3": "#3e3d32", "text": "#f8f8f2", "text2": "#e2e2dc", "muted": "#9a9581", "accent": "#66d9ef", "success": "#a6e22e", "warning": "#e6db74", "error": "#fb5d95", "info": "#a1efe4"},
    ),
    "gruvbox": ThemeSpec(
        label="Gruvbox", group="dark",
        vars={"bg": "#282828", "bg2": "#3c3836", "bg3": "#504945", "text": "#ebdbb2", "text2": "#d5c4a1", "muted": "#ada296", "accent": "#fe8019", "success": "#b8bb26", "warning": "#fabd2f", "error": "#fc7f70", "info": "#89a99d"},
    ),
    "solarized-dark": ThemeSpec(
        label="Solarized Dark", group="dark",
        vars={"bg": "#002b36", "bg2": "#073642", "bg3": "#0b4b5a", "text": "#eee8d5", "text2": "#93a1a1", "muted": "#879ca3", "accent": "#268bd2", "success": "#8ea300", "warning": "#c49500", "error": "#e87775", "info": "#2ca9a0"},
    ),
    "everforest-dark": ThemeSpec(
        label="Everforest Dark", group="dark",
        vars={"bg": "#2b3339", "bg2": "#323c41", "bg3": "#3a464c", "text": "#d3c6aa", "text2": "#a7c080", "muted": "#9da8a0", "accent": "#83c092", "success": "#a7c080", "warning": "#dbbc7f", "error": "#e88b8d", "info": "#7fbbb3"},
    ),
    "catppuccin-latte": ThemeSpec(
        label="Catppuccin Latte", group="light",
        vars={"bg": "#eff1f5", "bg2": "#e6e9ef", "bg3": "#ccd0da", "text": "#4c4f69", "text2": "#5c5f77", "muted": "#6f758b", "accent": "#8839ef", "success": "#358423", "warning": "#a46915", "error": "#d20f39", "info": "#1e66f5"},
    ),
    "rose-pine-dawn": ThemeSpec(
        label="Rose Pine Dawn", group="light",
        vars={"bg": "#faf4ed", "bg2": "#fffaf3", "bg3": "#f2e9e1", "text": "#575279", "text2": "#6e6a86", "muted": "#787289", "accent": "#907aa9", "success": "#286983", "warning": "#a76711", "error": "#af5971", "info": "#497e88"},
    ),
    "one-light": ThemeSpec(
        label="One Light", group="light",
        vars={"bg": "#fafafa", "bg2": "#ffffff", "bg3": "#e5e5e6", "text": "#383a42", "text2": "#4f525d", "muted": "#74757d", "accent": "#4078f2", "success": "#418240", "warning": "#9d6c01", "error": "#de3121", "info": "#a626a4"},
    ),
    "everforest-light": ThemeSpec(
        label="Everforest Light", group="light",
        vars={"bg": "#fdf6e3", "bg2": "#fffbef", "bg3": "#e8e0cc", "text": "#5c6a72", "text2": "#67767e", "muted": "#6b7a6f", "accent": "#2e8f6a", "success": "#488252", "warning": "#9b6b21", "error": "#ea0e09", "info": "#317ca5"},
    ),
    "solarized-light": ThemeSpec(
        label="Solarized Light", group="light",
        vars={"bg": "#fdf6e3", "bg2": "#eee8d5", "bg3": "#e3ddc9", "text": "#073642", "text2": "#566b72", "muted": "#637880", "accent": "#268bd2", "success": "#6a7a00", "warning": "#916e00", "error": "#dc322f", "info": "#228179"},
    ),
    "light": ThemeSpec(
        label="Light", group="light",
        vars={"bg": "#f7f7fb", "bg2": "#ffffff", "bg3": "#e6e8f0", "text": "#0f172a", "text2": "#334155", "muted": "#64748b", "accent": "#e94560", "success": "#12883e", "warning": "#b16105", "error": "#dc2626", "info": "#2563eb"},
    ),
}


def _label_for(theme_id: str) -> str:
    if theme_id in _LABEL_OVERRIDES:
        return _LABEL_OVERRIDES[theme_id]
    return " ".join(part.capitalize() for part in theme_id.split("-"))


def _specs_from_css(path: Path) -> Dict[str, ThemeSpec]:
    """Every palette the stylesheet defines, labelled and grouped by measurement."""
    resolved = _resolve_css(path.read_text(encoding="utf-8"))
    out: Dict[str, ThemeSpec] = {}
    for theme_id, css_vars in resolved.items():
        values = {}
        for key, css_name in _CSS_VARS.items():
            value = _expand(str(css_vars.get(css_name, "")).strip())
            if _rgb(value) is None:
                values = {}
                break
            values[key] = value
        if not values:
            continue  # a palette that does not define all eleven is not usable
        rgb = _rgb(values["bg"]) or (0, 0, 0)
        out[theme_id] = ThemeSpec(
            label=_label_for(theme_id),
            group="light" if (sum(rgb) / 3.0) > 128 else "dark",
            vars=values,
        )
    return out


def _theme_css_candidates() -> List[Path]:
    here = Path(__file__).resolve()
    candidates = [
        # A dev checkout, beside this repo: always the live file.
        here.parents[2] / "abstractuic" / "ui-kit" / "src" / "theme.css",
    ]
    # A packaged app: what the build copied in. Frozen bundles keep data files
    # under `sys._MEIPASS`, and `__file__` there points into the archive, so
    # ask for both — the same order `app._asset_path` uses.
    frozen_base = getattr(sys, "_MEIPASS", None)
    if frozen_base:
        candidates.append(
            Path(frozen_base) / "abstractassistant" / "assets" / "uic-theme.css"
        )
    candidates.append(here.parent / "assets" / "uic-theme.css")
    return candidates


def _load_specs() -> Dict[str, ThemeSpec]:
    for candidate in _theme_css_candidates():
        try:
            if not candidate.is_file():
                continue
            specs = _specs_from_css(candidate)
        except Exception as exc:
            warnings.warn(f"#FALLBACK: could not read themes from {candidate}: {exc!r}")
            continue
        if specs:
            return specs
    return dict(_VENDORED_SPECS)


def theme_options() -> List[Tuple[str, str, str]]:
    """``(id, label, group)`` for every selectable theme, app default first."""
    out = [(DEFAULT_THEME_ID, "Abstract Glass (default)", "dark")]
    shared = [(tid, spec.label, spec.group) for tid, spec in THEME_SPECS.items()]
    # Darks first, then lights, each alphabetical: a palette added upstream
    # lands in a predictable place instead of wherever the file happened to
    # declare it.
    shared.sort(key=lambda row: (row[2] != "dark", row[1].lower()))
    out.extend(shared)
    return out


def _rgb(color: str) -> Optional[Tuple[int, int, int]]:
    text = str(color or "").strip()
    if text.startswith("#"):
        body = text[1:]
        if len(body) == 3:
            body = "".join(ch * 2 for ch in body)
        if len(body) == 6:
            return tuple(int(body[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    match = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", text)
    if match:
        return (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return None


def _expand(color: str) -> str:
    """``#abc`` -> ``#aabbcc``; anything else unchanged."""
    text = str(color or "").strip()
    if text.startswith("#") and len(text) == 4:
        return "#" + "".join(ch * 2 for ch in text[1:])
    return text


def _alpha(color: str, value: float) -> str:
    rgb = _rgb(color)
    if rgb is None:
        return color
    return f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {max(0.0, min(1.0, value)):.2f})"


def _mix(color: str, other: str, amount: float) -> str:
    first, second = _rgb(color), _rgb(other)
    if first is None or second is None:
        return color
    ratio = max(0.0, min(1.0, amount))
    return "#%02x%02x%02x" % tuple(
        round(a + (b - a) * ratio) for a, b in zip(first, second)
    )


def _is_light_color(color: str) -> bool:
    """Would black text read better than white on this colour?"""
    rgb = _rgb(color)
    if rgb is None:
        return False
    r, g, b = rgb
    # Perceived brightness, so a light sage or yellow gets dark text.
    return (0.299 * r + 0.587 * g + 0.114 * b) > 150


def is_light(theme_id: str) -> bool:
    spec = THEME_SPECS.get(str(theme_id or "").strip())
    if spec is None:
        return False
    if spec.group == "light":
        return True
    rgb = _rgb(spec.vars.get("bg", ""))
    return bool(rgb and (sum(rgb) / 3.0) > 128)


def build_theme(theme_id: str) -> Optional[Theme]:
    """The full token set for ``theme_id``; ``None`` for the app's own theme.

    Only eleven colours are given per palette, so the rest are derived from
    them rather than invented: surfaces step toward the background, text and
    borders are ramps off the palette's own text colours, and every tinted
    background is an alpha of the colour it tints. That keeps a palette
    coherent and makes a new one cost nothing but its eleven values.
    """
    spec = THEME_SPECS.get(str(theme_id or "").strip())
    if spec is None:
        return None
    # Widen shorthand hex before anything else: `styles.alpha()` only
    # recognizes the 6-digit form and returns anything else unchanged, so a
    # `#eee` token would silently make a translucent surface opaque.
    v = {key: _expand(value) for key, value in spec.vars.items()}
    bg, bg2, bg3 = v["bg"], v["bg2"], v["bg3"]
    text, text2, muted = v["text"], v["text2"], v["muted"]
    accent, info = v["accent"], v["info"]
    success, warning, error = v["success"], v["warning"], v["error"]
    # "Ink" is the direction that adds contrast: darker on light themes.
    ink = "#000000" if is_light(theme_id) else "#ffffff"
    return Theme(
        surface_card=_alpha(bg, 0.98),
        surface_sunken=_mix(bg, ink, 0.03),
        surface_raised=bg2,
        surface_control=_mix(bg2, ink, 0.06),
        surface_control_hover=_mix(bg3, ink, 0.06),
        surface_control_pressed=_mix(bg2, ink, 0.14),
        overlay_faint=_alpha(ink, 0.05),
        overlay_hover=_alpha(ink, 0.10),
        overlay_active=_alpha(ink, 0.14),
        text_strong=_mix(text, ink, 0.25),
        text_primary=text,
        text_secondary=text2,
        text_muted=muted,
        text_faint=_alpha(muted, 0.80),
        border_subtle=_alpha(muted, 0.22),
        border_strong=_alpha(muted, 0.40),
        accent=accent,
        accent_text=_mix(accent, ink, 0.30),
        accent_bg=_alpha(accent, 0.12),
        accent_border=_alpha(accent, 0.35),
        # The call-to-action wears the palette's own accent. Deriving it by
        # mixing `success` into the background muddied every green into khaki
        # (everforest's #a7c080 became #889d6e).
        primary=accent,
        primary_text="#101010" if _is_light_color(accent) else "#f8fafc",
        primary_hover=_mix(accent, ink, 0.16),
        primary_pressed=_mix(accent, bg, 0.28),
        positive=success,
        positive_bg=_alpha(success, 0.14),
        warning=warning,
        warning_bg=_alpha(warning, 0.14),
        danger=error,
        danger_text=_mix(error, ink, 0.35),
        danger_bg=_alpha(error, 0.16),
        # The palettes carry one yellow/orange, so "warning" and "attention"
        # share a hue and separate by weight instead.
        attention=warning,
        attention_text=_mix(warning, ink, 0.35),
        attention_bg=_alpha(warning, 0.14),
        attention_border=_alpha(warning, 0.42),
        # The user's own messages keep an identity distinct from the accent.
        user_bg=_alpha(info, 0.20),
        user_border=_alpha(info, 0.42),
        code=CodePalette(
            background=_mix(bg, ink, 0.04),
            border=_alpha(muted, 0.25),
            inline_bg=_alpha(ink, 0.07),
            text=text,
            accent_spine=accent,
            keyword=accent,
            string=success,
            comment=muted,
            number=warning,
        ),
    )


# --------------------------------------------------------------- regeneration


def _resolve_css(css_text: str) -> Dict[str, Dict[str, str]]:
    """Resolve `theme.css` into ``{theme_id: {css_var: value}}``.

    Themes cascade: the bare ``:root`` block is the base, a grouped selector
    (the six light themes share one) applies to each id it names, and a
    per-theme block wins last — so the blocks must be applied in file order.
    """
    text = re.sub(r"/\*.*?\*/", "", css_text, flags=re.S)
    base: Dict[str, str] = {}
    themes: Dict[str, Dict[str, str]] = {}
    for match in re.finditer(r"(?P<sel>[^{}]+)\{(?P<body>[^{}]*)\}", text, re.S):
        decls = {}
        for line in match.group("body").split(";"):
            name, _, value = line.partition(":")
            if name.strip().startswith("--"):
                decls[name.strip()] = value.strip()
        if not decls:
            continue
        for selector in (s.strip() for s in match.group("sel").split(",")):
            if selector == ":root":
                base.update(decls)
                continue
            hit = re.fullmatch(r":root\.theme-([a-z0-9-]+)", selector)
            if hit:
                themes.setdefault(hit.group(1), {}).update(decls)
    return {"dark": dict(base)} | {
        tid: {**base, **vars_} for tid, vars_ in themes.items()
    }


_CSS_VARS = {
    "bg": "--bg-primary",
    "bg2": "--bg-secondary",
    "bg3": "--bg-tertiary",
    "text": "--text-primary",
    "text2": "--text-secondary",
    "muted": "--text-muted",
    "accent": "--accent",
    "success": "--success",
    "warning": "--warning",
    "error": "--error",
    "info": "--info",
}


def _refresh(css_path: str) -> int:
    """Report how the vendored palettes differ from a live ``theme.css``."""
    from pathlib import Path

    resolved = _resolve_css(Path(css_path).read_text(encoding="utf-8"))
    drift = 0
    for tid, spec in THEME_SPECS.items():
        live = resolved.get(tid)
        if live is None:
            print(f"GONE      {tid}: no longer in {css_path}")
            drift += 1
            continue
        for key, css_name in _CSS_VARS.items():
            want = str(live.get(css_name, "")).strip()
            have = str(spec.vars.get(key, "")).strip()
            if want and want != have:
                print(f"CHANGED   {tid}.{key}: {have} -> {want}")
                drift += 1
    for tid in resolved:
        if tid not in THEME_SPECS:
            print(f"NEW       {tid}: add it to THEME_SPECS")
            drift += 1
    print(f"{'drift: ' + str(drift) if drift else 'in sync'} ({len(THEME_SPECS)} vendored)")
    return 1 if drift else 0


if __name__ == "__main__":  # pragma: no cover - maintenance entry point
    import sys

    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "--refresh":
        raise SystemExit(_refresh(args[1]))
    print(__doc__)
    raise SystemExit(2)


#: Every selectable palette. Read from abstractuic's stylesheet when it can be
#: found, so palettes added upstream appear here with no code change; the
#: vendored snapshot above is the offline fallback. Assigned last because the
#: parsing helpers are defined below the loader.
THEME_SPECS: Dict[str, ThemeSpec] = _load_specs()

"""Re-colour a stylesheet from one palette to another.

Most of the app's chrome is one 22k-character stylesheet written with colour
literals rather than tokens. Rewriting all of it by hand would be a large,
risky edit for no behavioural gain — and the literals are not arbitrary: they
were derived from the app's own palette, so all but a handful are either a
token's colour or an alpha variant of one.

So the stylesheet is translated instead. Every colour in it is matched to the
token it came from (by base RGB, ignoring alpha) and re-emitted with the active
theme's colour for that token, keeping the original alpha. A colour that
matches nothing close enough is left alone, and `coverage()` reports how much
was translated so a test can hold the line.
"""

from __future__ import annotations

import re
from dataclasses import fields
from typing import Dict, List, Optional, Tuple

from .theme import CodePalette, Theme

__all__ = ["retint_stylesheet", "coverage", "parse_color", "MAX_MATCH_DISTANCE"]

#: How far a literal may sit from a token's colour and still be considered a
#: shade of it. Tuned on the real stylesheet: the near-misses are hand-nudged
#: variants 3-26 units away, while genuinely different roles are far further.
MAX_MATCH_DISTANCE = 45.0

_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}\b|rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*(?:,\s*[\d.]+\s*)?\)")

# Tokens that must never win a nearest-colour match: they are the same hue as a
# more specific token and would swallow it.
_LOW_PRIORITY = {"code.text", "code.keyword", "code.string", "code.number", "code.comment"}

#: The macOS traffic lights are system colours: they mean "close/minimise/zoom"
#: everywhere, so they must not follow the app's palette.
_FIXED_COLORS = {
    (255, 95, 87), (224, 68, 62),      # close
    (254, 188, 46), (222, 161, 35),    # minimise
    (40, 200, 64), (31, 163, 50),      # zoom
}

#: Black is structural, not semantic: shadows and rims are dark under every
#: palette, and re-tinting them turns a dark outline into a light-on-light one.
#: White is NOT excluded — `rgba(255,255,255,0.05)` IS the overlay token, and
#: it has to invert to a dark wash on a light theme.
_STRUCTURAL = {(0, 0, 0)}

#: Tokens that only ever describe a translucent wash. An OPAQUE literal is a
#: solid colour — text, a surface — and must never be answered with one of
#: these, or readable text becomes a 4% ghost.
_TRANSLUCENT_ONLY = (
    "overlay_faint", "overlay_hover", "overlay_active",
    "accent_bg", "positive_bg", "warning_bg", "danger_bg", "attention_bg",
    "user_bg", "border_subtle", "border_strong", "accent_border",
    "attention_border", "user_border", "code.inline_bg",
)


def parse_color(text: str) -> Optional[Tuple[Tuple[int, int, int], Optional[float]]]:
    """``(r, g, b), alpha`` for a hex or rgb/rgba literal; alpha None if opaque."""
    value = str(text or "").strip().lower()
    if value.startswith("#") and len(value) == 7:
        return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)), None
    match = re.match(
        r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)", value
    )
    if not match:
        return None
    rgb = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    alpha = float(match.group(4)) if match.group(4) is not None else None
    return rgb, alpha


def _token_colors(theme: Theme) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for field in fields(Theme):
        if field.name == "code":
            continue
        out[field.name] = str(getattr(theme, field.name))
    for field in fields(CodePalette):
        out[f"code.{field.name}"] = str(getattr(theme.code, field.name))
    return out


def _anchors(theme: Theme) -> List[Tuple[Tuple[int, int, int], str]]:
    """Each token's base RGB, most specific first."""
    anchors: List[Tuple[Tuple[int, int, int], str]] = []
    for name, value in _token_colors(theme).items():
        parsed = parse_color(value)
        if parsed is None:
            continue
        anchors.append((parsed[0], name))
    anchors.sort(key=lambda item: item[1] in _LOW_PRIORITY)
    return anchors


def _distance(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def _emit(color: str, alpha: Optional[float]) -> str:
    """The target colour, wearing the alpha the original literal had."""
    if alpha is None:
        return color
    parsed = parse_color(color)
    if parsed is None:
        return color
    (r, g, b), own_alpha = parsed
    # An alpha in the literal wins; a token that is itself translucent keeps
    # its own only when the literal was opaque.
    return f"rgba({r}, {g}, {b}, {alpha:.2f})"


def _translate(
    literal: str,
    *,
    anchors: List[Tuple[Tuple[int, int, int], str]],
    target_colors: Dict[str, str],
) -> Optional[str]:
    parsed = parse_color(literal)
    if parsed is None:
        return None
    rgb, alpha = parsed
    if rgb in _STRUCTURAL or rgb in _FIXED_COLORS:
        return None
    best_name = None
    best_distance = MAX_MATCH_DISTANCE
    for anchor_rgb, name in anchors:
        if alpha is None and name in _TRANSLUCENT_ONLY:
            continue
        distance = _distance(rgb, anchor_rgb)
        if distance == 0.0:
            best_name, best_distance = name, 0.0
            break
        if distance < best_distance:
            best_name, best_distance = name, distance
    if best_name is None:
        return None
    replacement = target_colors.get(best_name)
    if not replacement:
        return None
    if alpha is None:
        # An opaque literal stays opaque. Returning the token verbatim handed
        # a 4%-alpha wash to text that had been solid — 8:1 contrast became
        # 1.3:1, and it happened on the app's own default palette.
        target_rgb = parse_color(replacement)
        if target_rgb is None:
            return replacement
        (r, g, b), _ = target_rgb
        return "#%02x%02x%02x" % (r, g, b)
    return _emit(replacement, alpha)


def retint_stylesheet(qss: str, *, source: Theme, target: Theme) -> str:
    """``qss`` written against ``source``, re-coloured for ``target``."""
    if source is target or _token_colors(source) == _token_colors(target):
        # No theme selected (or the same one): the stylesheet is already right,
        # and translating it would nudge 71 literals for nothing.
        return qss
    anchors = _anchors(source)
    target_colors = _token_colors(target)

    def _replace(match: "re.Match[str]") -> str:
        literal = match.group(0)
        return _translate(literal, anchors=anchors, target_colors=target_colors) or literal

    return _COLOR_RE.sub(_replace, qss)


def coverage(qss: str, *, source: Theme) -> Tuple[int, int, List[str]]:
    """``(translated, total, untranslated)`` colour literals in ``qss``."""
    anchors = _anchors(source)
    target_colors = _token_colors(source)
    total = 0
    translated = 0
    missed: List[str] = []
    for match in _COLOR_RE.finditer(qss):
        total += 1
        if _translate(match.group(0), anchors=anchors, target_colors=target_colors):
            translated += 1
        else:
            missed.append(match.group(0))
    return translated, total, missed

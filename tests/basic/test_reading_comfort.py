"""How a reply is set, and whether you can see it at all.

The operator reported "there is simply no contrast between the message and the
background of the chat" — measured, the assistant bubble separated from the
card behind it by a luminance ratio of **1.04**, which is invisible. And the
reading rhythm was hard-coded, so nobody could adjust it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from abstractassistant.preferences import AssistantPreferences
from abstractassistant.retint import parse_color

_APP_SOURCE = Path(__file__).resolve().parents[2] / "abstractassistant" / "app.py"


def _palette_qss() -> str:
    text = _APP_SOURCE.read_text()
    start = text.rindex("def _apply_styles")
    open_at = text.index('_themed("""', start) + len('_themed("""')
    return text[open_at : text.index('"""', open_at)]


def _over(color: str, background):
    (r, g, b), alpha = parse_color(color)
    a = 1.0 if alpha is None else alpha
    return tuple(round(f * a + k * (1 - a)) for f, k in zip((r, g, b), background))


def _luminance(rgb) -> float:
    def _channel(value: float) -> float:
        value /= 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    r, g, b = (_channel(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _ratio(a, b) -> float:
    first, second = _luminance(a) + 0.05, _luminance(b) + 0.05
    return max(first, second) / min(first, second)


def _background(selector: str) -> str:
    """The background this selector ends up with — the LAST rule wins in QSS,
    and the user bubble's own rule follows the shared one."""
    qss = _palette_qss()
    found = None
    for block in re.finditer(rf"[^\n]*#{selector}\b[^{{]*\{{([^}}]*)\}}", qss):
        value = re.search(r"background:\s*([^;]+);", block.group(1))
        if value:
            found = value.group(1).strip()
    assert found, selector
    return found


@pytest.mark.basic
def test_a_message_is_visibly_separate_from_the_chat_behind_it() -> None:
    window = (11, 15, 22)
    card = _over("rgba(16, 22, 31, 0.98)", window)
    assistant = _over(_background("assistantBubble"), card)
    user = _over(_background("userBubble"), assistant)

    assistant_ratio = _ratio(assistant, card)
    user_ratio = _ratio(user, card)
    # 1.04 was the reported "no contrast". A filled panel needs a real step.
    assert assistant_ratio >= 1.25, f"assistant bubble separation {assistant_ratio:.2f}"
    assert user_ratio >= 1.25, f"user bubble separation {user_ratio:.2f}"
    # ...but a bubble is a surface, not a button: it must not shout.
    assert assistant_ratio <= 2.5, f"assistant bubble too loud: {assistant_ratio:.2f}"

    # And the two roles stay distinguishable from each other.
    assert _ratio(user, assistant) >= 1.15


@pytest.mark.basic
def test_the_reading_rhythm_is_a_preference_that_survives_a_relaunch() -> None:
    prefs = AssistantPreferences.from_dict(
        {"text_size": 17, "line_spacing": 1.8, "paragraph_spacing": 16, "bullet_spacing": 6}
    )
    assert (prefs.text_size, prefs.line_spacing) == (17, 1.8)
    assert (prefs.paragraph_spacing, prefs.bullet_spacing) == (16, 6)
    reloaded = AssistantPreferences.from_dict(prefs.to_dict())
    assert reloaded.text_size == 17 and reloaded.line_spacing == 1.8
    assert reloaded.paragraph_spacing == 16 and reloaded.bullet_spacing == 6

    # Nonsense is clamped, not obeyed: an unreadable transcript is not a
    # setting the user can get themselves into.
    wild = AssistantPreferences.from_dict(
        {"text_size": 400, "line_spacing": -3, "paragraph_spacing": 900, "bullet_spacing": "x"}
    )
    assert 10 <= wild.text_size <= 22
    assert 1.0 <= wild.line_spacing <= 2.2
    assert 0 <= wild.paragraph_spacing <= 28
    assert wild.bullet_spacing == 3

    # A fresh install reads the way the operator set it by hand: tighter
    # lines and a small paragraph gap, not the airy first cut.
    defaults = AssistantPreferences.from_dict({})
    assert (defaults.text_size, defaults.line_spacing) == (13, 1.20)
    assert (defaults.paragraph_spacing, defaults.bullet_spacing) == (3, 3)


@pytest.mark.basic
def test_the_rhythm_actually_reaches_the_rendered_reply() -> None:
    import abstractassistant.app as app_module
    from abstractassistant.utils.markdown_renderer import MarkdownRenderer

    renderer = MarkdownRenderer(theme="friendly_grayscale")
    original = app_module.TYPOGRAPHY
    try:
        app_module.TYPOGRAPHY = app_module.Typography(
            size=19, line=1.9, paragraph=21, bullet=7
        )
        html = app_module._assistant_html(renderer, "para\n\n- one\n- two")
        assert "font-size: 19px !important" in html
        assert "line-height: 1.9 !important" in html
        assert "margin: 0 0 21px 0 !important" in html
        assert "margin-bottom: 7px !important" in html
        # Headings scale with the body instead of being pinned.
        assert "font-size: 23px !important" in html  # h1 = size + 4
        # No placeholder survives into the page.
        assert "@@" not in html
    finally:
        app_module.TYPOGRAPHY = original

    html = app_module._assistant_html(renderer, "para")
    assert "font-size: 13px !important" in html and "@@" not in html


@pytest.mark.basic
def test_a_message_stays_separate_and_keeps_its_identity_in_every_theme() -> None:
    """Separation must not depend on which palette is loaded.

    An opaque bubble literal retints to whatever token is nearest, and that
    token sits a different distance from the card in every palette — the
    separation swung 1.29 to 2.18 across themes. Worse, the user bubble's base
    was ``accent``, so on the light themes it came out PINK. Both bubbles are
    now an alpha of a token, so the step is relative to the card.
    """
    from abstractassistant.retint import retint_stylesheet
    from abstractassistant.theme import DEFAULT_THEME
    from abstractassistant.ui_themes import build_theme, theme_options

    assistant_fill = _background("assistantBubble")
    user_fill = _background("userBubble")
    # An alpha of a token, not an opaque colour: that is what makes the step
    # relative to the card instead of absolute.
    for value in (assistant_fill, user_fill):
        _, alpha = parse_color(value)
        assert alpha is not None and alpha < 0.6, f"bubble fill is effectively opaque: {value}"

    spreads = []
    for theme_id, _label, _group in theme_options():
        target = build_theme(theme_id) or DEFAULT_THEME

        def _tint(color: str) -> str:
            return retint_stylesheet(color, source=DEFAULT_THEME, target=target)

        window = parse_color(_tint(DEFAULT_THEME.surface_sunken))[0]
        card = _over(_tint(DEFAULT_THEME.surface_card), window)
        assistant = _over(_tint(assistant_fill), card)
        user = _over(_tint(user_fill), card)

        assistant_ratio = _ratio(assistant, card)
        assert assistant_ratio >= 1.25, f"{theme_id}: assistant bubble separation {assistant_ratio:.2f}"
        assert assistant_ratio <= 2.5, f"{theme_id}: assistant bubble shouts at {assistant_ratio:.2f}"
        assert _ratio(user, card) >= 1.25, f"{theme_id}: user bubble vanishes into the card"
        spreads.append(assistant_ratio)

        # The user bubble is the palette's INFO colour. When it was the accent
        # it turned pink on the light themes: red-dominant, and the operator
        # never picked a pink theme.
        red, green, blue = user
        assert not (red > green + 12 and red > blue + 12), (
            f"{theme_id}: user bubble came out red/pink ({user})"
        )

    # Consistency is the point: no palette may be twice as separated as another.
    assert max(spreads) / min(spreads) <= 1.5, (
        f"separation swings {min(spreads):.2f}-{max(spreads):.2f} across themes"
    )

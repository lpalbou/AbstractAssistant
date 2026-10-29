"""Tool calls in words (kit backlog 0068): the Assistant says exactly the kit's sentences (the
shared cases, a copy of the kit's `tool_call_words.cases.json`) and its approval card never
prints JSON arguments."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from abstractassistant.core.tool_call_words import describe_tool_call, group_tool_calls

CASES = json.loads((Path(__file__).resolve().parents[2] / "abstractassistant" / "assets" / "tool_call_words.cases.json").read_text(encoding="utf-8"))


@pytest.mark.basic
@pytest.mark.parametrize("case", CASES["cases"], ids=lambda c: c["call"]["name"])
def test_the_kits_cases_read_the_same(case) -> None:
    w = describe_tool_call(case["call"])
    assert w.sentence == case["sentence"]
    if "fallback" in case:
        assert w.fallback == case["fallback"]
    else:
        assert w.fallback is None


@pytest.mark.basic
def test_the_group_line() -> None:
    assert group_tool_calls(CASES["group"]["calls"]) == CASES["group"]["text"]


@pytest.mark.basic
def test_the_approval_card_shows_words_not_json() -> None:
    import test_automations

    if test_automations._APP is None:
        test_automations._APP = test_automations._qt()  # kept alive for the whole session
    from PyQt5.QtWidgets import QLabel, QWidget

    from abstractassistant.ui.automations import _tool_call_label

    host = QWidget()
    label = _tool_call_label(CASES["cases"][1]["call"], parent=host)
    assert "{" not in label.text() and "<b>“Oct. 28, 2026” pharmaceutical FDA approval</b>" in label.text()
    assert label.accessibleName() == CASES["cases"][1]["sentence"] and label.toolTip() == "skim_websearch"
    assert isinstance(label, QLabel)

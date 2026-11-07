"""A failed run says why, in plain words (0.18.2).

Before, the conversation showed only "The run failed before it wrote a reply."
while the run's real reason (here: MTP required on a model that has none) was
reported by the gateway and dropped. A known failure is recognised by its
exception TYPE in the gateway's reason, never by the wording of its message.
"""

from __future__ import annotations

import pytest

from abstractassistant.core.run_failure import (
    GENERIC_FAILURE,
    error_type_of,
    explain_run_failure,
    failure_tooltip,
)

SPECULATION = (
    "Effect failed after 3 attempts: SpeculationUnavailableError: The openai-compatible provider "
    "has no native MTP adapter (speculation.require_acceleration=True)"
)


@pytest.mark.basic
def test_a_known_type_becomes_a_plain_sentence_with_the_action() -> None:
    failure = explain_run_failure(SPECULATION)
    assert failure.error_type == "SpeculationUnavailableError"
    assert "MTP" in failure.text and "Settings" in failure.text and "Off" in failure.text
    assert "SpeculationUnavailableError" not in failure.text  # no exception names on screen
    assert failure.reason == SPECULATION
    assert SPECULATION in failure_tooltip(failure)


@pytest.mark.basic
def test_the_type_is_matched_exactly_never_by_the_words_of_the_message() -> None:
    # The same words without the type: not recognised (no pattern over prose).
    assert error_type_of("The provider has no native MTP adapter (speculation.require_acceleration=True)") == ""
    # A type whose name merely CONTAINS the known one is a different type.
    assert error_type_of("Effect failed: NotSpeculationUnavailableErrorAtAll: x") == ""


@pytest.mark.basic
def test_an_unknown_failure_is_a_short_line_and_keeps_the_raw_reason() -> None:
    failure = explain_run_failure("Effect failed after 3 attempts: ProviderAPIError: upstream 502")
    assert failure.text == GENERIC_FAILURE
    assert failure.error_type == ""
    assert "upstream 502" in failure_tooltip(failure)
    empty = explain_run_failure("")
    assert empty.text == GENERIC_FAILURE and failure_tooltip(empty) == GENERIC_FAILURE


def _palette():
    pytest.importorskip("PyQt5.QtWidgets")
    from PyQt5.QtWidgets import QApplication

    import abstractassistant.app as app_module

    QApplication.instance() or QApplication([])
    palette = app_module.AssistantPalette.__new__(app_module.AssistantPalette)
    shown: list = []
    palette._set_status = lambda *a, **kw: None
    palette._set_history_status = lambda text="", **kw: shown.append((text, kw))
    palette._refresh_tray_feedback = lambda *a, **k: None
    palette._clear_run_activity = lambda: None
    palette._feed_activity = lambda payload: None
    palette._invalidate_session_digests = lambda: None
    palette._show_thinking_indicator = lambda: False
    palette.refresh_history = lambda *a, **k: None
    palette._set_banner = lambda *a, **k: None
    palette._finish_activity = lambda outcome: None
    palette._set_send_button_busy = lambda busy: None
    palette._discard_live_replies = lambda: None
    palette.sender = lambda: None
    palette._worker = None
    return app_module, palette, shown


@pytest.mark.basic
@pytest.mark.parametrize(
    "reason,expected",
    [
        (SPECULATION, explain_run_failure(SPECULATION).text),
        ("Effect failed after 3 attempts: ProviderAPIError: upstream 502", GENERIC_FAILURE),
    ],
)
def test_the_conversation_shows_the_runs_own_reason(reason, expected) -> None:
    app_module, palette, shown = _palette()
    # What the worker emits for a failed run: the step's (or the summary's) error, then the status.
    app_module.AssistantPalette._on_worker_event(palette, {"type": "error", "error": reason, "run_id": "run-1"})
    app_module.AssistantPalette._on_worker_event(palette, {"type": "status", "status": "failed"})
    palette._run_has_final_output = False
    app_module.AssistantPalette._on_worker_finished(palette)
    text, kw = shown[-1]
    assert text == expected
    assert kw.get("tone") == "error"
    assert reason in kw.get("tooltip", "")  # the gateway's own words, one hover away


"""The global summon hotkey registers and matches what pynput really reports.

Through 0.7.0 the default `cmd+shift+space` never registered: the sequence was
normalised to `<cmd>+<shift>+space` and `HotKey.parse` raised ValueError('space').
Even when parsed, the listener fed RAW keys to the HotKey (Key.space, Key.cmd_r),
which never equal the parsed ones (KeyCode(vk=49), Key.cmd), so the combination
could not fire. No listener is ever started here: pynput's Listener is replaced
by a recorder that keeps pynput's own `canonical`.
"""

from __future__ import annotations

import logging

import pytest

keyboard = pytest.importorskip("pynput.keyboard")
from pynput.keyboard import Key, KeyCode  # noqa: E402

from abstractassistant import hotkey as hotkey_module  # noqa: E402
from abstractassistant.hotkey import GlobalHotkeyManager, _normalize_sequence  # noqa: E402


class _RecordingListener:
    """Stands in for pynput's Listener: records the callbacks, starts nothing."""

    instances: list["_RecordingListener"] = []
    canonical = keyboard.Listener.canonical  # pynput's own normalisation

    def __init__(self, on_press=None, on_release=None, **_kwargs) -> None:
        self.on_press = on_press
        self.on_release = on_release
        self.daemon = False
        self.started = False
        self.stopped = False
        _RecordingListener.instances.append(self)

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


@pytest.fixture
def recorder(monkeypatch):
    _RecordingListener.instances = []
    monkeypatch.setattr(keyboard, "Listener", _RecordingListener)
    return _RecordingListener


@pytest.mark.basic
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("cmd+shift+space", "<cmd>+<shift>+<space>"),
        ("", "<cmd>+<shift>+<space>"),
        ("Command + Option + Return", "<cmd>+<alt>+<enter>"),
        ("ctrl+shift+a", "<ctrl>+<shift>+a"),
        ("cmd+f5", "<cmd>+<f5>"),
    ],
)
def test_sequences_normalise_to_what_pynput_parses(raw, expected) -> None:
    assert _normalize_sequence(raw) == expected
    keyboard.HotKey.parse(expected)  # raises ValueError on a bare named key


@pytest.mark.basic
def test_default_summon_combination_fires_on_the_keys_macos_reports(recorder, monkeypatch) -> None:
    monkeypatch.setattr(hotkey_module, "_macos_input_trusted", lambda: True)
    fired: list[int] = []
    manager = GlobalHotkeyManager()
    assert manager.start(sequence="cmd+shift+space", callback=lambda: fired.append(1)) is True
    assert manager.registered == "<cmd>+<shift>+<space>" and manager.error == ""
    listener = recorder.instances[-1]
    assert listener.started

    # What pynput's darwin backend reports for right-Cmd + Shift + Space.
    for key in (Key.cmd_r, Key.shift, Key.space):
        listener.on_press(key)
    assert fired == [1]
    for key in (Key.space, Key.shift, Key.cmd_r):
        listener.on_release(key)

    # Once the chord is released, a plain Space (typing in any app) never fires.
    listener.on_press(Key.space)
    listener.on_release(Key.space)
    listener.on_press(KeyCode.from_char(" "))
    assert fired == [1]

    # Left Cmd works the same, and so does a second summon.
    for key in (Key.cmd, Key.shift_r, Key.space):
        listener.on_press(key)
    assert fired == [1, 1]

    manager.stop()
    assert listener.stopped and manager.registered == ""


@pytest.mark.basic
def test_untrusted_macos_process_starts_no_listener_and_says_why(recorder, monkeypatch, caplog) -> None:
    monkeypatch.setattr(hotkey_module, "_macos_input_trusted", lambda: False)
    manager = GlobalHotkeyManager()
    with caplog.at_level(logging.WARNING, logger="abstractassistant.hotkey"):
        assert manager.start(sequence="cmd+shift+space", callback=lambda: None) is False
    assert recorder.instances == []
    assert manager.registered == ""
    assert "Accessibility" in manager.error and manager.error.startswith("#FALLBACK")
    assert manager.error in caplog.text


@pytest.mark.basic
def test_an_invalid_sequence_fails_loudly(recorder, monkeypatch, caplog) -> None:
    monkeypatch.setattr(hotkey_module, "_macos_input_trusted", lambda: True)
    manager = GlobalHotkeyManager()
    with caplog.at_level(logging.WARNING, logger="abstractassistant.hotkey"):
        assert manager.start(sequence="cmd+shift+notakey", callback=lambda: None) is False
    assert recorder.instances == []
    assert "not a valid key combination" in manager.error
    assert manager.error in caplog.text

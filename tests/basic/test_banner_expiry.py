"""Ephemeral speech notices expire without dismissing a later error or wait."""
from types import SimpleNamespace
from abstractassistant.app import AssistantPalette
import abstractassistant.app as app_module


def test_speech_notice_expiry_is_scoped_to_its_revision(monkeypatch):
    timers = []
    monkeypatch.setattr(app_module.QTimer, 'singleShot', lambda ms, callback: timers.append((ms, callback)))
    label = SimpleNamespace(clear=lambda:None, setText=lambda text:None,
                            setMinimumHeight=lambda n:None, setMaximumHeight=lambda n:None,
                            hide=lambda:None, show=lambda:None, setProperty=lambda *args:None)
    host = SimpleNamespace(banner_label=label, _BANNER_TONE_ALIASES={},
                           _refresh_widget_style=lambda label:None)
    host._state = lambda name, default=None: getattr(host, name, default)
    cleared = []
    host._clear_banner = cleared.append
    show = lambda text, key, tone='info': AssistantPalette._set_banner(host, text, tone, key=key)
    show('Muted output', 'speech', 'warning')
    assert timers[0][0] == 5000
    show('Muted output', 'speech', 'warning')  # Same text is a new notification.
    timers[0][1]()
    assert cleared == []
    timers[1][1]()
    assert cleared == ['speech']
    cleared.clear()
    show('Speaking', 'speech')
    show('Approval required', 'wait', 'warning')
    timers[-1][1]()
    assert cleared == []
    assert len(timers) == 3  # Persistent waits do not expire.

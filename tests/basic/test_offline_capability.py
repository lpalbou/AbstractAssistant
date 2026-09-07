"""AbstractFramework runs fully offline; the desktop app must not break that.

"Offline" here means no internet — the gateway itself is local. So the rule is
narrower and stricter than "handles a network error": nothing the user does to
read, pick or configure may need a remote host, and the one enrichment call that
does talk to the gateway must fail fast, once, and change nothing when it cannot.
"""

from __future__ import annotations

import re
import threading
import warnings
from pathlib import Path

import pytest

from abstractassistant.core.llm_manager import LLMManager
from abstractassistant.core.session_store import SessionSnapshot

_SOURCE = Path(__file__).resolve().parents[2] / "abstractassistant"

# Modules that must never reach the network: everything behind reading a
# session, picking a theme, or rendering a reply.
_LOCAL_ONLY = (
    "ui_themes.py",
    "theme.py",
    "preferences.py",
    "core/session_digest.py",
    "core/session_index.py",
    "core/session_store.py",
    "ui/session_switcher.py",
    "ui/styles.py",
)

_NETWORK = re.compile(
    r"\b(urlopen|urllib\.request|requests\.(get|post|put|delete)|httpx\.|socket\.(create_connection|socket))\b"
)


@pytest.mark.basic
def test_reading_picking_and_rendering_never_touch_the_network() -> None:
    offenders = []
    for name in _LOCAL_ONLY:
        path = _SOURCE / name
        if not path.exists():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _NETWORK.search(line) and not line.lstrip().startswith("#"):
                offenders.append(f"{name}:{number}: {line.strip()}")
    assert offenders == [], "these must work with no network:\n" + "\n".join(offenders)


@pytest.mark.basic
def test_themes_load_from_disk_with_no_gateway_and_no_internet() -> None:
    from abstractassistant.ui_themes import build_theme, theme_options

    options = theme_options()
    assert len(options) > 1
    # Every palette resolves to real colours from local data alone.
    for theme_id, _label, _group in options:
        theme = build_theme(theme_id)
        assert theme is None or theme.accent.startswith(("#", "rgb"))


@pytest.mark.basic
def test_the_markdown_css_pulls_nothing_from_a_cdn() -> None:
    """A reply must render identically with the network unplugged."""
    from abstractassistant.utils.markdown_renderer import MarkdownRenderer

    css = MarkdownRenderer(theme="friendly_grayscale")._get_base_css()
    assert "@import" not in css
    assert "http://" not in css and "https://" not in css
    assert "fonts.googleapis" not in css


def _manager(*, client) -> LLMManager:
    manager = LLMManager.__new__(LLMManager)
    manager._snapshot_lock = threading.RLock()
    manager._gateway_snapshot = SessionSnapshot(
        session_id="s1",
        actor_id="a1",
        messages=[{"message_id": "m1", "role": "user", "content": "look at this"}],
        last_run_id="run_1",
        workspace_root="/tmp/ws",
    )
    manager._ensure_gateway_snapshot = lambda: manager._gateway_snapshot
    manager.saved = []
    manager._save_gateway_snapshot = lambda snap: manager.saved.append(snap)
    manager.gateway_client = lambda: client
    return manager


@pytest.mark.basic
def test_the_attachment_backfill_is_bounded_and_harmless_when_unreachable() -> None:
    """It enriches a transcript that already renders, so an unreachable gateway
    must cost one bounded call and change nothing."""
    asked = {}

    class _Unreachable:
        def get_run_history_bundle(self, **kw):
            asked.update(kw)
            raise OSError("[Errno 61] Connection refused")

    manager = _manager(client=_Unreachable())
    with pytest.warns(UserWarning):
        assert manager.backfill_attachments_from_gateway() == 0

    # It never rewrites the transcript on failure...
    assert manager.saved == []
    assert manager._gateway_snapshot.messages[0].get("metadata") in (None, {})
    # ...and it does not hold a socket for the client's full default timeout.
    assert 0 < float(asked.get("timeout_s") or 0) <= 10.0


@pytest.mark.basic
def test_only_one_backfill_runs_at_a_time() -> None:
    """Switching sessions with an unreachable gateway must not leave one
    waiting thread per switch."""
    import abstractassistant.app as app_module

    palette = app_module.AssistantPalette.__new__(app_module.AssistantPalette)
    started = []
    release = threading.Event()

    class _Controller:
        def backfill_session_attachments(self):
            started.append(1)
            release.wait(timeout=5)
            return 0

    palette._controller = _Controller()
    palette.session_attachments_restored = type(
        "S", (), {"emit": staticmethod(lambda *a: None)}
    )()

    try:
        for _ in range(5):  # five session switches while the first call hangs
            app_module.AssistantPalette._backfill_session_attachments(palette)
        assert len(started) == 1, f"{len(started)} concurrent gateway calls"
    finally:
        release.set()

    # Once it finishes, the next switch is allowed to try again.
    for _ in range(50):
        if not palette._state("_attachment_backfill_running", False):
            break
        threading.Event().wait(0.02)
    app_module.AssistantPalette._backfill_session_attachments(palette)
    assert len(started) == 2
    release.set()


@pytest.mark.basic
def test_a_session_still_reads_when_the_backfill_finds_nothing() -> None:
    """The local transcript is the thing on screen; the gateway only adds to it."""

    class _Empty:
        def get_run_history_bundle(self, **_kw):
            return {"session": {"turns": []}}

    manager = _manager(client=_Empty())
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # no warning is expected on success
        assert manager.backfill_attachments_from_gateway() == 0
    assert manager.saved == []
    assert manager._gateway_snapshot.messages[0]["content"] == "look at this"

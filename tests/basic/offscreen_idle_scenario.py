"""Child-process scenario for test_offscreen_harness_idle.py (not collected by
the suite: the file name does not start with ``test_``).

Test 1 builds the REAL palette offscreen, opens its session switcher, clicks an
automation card's Active switch (which arms the switcher's pending-command
QTimer, shortened here), does the same in a standalone switcher (the
test_switcher_tabs shape), and ends the way every GUI test ends:
``window.deleteLater()`` then dropping the last reference. Test 2 idles past the
timer's deadline pumping Qt events, then checks that nothing the first test
handed to ``deleteLater()`` is still alive.

Without the harness's deferred-delete flush (tests/conftest.py) the C++ widget
tree survives its Python wrapper and the standalone switcher's timer fires into
a freed lambda: the process segfaults during test 2 (and the palette, whose
wrapper something still references, is reported as an orphan).
"""

from __future__ import annotations

import copy
import gc
import json
import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSTRAY_BACKEND", "dummy")

pytest.importorskip("PyQt5.QtWidgets")

from PyQt5.QtWidgets import QApplication  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "automations"
PENDING_MS = 1_000
IDLE_S = float(os.environ.get("ABSTRACTASSISTANT_HARNESS_IDLE_S", "6"))


_APP = None


def _app() -> QApplication:
    # Held for the whole process, as the suite's modules do: a QApplication whose
    # last Python reference goes away is deleted with every widget, which would
    # hide the very orphans this scenario is about.
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_palette_with_a_pending_automation_command_is_handed_to_delete_later(tmp_path, monkeypatch) -> None:
    import abstractassistant.app as app_module
    from abstractassistant.config import Config
    from abstractassistant.controller import AssistantController
    from abstractassistant.ui import session_switcher as switcher_module

    app = _app()
    # The harness (conftest) already did this; assert it rather than redo it.
    assert app_module._MAC_NATIVE_TRAFFIC_LIGHTS_AVAILABLE is False
    monkeypatch.setattr(switcher_module.SessionSwitcher, "PENDING_TIMEOUT_MS", PENDING_MS)

    controller = AssistantController(config=Config(), data_dir=tmp_path / "data")
    controller.update_preferences(hotkey_enabled=False)
    monkeypatch.setattr(controller, "backfill_session_attachments", lambda: 0)
    window = app_module.AssistantPalette(controller=controller)
    window.resize(650, 700)
    window.show()
    app.processEvents()
    # The gateway "thinks" forever: the card stays pending, the timer armed.
    window._automations.command = lambda aid, control, done: None

    window._open_session_switcher()
    switcher = window._session_switcher
    summaries = json.loads((FIXTURES / "list.json").read_text(encoding="utf-8"))["items"]
    switcher.set_automations(copy.deepcopy(summaries), available=True)
    switcher.set_tab("automations")
    card = next(r for r in switcher.automation_tab_rows if r.active_switch.is_actionable())
    card.active_switch.click()
    assert switcher.is_pending(card.automation_id)

    # The same card in a standalone switcher, as test_switcher_tabs builds them:
    # nothing else references it, so its wrapper (and the timer's lambda) is
    # freed below while the C++ side waits for a deletion that never runs.
    from abstractassistant.ui.session_switcher import SessionSwitcher

    alone = SessionSwitcher()
    alone.set_automations(copy.deepcopy(summaries), available=True)
    alone.set_tab("automations")
    alone_card = next(r for r in alone.automation_tab_rows if r.active_switch.is_actionable())
    alone_card.active_switch.click()
    assert alone.is_pending(alone_card.automation_id)

    window.close()
    window.deleteLater()
    alone.deleteLater()
    app.processEvents()
    del window, switcher, card, alone, alone_card
    gc.collect()


def test_idle_past_the_pending_timer_does_not_crash() -> None:
    app = _app()
    deadline = time.time() + IDLE_S
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)
    print(f"IDLE-SURVIVED {IDLE_S:.0f}s", flush=True)
    names = sorted({w.metaObject().className() for w in app.allWidgets()})
    assert names == [], f"widgets handed to deleteLater() are still alive: {names}"

"""
Pytest configuration to ensure local package imports.
"""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Prefer sibling packages in the monorepo when running tests from the repo root.
REPO_ROOT = ROOT.parent
VOICE_PKG_ROOT = REPO_ROOT / "abstractvoice"
if VOICE_PKG_ROOT.exists() and str(VOICE_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(VOICE_PKG_ROOT))
RUNTIME_SRC_ROOT = REPO_ROOT / "abstractruntime" / "src"
if RUNTIME_SRC_ROOT.exists() and str(RUNTIME_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC_ROOT))
# The sibling runtime tracks the sibling core (it imports symbols the released
# wheel does not carry yet). Preferring one sibling but not the other pairs a
# new runtime with an old installed core and every GUI/voice test module fails
# to import, so take abstractcore from the monorepo too when it is checked out.
CORE_PKG_ROOT = REPO_ROOT / "abstractcore"
if (CORE_PKG_ROOT / "abstractcore").is_dir() and str(CORE_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_PKG_ROOT))


# ---------------------------------------------------------------------------
# NO TEST MAY REACH A REAL GATEWAY (2026-09-17).
#
# Several GUI tests build a real `AssistantPalette` around `AssistantController(
# config=Config())`. `Config()` reads the gateway URL and token from the ENVIRONMENT, and
# a palette's bootstrap thread connects and RECONCILES THE MANAGED WORKFLOW — it PUTs the
# flow, publishes it and promotes it as the catalog default. On a developer machine with
# `ABSTRACTGATEWAY_AUTH_TOKEN` exported and a gateway on 127.0.0.1:8080, running this
# suite therefore rewrote the LIVE gateway's assistant workflow with whatever the working
# tree contained. Each publish makes the gateway rebuild its host — reloading a 15 GB
# model on its event loop (40-60 s of "unhealthy") and dropping every in-process prompt
# cache — and the installed app then published its own version back on its next launch.
# Measured in the gateway audit log: four such rebuilds in 17 minutes, two of them from
# `pytest tests/basic`.
#
# Two layers, because the first one is only a convention:
#   1. the environment is scrubbed before anything imports `abstractassistant.config`,
#      and the URL points at the discard port (connection refused, immediately);
#   2. sockets refuse the default gateway port and every non-loopback host outright.
# ---------------------------------------------------------------------------
import os  # noqa: E402
import socket  # noqa: E402

for _name in ("ABSTRACTGATEWAY_AUTH_TOKEN", "ABSTRACTFLOW_GATEWAY_AUTH_TOKEN", "ABSTRACTFLOW_GATEWAY_URL"):
    os.environ.pop(_name, None)
os.environ["ABSTRACTGATEWAY_URL"] = "http://127.0.0.1:9"
# The default URL is this computer's gateway (config._local_gateway_url reads its data
# dir's records), which may be a live one on another port: point it at an empty dir.
import tempfile  # noqa: E402

os.environ["ABSTRACTGATEWAY_DATA_DIR"] = tempfile.mkdtemp(prefix="abstractassistant-tests-gateway-data-")

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
_FORBIDDEN_PORTS = {8080}
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


def _refuse_real_gateways(address) -> None:
    if not isinstance(address, tuple) or len(address) < 2:
        return  # AF_UNIX and friends
    host, port = str(address[0]), int(address[1])
    if host not in _LOOPBACK_HOSTS or port in _FORBIDDEN_PORTS:
        raise AssertionError(
            f"a test tried to open a network connection to {host}:{port}. Tests must use fake "
            "gateways; a real one gets its managed workflow republished (see tests/conftest.py)."
        )


def _guarded_connect(self, address):
    _refuse_real_gateways(address)
    return _real_connect(self, address)


def _guarded_connect_ex(self, address):
    _refuse_real_gateways(address)
    return _real_connect_ex(self, address)


socket.socket.connect = _guarded_connect  # type: ignore[method-assign]
socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# OFFSCREEN QT HARNESS (2026-10-07, root backlog 1002 item 6).
#
# The suite used to segfault in whatever test happened to pump Qt events ~30 s
# after an automation card's Active switch was clicked (repro: test_switcher_tabs
# or test_automations followed by any idle loop). Root cause, measured:
#
#   * PyQt5 declares `QObject.deleteLater()` /TransferThis/: the call hands the
#     object's ownership to C++, so the Python wrapper no longer deletes it.
#   * Tests end with `widget.deleteLater(); app.processEvents()`, but no Qt event
#     loop ever runs in this process, and `processEvents()` at loop level 0 does
#     not dispatch DeferredDelete events. The C++ widget tree is never deleted.
#   * When the test's last reference goes, the garbage collector frees the
#     wrapper together with the Python lambdas connected to the tree's signals
#     (they form a cycle through `self`), while the C++ QTimers and connections
#     live on. SessionSwitcher's 30 s pending-command QTimer then fires into a
#     freed lambda: "Fatal Python error: Segmentation fault ... session_switcher.py,
#     line ??? in <lambda>".
#
# The fix is the harness's: after every test, actually run the deferred deletes
# (what the app's event loop does for a real user), so a widget a test handed to
# deleteLater is gone, with its timers, before the next test starts. The same
# fixture keeps the two native integrations that crash or leak offscreen out of
# every test: the AppKit traffic-light bridge (no NSWindow behind an offscreen
# widget) and the pynput global-hotkey listener (a real keyboard hook thread).
# ---------------------------------------------------------------------------
import pytest  # noqa: E402


def flush_deferred_deletes(rounds: int = 3) -> None:
    """Dispatch pending `deleteLater()` deletions the way an event loop would.

    Deleting an object may post further deletions (children, timers), so a few
    rounds; `processEvents()` lets queued signals land before each round."""
    try:
        from PyQt5.QtCore import QCoreApplication, QEvent
    except Exception:
        return
    app = QCoreApplication.instance()
    if app is None:
        return
    for _ in range(rounds):
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def _quiet_hotkey_start(self, *, sequence, callback):  # noqa: ARG001
    self.stop()
    self._error = ""
    return False


# Modules that test the hotkey manager itself (with a fake pynput).
_REAL_HOTKEY_MODULES = {"test_hotkey"}


@pytest.fixture(autouse=True)
def _offscreen_qt_harness(request, monkeypatch):
    try:
        import abstractassistant.app as app_module
    except Exception:
        app_module = None  # no PyQt5 in this environment: nothing Qt to guard
    if app_module is not None:
        monkeypatch.setattr(app_module, "_MAC_NATIVE_TRAFFIC_LIGHTS_AVAILABLE", False)
        module_name = getattr(request.module, "__name__", "").rsplit(".", 1)[-1]
        if module_name not in _REAL_HOTKEY_MODULES:
            from abstractassistant.hotkey import GlobalHotkeyManager

            monkeypatch.setattr(GlobalHotkeyManager, "start", _quiet_hotkey_start)
    yield
    flush_deferred_deletes()


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    flush_deferred_deletes()

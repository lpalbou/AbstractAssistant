"""The offscreen test harness survives an idle event loop (root backlog 1002
item 6).

The scenario runs in a child pytest process so that a regression shows up as
this test FAILING with the child's crash, instead of the whole suite dying with
a segfault in an unrelated later test. See tests/conftest.py ("OFFSCREEN QT
HARNESS") for the root cause and tests/basic/offscreen_idle_scenario.py for the
scenario itself: the real palette, a pending automation command, deleteLater,
then an idle period longer than the pending timer.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("PyQt5.QtWidgets")

SCENARIO = Path(__file__).with_name("offscreen_idle_scenario.py")


@pytest.mark.basic
def test_the_harness_survives_idle_after_a_palette_with_a_pending_command_is_deleted(tmp_path) -> None:
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYSTRAY_BACKEND"] = "dummy"
    env["PYTHONFAULTHANDLER"] = "1"
    env["HOME"] = str(tmp_path / "home")  # the child never touches the real HOME
    (tmp_path / "home").mkdir()
    for name in list(env):
        if name.startswith(("AGORA_", "ABSTRACTGATEWAY_AUTH", "ABSTRACTGATEWAY_ADMIN")):
            env.pop(name)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-s", "-p", "no:cacheprovider", str(SCENARIO)],
        cwd=str(SCENARIO.parents[2]),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    output = proc.stdout + proc.stderr
    crash = output.find("Fatal Python error")
    excerpt = output[crash : crash + 1500] if crash >= 0 else output[-4000:]
    assert proc.returncode == 0, f"child exit {proc.returncode}:\n{excerpt}"
    assert "IDLE-SURVIVED" in output and "2 passed" in output, output[-4000:]

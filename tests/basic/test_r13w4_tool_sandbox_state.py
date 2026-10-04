"""Round 13 (R13.4): the Tools cards show the gateway's command-sandbox state.

The gateway marks its process-spawning tools on GET /discovery/tools with
``sandboxed`` + ``sandbox`` (the state text) and reports the host state as
``command_sandbox`` (``sentence`` = the explanation). The Assistant shows the
row's ``sandbox`` text verbatim as a state chip on the card, with the gateway's
sentence as its tooltip, and nothing on a tool the gateway does not mark.

The payload is a real answer of a scratch gateway (fixtures/
discovery_tools_command_sandbox.json); the refused and flag states use the
gateway's own strings (abstractgateway.command_sandbox.tool_sandbox_fields /
_state_locked).
"""

from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import test_settings_pages as tsp

from abstractassistant.controller import AssistantController

LIVE = json.loads((Path(__file__).parent / "fixtures" / "discovery_tools_command_sandbox.json").read_text(encoding="utf-8"))
SPAWNING = ("execute_command", "local_helper_start", "shell_exec")

REFUSED_ROW = "Refused: no command sandbox on this host"
REFUSED_SENTENCE = (
    "Commands are refused because this host has no command sandbox (macOS sandbox-exec, Linux bubblewrap or "
    "Landlock); restart the gateway with --unsandboxed-commands to allow them unsandboxed."
)
FLAG_ROW = "Not sandboxed: unsandboxed commands allowed (flag)"
FLAG_SENTENCE = (
    "This host has no command sandbox and the gateway was started with --unsandboxed-commands: commands run "
    "with the gateway's own file access (their environment is still scrubbed)."
)


def _payload(state: str = "sandboxed") -> dict:
    payload = copy.deepcopy(LIVE)
    if state == "refused":
        row, sentence, sandboxed = REFUSED_ROW, REFUSED_SENTENCE, False
        payload["command_sandbox"].update(state="refused", kind="none", line="Commands refused: no sandbox on this host", sentence=sentence)
    elif state == "unsandboxed":
        row, sentence, sandboxed = FLAG_ROW, FLAG_SENTENCE, False
        payload["command_sandbox"].update(state="unsandboxed", kind="none", line="Unsandboxed commands allowed (flag)", sentence=sentence, unsandboxed_commands_allowed=True)
    else:
        return payload
    for item in payload["items"]:
        if "sandboxed" in item:
            item["sandboxed"], item["sandbox"] = sandboxed, row
    return payload


def _controller(payload: dict) -> AssistantController:
    c = object.__new__(AssistantController)
    c._cache_ttl_s = 20.0
    c._cache_epoch = 0
    c._tool_inventory_cache = None
    c._tool_inventory_cache_at = 0.0
    c._cache_lock = threading.RLock()
    c.gateway = SimpleNamespace(discovery_tools=lambda: copy.deepcopy(payload))
    c.preferences = SimpleNamespace(tool_preferences={})
    c.session_tool_auto_approval_active = lambda **_: False  # type: ignore[method-assign]
    return c


class _Ctl(tsp._Controller):
    def __init__(self, payload: dict):
        super().__init__()
        self._inventory = _controller(payload).tool_inventory()

    def tool_inventory(self):
        return copy.deepcopy(self._inventory)


def _tools_page(payload: dict):
    dlg, _ = tsp._dialog(_Ctl(payload))
    dlg.show_section("tools")
    page = dlg.page_tools
    page.refresh()
    return dlg, page


@pytest.mark.basic
def test_inventory_carries_the_gateway_sandbox_fields_untouched() -> None:
    inv = _controller(LIVE).tool_inventory()
    by_name = {item["name"]: item for item in inv["items"]}
    for name in SPAWNING:
        assert by_name[name]["sandboxed"] is True
        assert by_name[name]["sandbox"] == "Sandboxed to this run's workspaces"
    assert "sandboxed" not in by_name["read_file"] and "sandbox" not in by_name["read_file"]
    assert inv["command_sandbox"]["state"] == "sandboxed"
    assert inv["command_sandbox"]["sentence"] == LIVE["command_sandbox"]["sentence"]


@pytest.mark.basic
@pytest.mark.parametrize(
    "state,label,tone",
    [
        ("sandboxed", "Sandboxed to this run's workspaces", "success"),
        ("refused", REFUSED_ROW, "warning"),
        ("unsandboxed", FLAG_ROW, "danger"),
    ],
)
def test_spawning_tool_cards_show_the_gateway_state_with_its_sentence(state, label, tone) -> None:
    payload = _payload(state)
    dlg, page = _tools_page(payload)
    assert set(page._sandbox_chips) == set(SPAWNING)
    for name in SPAWNING:
        chip = page._sandbox_chips[name]
        assert chip.text() == label  # verbatim, never rewritten
        assert chip.toolTip() == payload["command_sandbox"]["sentence"]
        assert chip.property("tone") == tone
        assert chip.accessibleName() == f"Command sandbox: {label}"
        # The chip sits on the tool's own card row.
        assert page._rows[name]["row"].isAncestorOf(chip)
    dlg.close()


@pytest.mark.basic
def test_a_tool_the_gateway_does_not_mark_gets_no_state() -> None:
    payload = _payload("sandboxed")
    for item in payload["items"]:
        if item["name"] == "local_helper_start":
            item.pop("sandboxed")
            item.pop("sandbox")
    dlg, page = _tools_page(payload)
    assert "local_helper_start" not in page._sandbox_chips
    assert "read_file" not in page._sandbox_chips and "write_file" not in page._sandbox_chips
    assert set(page._sandbox_chips) == {"execute_command", "shell_exec"}
    dlg.close()


@pytest.mark.basic
def test_no_client_side_sandbox_wording_in_the_package() -> None:
    """The state text comes from the gateway: the package never spells it."""
    pkg = Path(__file__).resolve().parents[2] / "abstractassistant"
    for path in pkg.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for phrase in ("Sandboxed to this run", "no command sandbox on this host", "unsandboxed commands allowed"):
            assert phrase not in text, f"{path.name} spells the gateway's sandbox state: {phrase!r}"


@pytest.mark.basic
def test_a_long_gateway_state_wraps_on_the_card_and_short_ones_stay_one_line() -> None:
    partial = "Sandboxed to this run's workspaces (Deny everything, allow listed workspaces); otherwise commands refused"
    payload = _payload("sandboxed")
    for item in payload["items"]:
        if item["name"] == "shell_exec":
            item["sandbox"] = partial
    dlg, page = _tools_page(payload)
    assert page._sandbox_chips["shell_exec"].text() == partial
    assert page._sandbox_chips["shell_exec"].wordWrap()
    assert not page._sandbox_chips["execute_command"].wordWrap()
    dlg.close()

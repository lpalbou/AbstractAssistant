"""The macOS keyboard-permission check behind the global hotkey.

`hotkey._macos_input_trusted` asks Accessibility (`HIServices.AXIsProcessTrusted`,
from the declared macOS dependency pyobjc-framework-ApplicationServices). It must
never read a failure as "trusted". No pynput here, so this runs on every CI runner.
"""

from __future__ import annotations

import pytest

from abstractassistant import hotkey as hotkey_module


class _FakeHIServices:
    def __init__(self, trusted=None, error=None) -> None:
        self._trusted, self._error = trusted, error

    def AXIsProcessTrusted(self):  # noqa: N802 - pyobjc name
        if self._error is not None:
            raise self._error
        return self._trusted


@pytest.mark.basic
@pytest.mark.parametrize("trusted", [True, False])
def test_macos_trust_is_what_accessibility_says(monkeypatch, trusted) -> None:
    monkeypatch.setattr(hotkey_module.sys, "platform", "darwin")
    monkeypatch.setitem(hotkey_module.sys.modules, "HIServices", _FakeHIServices(trusted=trusted))
    assert hotkey_module._macos_input_trusted() is trusted


@pytest.mark.basic
def test_macos_trust_check_errors_are_not_read_as_trusted(monkeypatch) -> None:
    monkeypatch.setattr(hotkey_module.sys, "platform", "darwin")
    monkeypatch.setitem(
        hotkey_module.sys.modules, "HIServices", _FakeHIServices(error=RuntimeError("AX query failed (test)"))
    )
    with pytest.raises(RuntimeError, match="AX query failed"):
        hotkey_module._macos_input_trusted()


@pytest.mark.basic
def test_macos_trust_check_without_its_declared_dependency_fails_loudly(monkeypatch) -> None:
    monkeypatch.setattr(hotkey_module.sys, "platform", "darwin")
    monkeypatch.setitem(hotkey_module.sys.modules, "HIServices", None)
    with pytest.raises(ImportError):
        hotkey_module._macos_input_trusted()

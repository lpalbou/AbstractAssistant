"""About shows the framework identity (contract B) and the tray opens it.

Every row comes from ``abstractcore.utils.identity`` (the vendored copy of
AbstractFramework's ``identity/abstractframework.json``): nothing about who
wrote the app or where it lives is typed into the assistant.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSTRAY_BACKEND", "dummy")

pytest.importorskip("PyQt5.QtWidgets")

from abstractcore.utils.identity import about_fields, app_identity  # noqa: E402

EXPECTED_LABELS = [
    "Application",
    "Part of",
    "Author",
    "Copyright",
    "Website",
    "Source",
    "Documentation",
    "Report an issue",
    "Give feedback",
    "Contact",
]


@pytest.mark.basic
def test_about_page_shows_every_identity_row_with_links() -> None:
    from test_settings_pages import _dialog

    dlg, _ctl = _dialog()
    dlg.show_section("about")
    page = dlg.page_about
    page.refresh()
    assert list(page.identity_labels) == EXPECTED_LABELS

    from abstractassistant.cli import _package_version

    identity = app_identity("abstractassistant", version=_package_version())
    facts = dict(about_fields(identity))
    texts = {label: widget.text() for label, widget in page.identity_labels.items()}
    assert "AbstractAssistant" in texts["Application"]
    assert "AbstractFramework" in texts["Part of"] and 'href="https://abstractframework.ai"' in texts["Part of"]
    assert "Laurent-Philippe Albou" in texts["Author"]
    assert "MIT" in texts["Copyright"]
    for label in ("Website", "Source", "Documentation", "Report an issue", "Give feedback"):
        assert f'href="{facts[label]}"' in texts[label], label
        assert page.identity_labels[label].openExternalLinks()
    assert f'href="mailto:{facts["Contact"]}"' in texts["Contact"]
    # The app-specific rows are still there.
    assert "Gateway: AbstractGateway 0.2.29" in page.stack_label.text()
    assert page.workflow_label.text()


@pytest.mark.basic
def test_gateway_rows_fall_back_to_capabilities_then_to_the_error(tmp_path) -> None:
    from types import SimpleNamespace

    from abstractassistant.controller import AssistantController
    from abstractassistant.gateway.client import GatewayHttpError

    controller = object.__new__(AssistantController)
    controller._cache_ttl_s = 20.0
    raw = {"abstractgateway": {"installed": True, "version": "0.4.4"}, "abstractcore": {"installed": True, "version": "2.15.4"}}
    controller.llm_manager = SimpleNamespace(gateway_capabilities=lambda **kw: SimpleNamespace(raw=raw))
    controller.gateway_service = SimpleNamespace(describe_connection_issue=lambda exc: "Gateway unreachable")

    def _missing():
        raise GatewayHttpError("not found", status=404)

    controller.gateway = SimpleNamespace(gateway_about=_missing)
    payload, error = controller.gateway_about()
    assert error is None and payload["abstractgateway"] == "0.4.4" and payload["packages"]["abstractcore"] == "2.15.4"

    controller._gateway_about_cache = None

    def _down():
        raise GatewayHttpError("boom", status=502)

    controller.gateway = SimpleNamespace(gateway_about=_down)
    assert controller.gateway_about() == (None, "Gateway unreachable")

    controller._gateway_about_cache = None
    controller.gateway = SimpleNamespace(gateway_about=lambda: {"abstractgateway": "0.5.0", "abstractframework": "0.4.0", "packages": {}})
    payload, error = controller.gateway_about()
    assert payload["abstractframework"] == "0.4.0"


@pytest.mark.basic
def test_copy_diagnostics_carries_the_about_lines() -> None:
    import json

    from PyQt5.QtWidgets import QApplication
    from test_settings_pages import _dialog

    dlg, _ctl = _dialog()
    dlg.show_section("about")
    dlg.page_about._copy_diagnostics()
    diag = json.loads(QApplication.clipboard().text())
    assert diag["about"][0].startswith("Application: AbstractAssistant")
    assert any(line.startswith("Report an issue: https://") for line in diag["about"])
    assert diag["gateway"][0] == "Gateway: AbstractGateway 0.2.29"


@pytest.mark.basic
def test_tray_menu_has_about_which_opens_the_about_page() -> None:
    from PyQt5.QtWidgets import QApplication

    import abstractassistant.app as app_module

    _app = QApplication.instance() or QApplication([])  # noqa: F841
    opened: list = []

    class _Palette:
        def show_palette(self):
            pass

        def hide(self):
            pass

        def _create_session(self):
            pass

        def open_automations(self):
            pass

        def _open_settings(self, section: str = ""):
            opened.append(section)

    menu = app_module._build_tray_menu(palette=_Palette(), quit_app=lambda: None)
    labels = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert labels == ["Show", "Hide", "New Session", "Automations…", "Settings", "About AbstractAssistant…", "Quit"]
    about = next(a for a in menu.actions() if a.text() == "About AbstractAssistant…")
    about.trigger()
    assert opened == ["about"]


@pytest.mark.basic
def test_about_rows_are_rendered_by_core_about_html() -> None:
    """One link rule for every app: the About rows are core's about_html
    output (only Contact becomes a mailto), not a local re-implementation."""
    import abstractcore.utils.identity as identity
    from test_settings_pages import _dialog

    calls: list = []
    real = identity.about_html

    def _spy(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    identity.about_html = _spy
    try:
        dlg, _ctl = _dialog()
        dlg.show_section("about")
        dlg.page_about.refresh()
    finally:
        identity.about_html = real
    assert calls
    texts = {label: w.text() for label, w in dlg.page_about.identity_labels.items()}
    assert sum("mailto:" in t for t in texts.values()) == 1 and "mailto:" in texts["Contact"]
    # A value with a URL inside text: only the URL is the link.
    assert texts["Part of"].startswith("AbstractFramework — <a ")

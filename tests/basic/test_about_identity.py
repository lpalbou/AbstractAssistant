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

    identity = app_identity("abstractassistant")
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
    assert "abstractgateway 0.2.29" in page.stack_label.text()
    assert page.workflow_label.text()


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

        def _open_settings(self, section: str = ""):
            opened.append(section)

    menu = app_module._build_tray_menu(palette=_Palette(), quit_app=lambda: None)
    labels = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert labels == ["Show", "Hide", "New Session", "Settings", "About AbstractAssistant…", "Quit"]
    about = next(a for a in menu.actions() if a.text() == "About AbstractAssistant…")
    about.trigger()
    assert opened == ["about"]

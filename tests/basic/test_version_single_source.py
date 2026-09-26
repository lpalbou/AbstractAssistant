"""One version everywhere: `abstractassistant.__version__` equals pyproject's,
and `--version`, Settings → About and the .app bundle all use it (never
"unknown")."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _pyproject_version() -> str:
    if sys.version_info >= (3, 11):
        import tomllib
    else:  # pragma: no cover
        import tomli as tomllib
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


@pytest.mark.basic
def test_version_matches_pyproject() -> None:
    import abstractassistant

    assert abstractassistant.__version__ == _pyproject_version()


@pytest.mark.basic
def test_cli_about_and_app_bundle_use_it(monkeypatch, capsys) -> None:
    import importlib.metadata

    import abstractassistant
    from abstractassistant import cli

    # No dist-info (a frozen .app): the version must still be the real one.
    def _missing(_name):
        raise importlib.metadata.PackageNotFoundError("abstractassistant")

    monkeypatch.setattr(importlib.metadata, "version", _missing)
    assert cli._package_version() == abstractassistant.__version__
    with pytest.raises(SystemExit):
        cli.create_parser().parse_args(["--version"])
    assert capsys.readouterr().out.strip() == f"abstractassistant {abstractassistant.__version__}"

    pytest.importorskip("PyQt5.QtWidgets")
    from abstractassistant.ui.settings.pages import _assistant_version

    assert _assistant_version() == abstractassistant.__version__

    spec = (ROOT / "packaging" / "macos" / "AbstractAssistant.spec").read_text(encoding="utf-8")
    assert "_version.py" in spec and "importlib_metadata" not in spec
    assert 'return "unknown"' not in (ROOT / "abstractassistant" / "cli.py").read_text(encoding="utf-8")

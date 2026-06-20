from __future__ import annotations

from pathlib import Path

import pytest

import abstractassistant.build_macos_app as build_module
import abstractassistant.macos_entry as macos_entry


@pytest.mark.basic
def test_pyinstaller_spec_declares_menu_bar_app_contract() -> None:
    spec_path = Path(__file__).resolve().parents[2] / "packaging" / "macos" / "AbstractAssistant.spec"
    spec = spec_path.read_text(encoding="utf-8")

    assert '"LSUIElement": True' in spec
    assert 'bundle_identifier=BUNDLE_ID' in spec
    assert 'macos_entry.py' in spec
    assert 'console=False' in spec
    assert 'argv_emulation=False' in spec
    assert 'collect_submodules("pymdownx")' in spec


@pytest.mark.basic
def test_build_macos_app_installs_pyinstaller_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    spec_path = root / "packaging" / "macos" / "AbstractAssistant.spec"
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text("# spec\n", encoding="utf-8")
    dist_app = root / "dist" / "macos" / "AbstractAssistant.app"
    install_calls: list[tuple[Path, Path]] = []

    monkeypatch.setattr(build_module.sys, "platform", "darwin")
    monkeypatch.setattr(build_module, "_repo_root", lambda: root)
    monkeypatch.setattr(build_module, "_ensure_icon_assets", lambda _root: None)

    def _fake_pyinstaller_run(spec: Path, dist_dir: Path, work_dir: Path) -> None:
        assert spec == spec_path
        assert dist_dir == root / "dist" / "macos"
        assert work_dir == root / "build" / "macos" / "pyinstaller-work"
        (dist_app / "Contents").mkdir(parents=True, exist_ok=True)
        (dist_app / "Contents" / "Info.plist").write_text("plist", encoding="utf-8")

    monkeypatch.setattr(build_module, "_pyinstaller_run", _fake_pyinstaller_run)
    monkeypatch.setattr(build_module, "_install_app", lambda src, dst: install_calls.append((src, dst)))

    app_path = build_module.build_macos_app(install_to_applications=True)

    assert app_path == Path("/Applications/AbstractAssistant.app")
    assert install_calls == [(dist_app, Path("/Applications/AbstractAssistant.app"))]


@pytest.mark.basic
def test_macos_entry_sets_launch_env_for_frozen_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[object] = []

    monkeypatch.delenv("ABSTRACTASSISTANT_SHOW_ON_LAUNCH", raising=False)
    monkeypatch.delenv("ABSTRACTASSISTANT_TRAY_LOG_PATH", raising=False)
    monkeypatch.delenv("ABSTRACTASSISTANT_TRAY_CAPTURE_PATH", raising=False)
    monkeypatch.setattr(macos_entry.sys, "argv", ["AbstractAssistant"])
    monkeypatch.setattr(macos_entry.sys, "frozen", True, raising=False)
    monkeypatch.setattr(macos_entry, "launch_tray_app", lambda **kwargs: calls.append(kwargs) or 7)
    monkeypatch.setattr(macos_entry.Path, "home", lambda: tmp_path)

    result = macos_entry.main()

    assert result == 7
    assert calls and isinstance(calls[0], dict)
    assert calls[0]["debug"] is False
    assert calls[0]["data_dir"] is None
    assert calls[0]["config"] is not None
    assert macos_entry.os.environ["ABSTRACTASSISTANT_SHOW_ON_LAUNCH"] == "1"
    assert "abstractassistant-launcher.log" in str(macos_entry.os.environ["ABSTRACTASSISTANT_TRAY_LOG_PATH"])
    assert "abstractassistant-status-item.png" in str(macos_entry.os.environ["ABSTRACTASSISTANT_TRAY_CAPTURE_PATH"])

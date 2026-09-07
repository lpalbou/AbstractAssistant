"""The macOS build must fail loudly, and must not fail because of itself.

Two failures seen for real on 2026-09-06: the build exited 0 with a traceback
and no bundle when the package was not pip-installed, and two overlapping
builds destroyed each other's PyInstaller cache — every build starts with
`--clean`, which deletes the shared cache, so the other one then evaluated an
empty index file and died with a bare `SyntaxError` naming nothing.
"""

from __future__ import annotations

import sys

import pytest

pytest.importorskip("fcntl")

from abstractassistant.build_macos_app import (  # noqa: E402
    _build_lock,
    _pyinstaller_cache_dir,
    _pyinstaller_run,
)


@pytest.mark.basic
def test_two_builds_cannot_run_at_once(tmp_path, monkeypatch) -> None:
    import abstractassistant.build_macos_app as build_module

    monkeypatch.setattr(build_module, "_build_dir", lambda root: tmp_path / "build")

    with _build_lock(tmp_path):
        with pytest.raises(RuntimeError) as excinfo:
            with _build_lock(tmp_path):
                pass
        message = str(excinfo.value)
        # It must name the cause and what to do, not just refuse.
        assert "already running" in message
        assert "cache" in message
        assert "build.lock" in message

    # The lock is released, so the next build is free to run.
    with _build_lock(tmp_path):
        pass


@pytest.mark.basic
def test_a_corrupt_cache_is_cleared_and_the_build_retried(tmp_path, monkeypatch) -> None:
    """`load_py_data_struct` evaluates the cache index; an empty one raises
    SyntaxError. Nothing in that cache is precious."""
    import abstractassistant.build_macos_app as build_module

    cache = tmp_path / "pyinstaller-cache"
    cache.mkdir()
    (cache / "index.dat").write_text("")
    monkeypatch.setattr(build_module, "_pyinstaller_cache_dir", lambda: cache)

    calls: list = []

    def _fake_run(args):
        calls.append(list(args))
        if len(calls) == 1:
            raise SyntaxError("invalid syntax")

    fake_module = type("M", (), {"run": staticmethod(_fake_run)})
    monkeypatch.setitem(sys.modules, "PyInstaller.__main__", fake_module)

    _pyinstaller_run(tmp_path / "app.spec", tmp_path / "dist", tmp_path / "work")

    assert len(calls) == 2, "the build must be retried once"
    assert not cache.exists(), "the corrupt cache must be cleared before retrying"
    # A retry uses the same arguments, not a degraded set.
    assert calls[0] == calls[1]
    assert "--clean" in calls[0]


@pytest.mark.basic
def test_a_second_failure_is_not_swallowed(tmp_path, monkeypatch) -> None:
    import abstractassistant.build_macos_app as build_module

    monkeypatch.setattr(build_module, "_pyinstaller_cache_dir", lambda: tmp_path / "gone")

    def _always_fails(args):
        raise SyntaxError("invalid syntax")

    monkeypatch.setitem(
        sys.modules, "PyInstaller.__main__", type("M", (), {"run": staticmethod(_always_fails)})
    )
    with pytest.raises(SyntaxError):
        _pyinstaller_run(tmp_path / "app.spec", tmp_path / "dist", tmp_path / "work")


@pytest.mark.basic
def test_the_cache_directory_is_the_real_one() -> None:
    cache = _pyinstaller_cache_dir()
    assert cache.name == "pyinstaller"
    if sys.platform == "darwin":
        assert "Application Support" in str(cache)

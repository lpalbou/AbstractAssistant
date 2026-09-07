"""Build a real macOS app bundle for AbstractAssistant via PyInstaller."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

from abstractassistant.utils.icon_generator import IconGenerator


APP_NAME = "AbstractAssistant"
BUNDLE_ID = "ai.abstractcore.abstractassistant"
MIN_MACOS = "10.15"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _build_dir(root: Path) -> Path:
    return root / "build" / "macos"


def _dist_dir(root: Path) -> Path:
    return root / "dist" / "macos"


def _applications_target() -> Path:
    return Path("/Applications") / f"{APP_NAME}.app"


def _spec_path(root: Path) -> Path:
    return root / "packaging" / "macos" / f"{APP_NAME}.spec"


def _generate_icon_png(target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    asset = Path(__file__).resolve().parent / "assets" / "app_icon.png"
    if asset.exists():
        # Ship the designed app icon (transparent rounded-square art) rather
        # than the procedural constellation; iconutil resizes it downstream.
        Image.open(asset).convert("RGBA").save(target)
        return
    image = IconGenerator(size=1024).create_app_icon("blue", animated=False)
    image.save(target)


def _create_icns_file(png_path: Path, icns_path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="abstractassistant-iconset-") as tmpdir:
        iconset_dir = Path(tmpdir) / "app.iconset"
        iconset_dir.mkdir(parents=True, exist_ok=True)
        image = Image.open(png_path)
        sizes = [
            (16, "icon_16x16.png"),
            (32, "icon_16x16@2x.png"),
            (32, "icon_32x32.png"),
            (64, "icon_32x32@2x.png"),
            (128, "icon_128x128.png"),
            (256, "icon_128x128@2x.png"),
            (256, "icon_256x256.png"),
            (512, "icon_256x256@2x.png"),
            (512, "icon_512x512.png"),
            (1024, "icon_512x512@2x.png"),
        ]
        for size, name in sizes:
            image.resize((size, size), Image.Resampling.LANCZOS).save(iconset_dir / name)
        result = subprocess.run(
            ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "iconutil failed")


def _ensure_icon_assets(root: Path) -> tuple[Path, Path]:
    build_dir = _build_dir(root)
    png_path = build_dir / "icon.png"
    icns_path = build_dir / "icon.icns"
    _generate_icon_png(png_path)
    _create_icns_file(png_path, icns_path)
    return png_path, icns_path


def _pyinstaller_cache_dir() -> Path:
    """Where PyInstaller keeps its shared binary cache on this machine."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "pyinstaller"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "pyinstaller"


@contextlib.contextmanager
def _build_lock(root: Path):
    """Refuse to run two builds at once.

    They share one PyInstaller cache and each starts by deleting it
    (`--clean`), so a second build wipes the first one's index mid-read and it
    dies on `eval('')` — an empty cache file — with a SyntaxError that names
    nothing. One at a time, and say so plainly.
    """
    lock_dir = _build_dir(root)
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "build.lock"
    handle = lock_path.open("w")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError(
                f"another AbstractAssistant build is already running (lock: {lock_path}). "
                "Builds share PyInstaller's cache and corrupt it if they overlap — "
                "wait for the other one to finish, or delete the lock if it is stale."
            ) from None
        handle.write(f"{os.getpid()}\n")
        handle.flush()
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _pyinstaller_run(spec_path: Path, dist_dir: Path, work_dir: Path) -> None:
    try:
        from PyInstaller.__main__ import run as pyinstaller_run
    except Exception as exc:
        raise RuntimeError(
            "PyInstaller is required to build the macOS app. Install it with: "
            'pip install "pyinstaller>=6.21.0"'
        ) from exc

    args = [
        "--noconfirm",
        "--clean",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        str(spec_path),
    ]
    try:
        pyinstaller_run(list(args))
    except SyntaxError:
        # A truncated cache index: `load_py_data_struct` evaluates the file and
        # an empty one raises SyntaxError from "<string>", line 0. Nothing here
        # is precious, so drop it and build once more.
        cache = _pyinstaller_cache_dir()
        print(f"PyInstaller cache looks corrupt; clearing {cache} and retrying")
        shutil.rmtree(cache, ignore_errors=True)
        pyinstaller_run(list(args))


def _install_app(source_app: Path, target_app: Path) -> None:
    if target_app.exists():
        shutil.rmtree(target_app)
    shutil.copytree(source_app, target_app, symlinks=True)
    subprocess.run(["touch", str(target_app)], capture_output=True, text=True)
    lsregister = Path(
        "/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister"
    )
    if lsregister.exists():
        subprocess.run([str(lsregister), "-f", str(target_app)], capture_output=True, text=True)


def _require_voice_io() -> None:
    """Preflight: refuse to build a bundle without local audio I/O.

    Voice is core to the assistant. Without sounddevice the bundle silently
    loses gateway streaming TTS (first audio waits for whole-message
    synthesis: ~1 minute for long replies instead of seconds) and local
    microphone capture — PyInstaller records the miss as one line in a warn
    file nobody reads. `abstractvoice[audio-io]` is a base dependency, so its
    absence means a broken build environment; fail loudly rather than ship a
    degraded app (2026-07-15 time-to-first-voice regression).
    """
    try:
        import sounddevice  # noqa: F401
    except Exception as exc:
        raise RuntimeError(
            "'sounddevice' is not importable in this build environment, so the "
            "bundle would lose audio streaming and microphone capture. It ships "
            "with the base install via abstractvoice[audio-io]; reinstall the "
            "package (pip install --no-build-isolation -e .) into the build venv "
            "and rebuild."
        ) from exc


def _sync_shared_themes(root: Path) -> None:
    """Carry abstractuic's palettes into the bundle.

    The app reads `theme.css` so palettes added upstream appear with no code
    change, but a packaged .app has no sibling checkout to read — so the build
    copies the current stylesheet into the assets the spec already bundles.
    Missing checkout is not fatal: the app falls back to its vendored snapshot.
    """
    source = root.parent / "abstractuic" / "ui-kit" / "src" / "theme.css"
    target = root / "abstractassistant" / "assets" / "uic-theme.css"
    if not source.is_file():
        print(f"note: {source} not found; bundling the vendored palettes instead")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    print(f"themes: {source} -> {target}")


def build_macos_app(*, install_to_applications: bool = True) -> Path:
    if sys.platform != "darwin":
        raise RuntimeError("macOS app builds are only supported on macOS")
    _require_voice_io()
    root = _repo_root()
    with _build_lock(root):
        return _build_locked(root, install_to_applications=install_to_applications)


def _build_locked(root: Path, *, install_to_applications: bool) -> Path:
    _ensure_icon_assets(root)
    _sync_shared_themes(root)
    spec_path = _spec_path(root)
    if not spec_path.exists():
        raise RuntimeError(f"Missing PyInstaller spec file: {spec_path}")
    dist_dir = _dist_dir(root)
    work_dir = _build_dir(root) / "pyinstaller-work"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    _pyinstaller_run(spec_path, dist_dir, work_dir)
    built_app = dist_dir / f"{APP_NAME}.app"
    if not built_app.exists():
        raise RuntimeError(f"PyInstaller did not produce {built_app}")
    if install_to_applications:
        target_app = _applications_target()
        _install_app(built_app, target_app)
        return target_app
    return built_app


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a real macOS app bundle for AbstractAssistant")
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Build under dist/macos but do not copy the app into /Applications",
    )
    args = parser.parse_args()
    app_path = build_macos_app(install_to_applications=not args.skip_install)
    print(app_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

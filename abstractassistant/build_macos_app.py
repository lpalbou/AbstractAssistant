"""Build a real macOS app bundle for AbstractAssistant via PyInstaller."""

from __future__ import annotations

import argparse
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


def _pyinstaller_run(spec_path: Path, dist_dir: Path, work_dir: Path) -> None:
    try:
        from PyInstaller.__main__ import run as pyinstaller_run
    except Exception as exc:
        raise RuntimeError(
            "PyInstaller is required to build the macOS app. Install it with: "
            'pip install "pyinstaller>=6.21.0"'
        ) from exc
    pyinstaller_run(
        [
            "--noconfirm",
            "--clean",
            "--distpath",
            str(dist_dir),
            "--workpath",
            str(work_dir),
            str(spec_path),
        ]
    )


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


def build_macos_app(*, install_to_applications: bool = True) -> Path:
    if sys.platform != "darwin":
        raise RuntimeError("macOS app builds are only supported on macOS")
    root = _repo_root()
    _ensure_icon_assets(root)
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

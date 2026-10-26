# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules


APP_NAME = "AbstractAssistant"
# The Mac app joins the AbstractAssistant Apple family (iPhone `ai.abstractframework.assistant`,
# watch `….watchkitapp`): ADR 0006. Through 0.15.0 it was `ai.abstractcore.abstractassistant`.
# abstractassistant/build_macos_app.py carries the same id (a test keeps them equal).
BUNDLE_ID = "ai.abstractframework.assistant.mac"
MIN_MACOS = "10.15"

ROOT = Path(SPECPATH).resolve().parents[1]
ENTRY = ROOT / "abstractassistant" / "macos_entry.py"
ICON = ROOT / "build" / "macos" / "icon.icns"


def _version() -> str:
    """The app version: `abstractassistant/_version.py`, the package's single
    source (read as text, so the build needs neither an install nor imports)."""
    import re

    text = (ROOT / "abstractassistant" / "_version.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.M)
    if not match:
        raise SystemExit("abstractassistant/_version.py has no __version__")
    return match.group(1)


VERSION = _version()


def _signing_from_env(environ, spec_dir):
    """(codesign identity, entitlements file) for PyInstaller, from the environment.

    Unset = the unsigned local build, exactly as before (PyInstaller ad-hoc signs it and no
    entitlements apply). With ABSTRACTASSISTANT_CODESIGN_IDENTITY set (a "Developer ID
    Application: … (TEAMID)" identity; `build-macos-app --sign` sets it) every collected
    binary is signed with that identity, the hardened runtime and a secure timestamp, using
    packaging/macos/entitlements.plist unless ABSTRACTASSISTANT_ENTITLEMENTS names another
    file. Self-contained (no imports, no globals) so tests can run it on its own.
    """
    identity = str(environ.get("ABSTRACTASSISTANT_CODESIGN_IDENTITY") or "").strip() or None
    if identity is None:
        # Entitlements only mean something with a signature that carries them.
        return None, None
    entitlements = str(environ.get("ABSTRACTASSISTANT_ENTITLEMENTS") or "").strip()
    return identity, entitlements or str(spec_dir / "entitlements.plist")


CODESIGN_IDENTITY, ENTITLEMENTS_FILE = _signing_from_env(os.environ, Path(SPECPATH).resolve())
if CODESIGN_IDENTITY:
    if not Path(ENTITLEMENTS_FILE).is_file():
        raise SystemExit(f"entitlements file not found: {ENTITLEMENTS_FILE}")
    print(f"codesign: {CODESIGN_IDENTITY!r} with {ENTITLEMENTS_FILE}")
PATHEX = [str(ROOT)]
for candidate in (
    ROOT.parent / "abstractruntime" / "src",
    ROOT.parent / "abstractcore" / "src",
    ROOT.parent / "abstractcore",
    ROOT.parent / "abstractvoice",
):
    if candidate.exists():
        PATHEX.append(str(candidate.resolve()))

HIDDENIMPORTS = [
    "abstractassistant.app",
    "abstractassistant.controller",
    "abstractassistant.gateway_service",
    "abstractassistant.assistant_workflow",
    "abstractassistant.hotkey",
    "abstractassistant.preferences",
    "abstractassistant.core.gateway_stt_adapter",
    "abstractassistant.ui.gateway_worker",
    "abstractcore.config.manager",
    "abstractruntime.integrations.abstractcore.session_attachments",
    "abstractvoice.recognition",
    "abstractvoice.tts",
]

ASSETS_DIR = ROOT / "abstractassistant" / "assets"
DATAS = []
if ASSETS_DIR.exists():
    DATAS.append((str(ASSETS_DIR), "abstractassistant/assets"))

a = Analysis(
    [str(ENTRY)],
    pathex=PATHEX,
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDENIMPORTS,
    # Project hooks (see hooks/hook-webrtcvad.py) take precedence over the contrib ones.
    hookspath=[str(Path(SPECPATH).resolve() / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    # pygame is only reachable through nltk's lazy timit corpus import; bundling
    # it drags SDL dylibs whose codesign processing can fail (libwebp bincache).
    # abstractgateway: config._gateway_local_rule imports it to find this computer's
    # gateway when both share a Python (the console's install); a frozen bundle must
    # not carry a whole gateway, so the app uses its saved sign-in or 127.0.0.1:8080
    # (the console still opens it with --gateway-url).
    excludes=["PyQt6", "PySide2", "PySide6", "pygame", "abstractgateway"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=CODESIGN_IDENTITY,
    entitlements_file=ENTITLEMENTS_FILE,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    icon=str(ICON),
    bundle_identifier=BUNDLE_ID,
    info_plist={
        "CFBundleDisplayName": APP_NAME,
        "CFBundleName": APP_NAME,
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": MIN_MACOS,
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
        "NSAppleScriptEnabled": False,
        # Voice mode records via abstractvoice; without this usage string
        # macOS terminates the process on first microphone access.
        "NSMicrophoneUsageDescription": (
            "AbstractAssistant uses the microphone for voice conversations "
            "and dictation."
        ),
    },
)

# -*- mode: python ; coding: utf-8 -*-

from importlib import metadata as importlib_metadata
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules


APP_NAME = "AbstractAssistant"
BUNDLE_ID = "ai.abstractcore.abstractassistant"
MIN_MACOS = "10.15"

ROOT = Path(SPECPATH).resolve().parents[1]
ENTRY = ROOT / "abstractassistant" / "macos_entry.py"
ICON = ROOT / "build" / "macos" / "icon.icns"
VERSION = str(importlib_metadata.version("abstractassistant"))
PATHEX = [str(ROOT)]
for candidate in (
    ROOT.parent / "abstractruntime" / "src",
    ROOT.parent / "abstractgateway" / "src",
    ROOT.parent / "abstractcore" / "src",
    ROOT.parent / "abstractcore",
    ROOT.parent / "abstractvoice",
):
    if candidate.exists():
        PATHEX.append(str(candidate.resolve()))

HIDDENIMPORTS = [
    "abstractassistantv2",
    "abstractassistantv2.app",
    "abstractassistantv2.controller",
    "abstractassistantv2.gateway",
    "abstractassistantv2.hotkey",
    "abstractassistantv2.preferences",
    "abstractassistant.core.gateway_stt_adapter",
    "abstractassistant.ui.gateway_worker",
    "abstractcore.config.manager",
    "abstractruntime.integrations.abstractcore.session_attachments",
    "abstractvoice.recognition",
    "abstractvoice.tts",
]

a = Analysis(
    [str(ENTRY)],
    pathex=PATHEX,
    binaries=[],
    datas=[],
    hiddenimports=HIDDENIMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # pygame is only reachable through nltk's lazy timit corpus import; bundling
    # it drags SDL dylibs whose codesign processing can fail (libwebp bincache).
    excludes=["PyQt6", "PySide2", "PySide6", "pygame"],
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
    codesign_identity=None,
    entitlements_file=None,
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

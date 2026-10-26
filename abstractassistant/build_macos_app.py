"""Build a real macOS app bundle for AbstractAssistant via PyInstaller."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional, Sequence

from PIL import Image

from abstractassistant.utils.icon_generator import IconGenerator


APP_NAME = "AbstractAssistant"
# The same id as packaging/macos/AbstractAssistant.spec (a test keeps them equal): the Mac app
# in the AbstractAssistant Apple family, ADR 0006. Released bundles through 0.14.3 carried
# ai.abstractcore.abstractassistant; 0.15.0 is the first built with this id.
BUNDLE_ID = "ai.abstractframework.assistant.mac"
MIN_MACOS = "10.15"

# Signing and notarization (ADR 0006, docs/macos-signing.md). All optional: with none of the
# flags below the build is the unsigned local one it always was. The Apple names reuse the
# iPhone pipeline's secrets (ASC_KEY_ID, ASC_ISSUER_ID, ASC_KEY_P8, TEAM_ID).
IDENTITY_ENV = "ABSTRACTASSISTANT_CODESIGN_IDENTITY"
ENTITLEMENTS_ENV = "ABSTRACTASSISTANT_ENTITLEMENTS"
NOTARY_PROFILE_ENV = "ABSTRACTASSISTANT_NOTARY_PROFILE"
ASC_KEY_ID_ENV = "ASC_KEY_ID"
ASC_ISSUER_ID_ENV = "ASC_ISSUER_ID"
ASC_KEY_PATH_ENV = "ASC_KEY_PATH"
ASC_KEY_P8_ENV = "ASC_KEY_P8"
TEAM_ID_ENV = "TEAM_ID"
# PyInstaller only WARNS when signing the bundle fails unless this is set (PyInstaller
# building/osx.py, BUNDLE): with an identity, a broken seal must stop the build.
STRICT_CODESIGN_ENV = "PYINSTALLER_STRICT_BUNDLE_CODESIGN_ERROR"


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


def _entitlements_path(root: Path) -> Path:
    return root / "packaging" / "macos" / "entitlements.plist"


def _app_version(root: Path) -> str:
    text = (root / "abstractassistant" / "_version.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.M)
    if not match:
        raise RuntimeError("abstractassistant/_version.py has no __version__")
    return match.group(1)


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


def _require_hook_metadata() -> None:
    """Preflight: the distributions the project's PyInstaller hooks copy metadata from.

    packaging/macos/hooks/hook-webrtcvad.py copies `webrtcvad-wheels` (what
    abstractvoice[audio-io] requires); an environment holding the older `webrtcvad`
    instead fails inside PyInstaller's analysis after ~7 minutes (measured 2026-10-26).
    Say it before the build starts.
    """
    import importlib.metadata as metadata

    try:
        metadata.distribution("webrtcvad-wheels")
    except metadata.PackageNotFoundError:
        raise RuntimeError(
            "'webrtcvad-wheels' is not installed in this build environment (abstractvoice[audio-io] "
            "requires it; an older 'webrtcvad' does not count), so PyInstaller's webrtcvad hook would "
            "fail minutes into the build. Reinstall the package with its voice extra into the build "
            "venv (pip install -e \".[macos-app]\" from a fresh venv) and rebuild."
        ) from None


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



# ---------------------------------------------------------------------------------------------
# Signing, notarization and the disk image. Everything here is macOS distribution packaging
# layered on a cross-platform app: nothing below is imported by the app at run time, and the
# planners are pure (they only build argument lists) so they are tested on any platform.
# ---------------------------------------------------------------------------------------------


class SigningError(RuntimeError):
    """A signing/notarization configuration or step that cannot go on. Always says why."""


# Development certificates: they sign code that runs on this team's own Macs (the hardened
# runtime and library validation behave exactly as with Developer ID), but Gatekeeper and the
# notary service refuse them. Allowed for --local-test only.
_DEVELOPMENT = ("Apple Development", "Mac Developer")
# Mac App Store certificates: never right for this app (ADR 0006 section 2).
_STORE = ("Apple Distribution", "3rd Party Mac Developer")
_DEVELOPER_ID_PREFIX = "Developer ID Application:"
_KEY_ID = re.compile(r"^[A-Z0-9]{10}$")
_ISSUER_ID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_TEAM_IN_IDENTITY = re.compile(r"\(([A-Z0-9]{10})\)\s*$")


@dataclass(frozen=True)
class NotaryAuth:
    """How notarytool signs in: a keychain profile (`notarytool store-credentials`) or an
    App Store Connect team API key. `key_text` is the .p8 itself (CI's ASC_KEY_P8), written
    to a private file only for the duration of the submission."""

    profile: str = ""
    key_id: str = ""
    issuer_id: str = ""
    key_path: str = ""
    key_text: str = field(default="", repr=False)

    def args(self, key_file: Optional[str] = None) -> list[str]:
        if self.profile:
            return ["--keychain-profile", self.profile]
        path = key_file or self.key_path or "<ASC_KEY_P8 written to a private temporary file>"
        return ["--key", path, "--key-id", self.key_id, "--issuer", self.issuer_id]


@dataclass(frozen=True)
class Step:
    """One command of the plan. `kind` asks the runner for a check beyond the exit code."""

    label: str
    argv: tuple[str, ...]
    kind: str = "run"  # run | notarize | assess-app | assess-dmg | team | nested | note
    target: str = ""  # the bundle a "nested" check walks

    def shell(self) -> str:
        return shlex.join(self.argv)


def _env_value(env: Mapping[str, str], name: str) -> str:
    return str(env.get(name) or "").strip()


def resolve_identity(env: Mapping[str, str], override: str = "", *, local_test: bool = False) -> str:
    """The identity to sign with, or a SigningError saying how to provide one.

    A release needs a Developer ID Application identity. `local_test` also accepts an Apple
    Development identity: a build to launch on this Mac under the real hardened runtime, never
    to notarize or ship. Ad-hoc ('-') is refused in both cases: a hardened, ad-hoc PyInstaller
    bundle cannot load its own libpython (library validation, "different Team IDs"), so it
    proves nothing. A Developer ID name ends with its team in parentheses, checked against
    TEAM_ID; a development name ends with the person's id instead, so it is checked on the
    signed app (TeamIdentifier) rather than here."""
    identity = str(override or "").strip() or _env_value(env, IDENTITY_ENV)
    if not identity:
        raise SigningError(
            f"signing needs a Developer ID Application identity: pass --identity or set {IDENTITY_ENV} "
            '(e.g. "Developer ID Application: Your Name (TEAMID)"; docs/macos-signing.md)'
        )
    if identity == "-":
        raise SigningError(
            "ad-hoc signing ('-') cannot pass Gatekeeper or notarization, and a hardened ad-hoc bundle "
            "cannot even load its own Python library; for a local launch test use an Apple Development "
            "identity with --local-test (docs/macos-signing.md)"
        )
    for prefix in _STORE:
        if identity.startswith(prefix):
            raise SigningError(
                f"{identity!r} is a Mac App Store certificate; this app is distributed with Developer ID "
                "(ADR 0006): use the Developer ID Application identity"
            )
    for prefix in _DEVELOPMENT:
        if identity.startswith(prefix) and not local_test:
            raise SigningError(
                f"{identity!r} is a development certificate: Gatekeeper and notarization refuse it. Use the "
                "Developer ID Application identity, or --local-test to build a signed app to launch on this Mac"
            )
    team = _env_value(env, TEAM_ID_ENV)
    match = _TEAM_IN_IDENTITY.search(identity)
    if team and match and identity.startswith(_DEVELOPER_ID_PREFIX) and match.group(1) != team:
        raise SigningError(f"identity {identity!r} belongs to team {match.group(1)}, but {TEAM_ID_ENV}={team}")
    return identity


def resolve_notary_auth(env: Mapping[str, str], profile_override: str = "") -> NotaryAuth:
    """Exactly one way to sign in to the notary service, or a SigningError naming the variables."""
    profile = str(profile_override or "").strip() or _env_value(env, NOTARY_PROFILE_ENV)
    key_id = _env_value(env, ASC_KEY_ID_ENV)
    issuer = _env_value(env, ASC_ISSUER_ID_ENV)
    key_path = _env_value(env, ASC_KEY_PATH_ENV)
    key_text = str(env.get(ASC_KEY_P8_ENV) or "").strip()
    api_parts = {ASC_KEY_ID_ENV: key_id, ASC_ISSUER_ID_ENV: issuer, f"{ASC_KEY_PATH_ENV} or {ASC_KEY_P8_ENV}": key_path or key_text}
    any_api = any(api_parts.values())
    if profile and any_api:
        raise SigningError(
            f"both a notary keychain profile ({NOTARY_PROFILE_ENV}/--notary-profile) and an App Store Connect "
            "API key are set; set one, so it is clear which account notarizes"
        )
    if profile:
        return NotaryAuth(profile=profile)
    if not any_api:
        raise SigningError(
            "notarization needs credentials: a keychain profile made with `xcrun notarytool store-credentials` "
            f"(--notary-profile or {NOTARY_PROFILE_ENV}), or an App Store Connect team API key "
            f"({ASC_KEY_ID_ENV}, {ASC_ISSUER_ID_ENV} and {ASC_KEY_PATH_ENV} or {ASC_KEY_P8_ENV}); docs/macos-signing.md"
        )
    missing = [name for name, value in api_parts.items() if not value]
    if missing:
        raise SigningError(f"the App Store Connect API key is incomplete: {', '.join(missing)} not set")
    if key_path and key_text:
        raise SigningError(f"set {ASC_KEY_PATH_ENV} or {ASC_KEY_P8_ENV}, not both")
    if not _KEY_ID.match(key_id):
        raise SigningError(f"{ASC_KEY_ID_ENV} is not a 10-character App Store Connect key id")
    if not _ISSUER_ID.match(issuer):
        raise SigningError(f"{ASC_ISSUER_ID_ENV} is not an issuer UUID")
    if key_path and not Path(key_path).expanduser().is_file():
        raise SigningError(f"{ASC_KEY_PATH_ENV} does not name a file: {key_path}")
    return NotaryAuth(key_id=key_id, issuer_id=issuer, key_path=str(Path(key_path).expanduser()) if key_path else "", key_text=key_text)


_MACH_O_MAGIC = {
    bytes.fromhex("cffaedfe"), bytes.fromhex("cefaedfe"),  # 64/32-bit, little-endian
    bytes.fromhex("feedfacf"), bytes.fromhex("feedface"),
    bytes.fromhex("cafebabe"), bytes.fromhex("bebafeca"),  # universal
}


def mach_o_files(bundle: Path) -> list[Path]:
    """Every Mach-O file inside the bundle (by magic number; symlinks skipped), sorted."""
    found = []
    for path in sorted(Path(bundle).rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            with path.open("rb") as handle:
                head = handle.read(4)
        except OSError:
            continue
        if head in _MACH_O_MAGIC:
            found.append(path)
    return found


def check_nested_signature(output: str, *, team_id: str = "") -> Optional[str]:
    """What is wrong with one nested binary's signature (`codesign -dv --verbose=2`), or None.
    Notarization requires the hardened runtime and a secure timestamp on every executable."""
    text = output or ""
    flags = re.search(r"flags=0x[0-9a-f]+\(([^)]*)\)", text)
    if not flags or "runtime" not in flags.group(1).split(","):
        return "no hardened runtime"
    if "adhoc" in flags.group(1).split(","):
        return "ad-hoc signature"
    if "Timestamp=" not in text:
        return "no secure timestamp"
    if team_id and f"TeamIdentifier={team_id}" not in text:
        found = re.search(r"TeamIdentifier=(\S+)", text)
        return f"team {found.group(1) if found else 'unknown'}, not {team_id}"
    return None


def plan_release(
    *,
    app: Path,
    work_dir: Path,
    out_dir: Path,
    version: str,
    entitlements: Path,
    identity: Optional[str] = None,
    notary: Optional[NotaryAuth] = None,
    dmg: bool = False,
    team_id: str = "",
    local_test: bool = False,
) -> list[Step]:
    """The ordered commands after PyInstaller, for the options given. Empty = the unsigned
    build (nothing runs after PyInstaller, as before).

    Signing is inside-out and done by PyInstaller (the spec passes the identity and the
    entitlements to it): every collected binary is signed first, then the bundle. There is no
    second `codesign --deep` pass here: it would replace every nested signature (`man codesign`:
    deprecated for signing since macOS 13). These steps verify instead, including every nested
    binary's hardened runtime, timestamp and team, which is what notarization checks.

    With a disk image and notarization, the app is notarized and stapled first, then the image
    is built from the stapled app, signed, notarized and stapled itself: one more submission
    than strictly needed, so that the app INSIDE the image carries its own ticket and opens
    offline once copied out (a ticket cannot be stapled into an image after it is built)."""
    if notary is not None and not identity:
        raise SigningError("notarization needs a signed app: --notarize signs first, give it an identity")
    if local_test and (notary is not None or dmg):
        raise SigningError("--local-test builds a signed app to launch on this Mac; it cannot be notarized or imaged")
    steps: list[Step] = []
    dmg_path = out_dir / f"{APP_NAME}-{version}.dmg"
    if identity:
        steps += [
            Step("verify the signature PyInstaller made", ("codesign", "--verify", "--deep", "--strict", "--verbose=1", str(app))),
            Step("show the signature", ("codesign", "--display", "--verbose=4", str(app)), kind="team" if team_id else "run"),
            Step("show the entitlements", ("codesign", "--display", "--entitlements", "-", str(app))),
            Step(
                "check every nested binary: hardened runtime, secure timestamp" + (f", team {team_id}" if team_id else ""),
                ("codesign", "--display", "--verbose=2", "<each Mach-O file in the app>"),
                kind="nested", target=str(app),
            ),
        ]
    if local_test:
        executable = app / "Contents" / "MacOS" / APP_NAME
        steps += [
            Step("Gatekeeper is not asked: a development identity is not meant to pass it", (), kind="note"),
            Step(
                f"launch test (by hand, docs/macos-signing.md): run {executable} from Terminal, then try a voice "
                "conversation, a spoken reply, the hotkey and an attachment; on a crash read Console for "
                "CODE SIGNING / Library Validation",
                (), kind="note",
            ),
        ]
        return steps
    if notary is not None:
        upload_zip = work_dir / f"{APP_NAME}-{version}-notary-upload.zip"
        steps += [
            Step("zip the app for the notary service", ("ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app), str(upload_zip))),
            Step("notarize the app (waits for Apple)", ("xcrun", "notarytool", "submit", str(upload_zip), *notary.args(), "--wait", "--output-format", "json"), kind="notarize"),
            Step("staple the ticket to the app", ("xcrun", "stapler", "staple", str(app))),
            Step("validate the stapled ticket", ("xcrun", "stapler", "validate", str(app))),
        ]
    if identity:
        steps.append(Step("Gatekeeper assessment of the app", ("spctl", "--assess", "--type", "execute", "--verbose=4", str(app)), kind="assess-app"))
    if notary is not None and not dmg:
        steps.append(Step("zip the stapled app for download", ("ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app), str(out_dir / f"{APP_NAME}-{version}.zip"))))
    if dmg:
        staging = work_dir / "dmg-root"
        steps += [
            Step("clear the disk image's staging folder", ("rm", "-rf", str(staging))),
            Step("stage the app for the disk image", ("ditto", str(app), str(staging / f"{APP_NAME}.app"))),
            Step("add the Applications shortcut", ("ln", "-s", "/Applications", str(staging / "Applications"))),
            Step("build the disk image", ("hdiutil", "create", "-volname", APP_NAME, "-srcfolder", str(staging), "-ov", "-format", "UDZO", str(dmg_path))),
        ]
        if identity:
            steps.append(Step("sign the disk image", ("codesign", "--force", "--timestamp", "--sign", identity, str(dmg_path))))
        if notary is not None:
            steps += [
                Step("notarize the disk image (waits for Apple)", ("xcrun", "notarytool", "submit", str(dmg_path), *notary.args(), "--wait", "--output-format", "json"), kind="notarize"),
                Step("staple the ticket to the disk image", ("xcrun", "stapler", "staple", str(dmg_path))),
                Step("validate the disk image's ticket", ("xcrun", "stapler", "validate", str(dmg_path))),
            ]
        if identity:
            steps.append(Step("Gatekeeper assessment of the disk image", ("spctl", "--assess", "--type", "open", "--context", "context:primary-signature", "--verbose=4", str(dmg_path)), kind="assess-dmg"))
    return steps


def check_assessment(returncode: int, output: str, *, notarized: bool) -> None:
    """spctl's verdict, read strictly. Notarized: it must be accepted as a notarized Developer
    ID. Signed only: Gatekeeper rejects any un-notarized app, so the one acceptable answer is
    the rejection that proves the signature is a Developer ID one ("Unnotarized Developer ID");
    anything else (ad-hoc, another certificate, a broken seal) fails."""
    text = output or ""
    if notarized:
        if returncode == 0 and "accepted" in text and "Notarized Developer ID" in text:
            return
        raise SigningError(f"Gatekeeper did not accept the notarized build:\n{text.strip()}")
    if returncode == 0 and "accepted" in text:
        return
    if "Unnotarized Developer ID" in text:
        print("  (expected: signed with Developer ID, not notarized yet; Gatekeeper accepts it after --notarize)")
        return
    raise SigningError(f"Gatekeeper rejected the signature (not a Developer ID signature?):\n{text.strip()}")


def check_team(output: str, team_id: str) -> None:
    if f"TeamIdentifier={team_id}" not in (output or ""):
        found = re.search(r"TeamIdentifier=(\S+)", output or "")
        raise SigningError(
            f"the app is signed by team {found.group(1) if found else 'unknown'}, not {TEAM_ID_ENV}={team_id}"
        )


def parse_notary_result(output: str) -> dict:
    """notarytool's JSON answer; anything but "Accepted" is a SigningError naming the
    submission so `xcrun notarytool log <id>` finds Apple's reasons."""
    text = (output or "").strip()
    payload: object = {}
    for candidate in (text, text.splitlines()[-1] if text else ""):
        try:
            payload = json.loads(candidate)
            break
        except ValueError:
            continue
    if not isinstance(payload, dict) or not payload:
        raise SigningError(f"notarytool gave no readable result:\n{(output or '').strip()}")
    status = str(payload.get("status") or "")
    if status != "Accepted":
        raise SigningError(
            f"notarization {status or 'did not complete'} (submission {payload.get('id', '?')}): "
            f"{payload.get('message', '')}".strip()
        )
    return payload


@contextlib.contextmanager
def _private_key_file(auth: Optional[NotaryAuth]):
    """The .p8 from ASC_KEY_P8 in a 0700 directory for the duration of the plan, then gone,
    including on failure (the iPhone pipeline's upload-candidate.sh does the same)."""
    if auth is None or auth.profile or not auth.key_text:
        yield None
        return
    folder = Path(tempfile.mkdtemp(prefix="abstractassistant-notary-"))
    try:
        folder.chmod(0o700)
        key = folder / f"AuthKey_{auth.key_id}.p8"
        fd = os.open(str(key), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(auth.key_text.strip() + "\n")
        yield str(key)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def _with_key_file(step: Step, auth: Optional[NotaryAuth], key_file: Optional[str]) -> Step:
    if step.kind != "notarize" or auth is None or not key_file:
        return step
    placeholder = auth.args()
    argv = list(step.argv)
    start = argv.index(placeholder[0])
    argv[start:start + len(placeholder)] = auth.args(key_file)
    return Step(step.label, tuple(argv), step.kind, step.target)


def _check_nested(step: Step, *, team_id: str, runner) -> None:
    files = mach_o_files(Path(step.target))
    if not files:
        # An absent input must not read as a pass: a bundle with no binaries is broken.
        raise SigningError(f"{step.label}: no Mach-O file found in {step.target}")
    problems = []
    for path in files:
        result = runner(["codesign", "--display", "--verbose=2", str(path)], capture_output=True, text=True)
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        problem = f"exit {result.returncode}" if result.returncode != 0 else check_nested_signature(output, team_id=team_id)
        if problem:
            problems.append(f"{path.relative_to(step.target)}: {problem}")
    print(f"  {len(files)} binaries checked, {len(problems)} wrong", flush=True)
    if problems:
        shown = "\n  ".join(problems[:15])
        more = f"\n  … and {len(problems) - 15} more" if len(problems) > 15 else ""
        raise SigningError(f"{step.label}: {len(problems)} of {len(files)} binaries fail:\n  {shown}{more}")


def run_plan(
    steps: Sequence[Step], *, dry_run: bool = False, notary: Optional[NotaryAuth] = None,
    team_id: str = "", runner=subprocess.run,
) -> None:
    """Run each step, printing exactly what runs; stop at the first failure with the tool's
    own output. A dry run prints the commands and runs nothing."""
    with (contextlib.nullcontext(None) if dry_run else _private_key_file(notary)) as key_file:
        for number, step in enumerate(steps, 1):
            step = _with_key_file(step, notary, key_file)
            if step.kind == "note":
                print(f"[{number}/{len(steps)}] {step.label}", flush=True)
                continue
            print(f"[{number}/{len(steps)}] {step.label}\n  $ {step.shell()}", flush=True)
            if dry_run:
                continue
            if step.kind == "nested":
                _check_nested(step, team_id=team_id, runner=runner)
                continue
            result = runner(list(step.argv), capture_output=True, text=True)
            output = ((result.stdout or "") + (result.stderr or "")).strip()
            if output:
                print("  " + output.replace("\n", "\n  "), flush=True)
            if step.kind in ("assess-app", "assess-dmg"):
                check_assessment(result.returncode, output, notarized=notary is not None)
            elif step.kind == "notarize":
                # Read the verdict whatever the exit code: "Invalid" must not pass as done.
                try:
                    parse_notary_result(result.stdout or "")
                except SigningError as exc:
                    log = shlex.join(["xcrun", "notarytool", "log", "<submission id>", *(notary.args() if notary else [])])
                    said = f"\n  notarytool (exit {result.returncode}): {(result.stderr or '').strip()}" if (result.stderr or "").strip() else ""
                    raise SigningError(f"{step.label}: {exc}{said}\n  Apple's reasons: {log}") from None
            elif result.returncode != 0:
                raise SigningError(f"{step.label} failed (exit {result.returncode}):\n{output}")
            elif step.kind == "team":
                check_team(output, team_id)


@dataclass(frozen=True)
class ReleaseOptions:
    sign: bool = False
    notarize: bool = False
    dmg: bool = False
    dry_run: bool = False
    identity: str = ""
    notary_profile: str = ""
    local_test: bool = False


def _resolved_release(options: ReleaseOptions, env: Mapping[str, str]) -> tuple[Optional[str], Optional[NotaryAuth]]:
    """Validate the whole configuration before a minute of PyInstaller is spent."""
    if options.local_test and (options.notarize or options.dmg):
        raise SigningError("--local-test builds a signed app to launch on this Mac; it cannot be notarized or imaged")
    sign = options.sign or options.notarize or options.local_test
    identity = resolve_identity(env, options.identity, local_test=options.local_test) if sign else None
    notary = resolve_notary_auth(env, options.notary_profile) if options.notarize else None
    return identity, notary


def build_macos_app(*, install_to_applications: bool = True, release: Optional[ReleaseOptions] = None) -> Path:
    release = release or ReleaseOptions()
    root = _repo_root()
    env = dict(os.environ)
    identity, notary = _resolved_release(release, env)
    if release.dry_run:
        _print_dry_run(root, identity=identity, notary=notary, release=release, env=env,
                       install_to_applications=install_to_applications)
        return _dist_dir(root) / f"{APP_NAME}.app"
    if sys.platform != "darwin":
        raise RuntimeError("macOS app builds are only supported on macOS")
    _require_voice_io()
    _require_hook_metadata()
    with _build_lock(root):
        return _build_locked(root, install_to_applications=install_to_applications,
                             identity=identity, notary=notary, release=release, env=env)


def _plan_for(root: Path, *, identity, notary, release: ReleaseOptions, env: Mapping[str, str]) -> list[Step]:
    return plan_release(
        app=_dist_dir(root) / f"{APP_NAME}.app",
        work_dir=_build_dir(root),
        out_dir=_dist_dir(root),
        version=_app_version(root),
        entitlements=Path(_env_value(env, ENTITLEMENTS_ENV) or _entitlements_path(root)),
        identity=identity,
        notary=notary,
        dmg=release.dmg,
        team_id=_env_value(env, TEAM_ID_ENV),
        local_test=release.local_test,
    )


def _print_dry_run(root: Path, *, identity, notary, release: ReleaseOptions, env, install_to_applications: bool) -> None:
    print("dry run: nothing is built, signed or uploaded")
    spec_env = f"{IDENTITY_ENV}={shlex.quote(identity)} " if identity else ""
    print(f"[0] PyInstaller (run in this process)\n  $ {spec_env}pyinstaller --noconfirm --clean --distpath {_dist_dir(root)} "
          f"--workpath {_build_dir(root) / 'pyinstaller-work'} {_spec_path(root)}")
    run_plan(_plan_for(root, identity=identity, notary=notary, release=release, env=env), dry_run=True, notary=notary)
    if install_to_applications:
        print(f"[last] copy into {_applications_target()}")


def _build_locked(root: Path, *, install_to_applications: bool, identity=None, notary=None,
                  release: Optional[ReleaseOptions] = None, env: Optional[Mapping[str, str]] = None) -> Path:
    release = release or ReleaseOptions()
    env = env if env is not None else dict(os.environ)
    if identity:
        # The spec reads these (it runs in this process): PyInstaller then signs every
        # collected binary inside-out with this identity and the hardened runtime.
        os.environ[IDENTITY_ENV] = identity
        os.environ.setdefault(ENTITLEMENTS_ENV, str(_entitlements_path(root)))
        os.environ[STRICT_CODESIGN_ENV] = "1"  # the spec sets it too, for the environment-only path
        env = dict(os.environ)
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
    steps = _plan_for(root, identity=identity, notary=notary, release=release, env=env)
    if steps:
        run_plan(steps, notary=notary, team_id=_env_value(env, TEAM_ID_ENV))
    if install_to_applications:
        target_app = _applications_target()
        _install_app(built_app, target_app)
        return target_app
    return built_app


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build a real macOS app bundle for AbstractAssistant")
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Build under dist/macos but do not copy the app into /Applications",
    )
    parser.add_argument(
        "--sign",
        action="store_true",
        help=f"Sign with a Developer ID Application identity (--identity or {IDENTITY_ENV}), hardened runtime, "
        "packaging/macos/entitlements.plist; then codesign --verify and spctl --assess",
    )
    parser.add_argument(
        "--notarize",
        action="store_true",
        help=f"Sign, then notarize with notarytool and staple (credentials: --notary-profile / {NOTARY_PROFILE_ENV}, "
        f"or {ASC_KEY_ID_ENV} + {ASC_ISSUER_ID_ENV} + {ASC_KEY_PATH_ENV}|{ASC_KEY_P8_ENV})",
    )
    parser.add_argument(
        "--local-test",
        action="store_true",
        help="Sign with an Apple Development (or Developer ID) identity and the hardened runtime, verify, "
        "and print the launch test to run on this Mac; never notarized, never for distribution",
    )
    parser.add_argument("--dmg", action="store_true", help="Also build dist/macos/AbstractAssistant-<version>.dmg (signed and notarized with --sign/--notarize)")
    parser.add_argument("--identity", default="", help=f"codesign identity (overrides {IDENTITY_ENV})")
    parser.add_argument("--notary-profile", default="", help=f"notarytool keychain profile (overrides {NOTARY_PROFILE_ENV})")
    parser.add_argument("--dry-run", action="store_true", help="Check the configuration and print every command; build and run nothing")
    args = parser.parse_args(argv)
    if args.notarize and not args.sign:
        print("--notarize signs first (as with --sign)")
    release = ReleaseOptions(
        sign=args.sign, notarize=args.notarize, dmg=args.dmg, dry_run=args.dry_run,
        identity=args.identity, notary_profile=args.notary_profile, local_test=args.local_test,
    )
    try:
        app_path = build_macos_app(install_to_applications=not args.skip_install, release=release)
    except SigningError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"dry run: would build {app_path}" if args.dry_run else app_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

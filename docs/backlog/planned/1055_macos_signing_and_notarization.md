# 1055 — Sign and notarize the macOS app

> Package: abstractassistant
> Type: release
> Created: 2026-10-26
> Status: Planned
> Completed: N/A
> Priority: P1
> Labels: macos, packaging, signing, distribution

## Current code reality

`AbstractAssistant.app` (PyInstaller, `packaging/macos/AbstractAssistant.spec`) was ad-hoc signed
and not notarized: Gatekeeper blocks any downloaded copy, and the designated requirement was a bare
cdhash (`codesign -d -r-` on the 2026-09-27 bundle: `designated => cdhash H"3cc4…"`), so privacy
grants were tied to one build. Its id `ai.abstractcore.abstractassistant` was outside the Apple
family (`ai.abstractframework.assistant`, `.watchkitapp`, team `K3R4D6HP2A`).

Shipped 2026-10-26 (ADR 0006, Proposed), all off by default:

- bundle id `ai.abstractframework.assistant.mac` (spec + `build_macos_app.py`, kept equal by a
  test; nothing reads it at run time);
- `packaging/macos/entitlements.plist` (`allow-unsigned-executable-memory`, `device.audio-input`);
- the spec signs inside-out through PyInstaller with `ABSTRACTASSISTANT_CODESIGN_IDENTITY` when
  set (unset = the old build), and then forces `PYINSTALLER_STRICT_BUNDLE_CODESIGN_ERROR=1`;
- `build-macos-app --sign / --notarize / --dmg / --local-test / --dry-run`, with `--identity`,
  `--notary-profile`, the iPhone pipeline's `ASC_KEY_ID` / `ASC_ISSUER_ID` / `ASC_KEY_P8` (or
  `ASC_KEY_PATH`) and `TEAM_ID`. There is no outer `--deep` reseal (review fix 10). Every nested
  Mach-O is checked for the hardened runtime, a secure timestamp and the team. `--local-test`
  accepts an Apple Development identity for a launch test on this Mac and is never notarized;
- a preflight for `webrtcvad-wheels` (an environment without it failed 7 min 22 s into
  PyInstaller), and the floor `abstractvoice>=0.11.4`, the first release that installs it
  (PyPI metadata; abstractvoice commit `1e2c173`);
- `tests/basic/test_macos_signing.py` (40 tests, pure, run on Linux CI);
- the operator checklist `docs/macos-signing.md`, host-independent Apple steps first.

Proven locally: the entitlements lint; a PyInstaller 6.21 `.app` signed through the real executor
(ad-hoc identity, hardened runtime, the entitlements) verifies `--deep --strict`, carries
`flags=0x10002(adhoc,runtime)` and the new identifier; a tampered file fails verification and stops
the run; `spctl` rejects the ad-hoc build and the strict check fails it; the disk-image commands
produce a UDZO image.

Proven 2026-10-26 on probes signed by PyInstaller with this team's **Apple Development** identity
(PyInstaller 6.22.3, strict codesign; the probes, not AbstractAssistant, were launched):

- **Probe A** (libpython, PyQt5 and a platform plugin, numpy, cffi, pyobjc, PortAudio; the shipped
  entitlements): 115 Mach-O files, all hardened, timestamped, team `K3R4D6HP2A`. It launched
  with library validation on and every check passed, so `disable-library-validation` is not
  needed. The real `--local-test` plan ran on it: 115 checked, 0 wrong. The same check on an
  ad-hoc bundle failed 48 of 48.
- **Probe B** (the same app, `audio-input` only): everything still passed, so the callbacks do
  not need `allow-unsigned-executable-memory`.
- **Probe C** (llvmlite MCJIT): it runs with `allow-unsigned-executable-memory`. Without it, the
  process is SIGKILLed (137); the kernel logs `CODE SIGNING: … rejecting invalid page`.

Not proven: a Developer ID signature (the certificate was created in Xcode on 2026-10-26),
notarization, and a launch of AbstractAssistant itself signed.

## Scope and expected outcome

A downloaded `AbstractAssistant-<version>.dmg` (or `.zip`) opens on any Mac without the "cannot
verify the developer" dialog, keeps its microphone and Accessibility grants across updates, and is
produced by one command (later one protected CI job). Out of scope: the Mac App Store (ADR 0006
section 2), a shared sign-in with the iPhone/watch (section 4).

## Steps

| # | Step | Owner | Size |
|---|---|---|---|
| 1 | Accept or amend ADR 0006: the bundle id (before the first signed build, since a later change re-keys everyone's grants again) and Developer ID as the channel, zip or disk image | operator | S |
| 2 | Apple setup, `docs/macos-signing.md` Part 1: agreements, App ID `ai.abstractframework.assistant.mac`, Developer ID Application certificate (+ `.p12` backup), notary credentials (team key or `notarytool store-credentials`) | operator | S |
| 3 | **Rebuild the build environment before any signed build.** Neither this Mac's pyenv 3.12 (`webrtcvad` 2.0.10, not `webrtcvad-wheels`) nor the repo `.venv` (abstractassistant 0.12.3, no `webrtcvad-wheels`) can build. The fresh scratch venv of 2026-10-26 has the right VAD, but its `numba` 0.68 cannot import with NumPy 2.5.4 ("Numba needs NumPy 2.4 or less"), so a bundle built there ships a broken numba. Fix NumPy, or drop numba (step 5), then build unsigned | assistant seat | S |
| 3b | `build-macos-app --local-test` with the Apple Development identity; the launch test of `docs/macos-signing.md` (voice, spoken reply, hotkey, attachments, Open from the console) | operator + assistant seat | S |
| 4 | First `build-macos-app --notarize --dmg`; Part 3 checks on a second Mac (downloaded copy, quarantine on); launch smoke: tray, palette, voice conversation (microphone prompt), spoken reply (numba/JIT path), hotkey (Accessibility), attachments, Open from the gateway console (handover). Evidence in `docs/backlog/evidence/1055/` | operator + assistant seat | M |
| 5 | Drop `allow-unsigned-executable-memory`: its only measured need is llvmlite's JIT (probe C), and nothing in the app is known to import numba or librosa. Find who pulls them in (`unstructured`, via abstractcore media), exclude `numba`/`llvmlite` in the spec if no run-time path exists, remove the key, and re-run the step 3b launch test without it | assistant seat | S |
| 6 | `scripts/install.sh --purge` (framework root) also clears `~/Library/Preferences/ai.abstractframework.assistant.mac.plist` and `defaults delete ai.abstractframework.assistant.mac`, keeping the old id; extend `scripts/tests/test_install_user_path.sh` D5 | framework seat | S |
| 7 | Confirm the gateway's desktop detection and `open -a AbstractAssistant.app` with the new bundle (it finds by path and name, not id; check LaunchServices with an old bundle still in `~/Applications`) | gateway seat | XS |
| 8 | CI: a macOS job building the unsigned app on changes; a manual, main-only job in a protected environment (human approval, like `app-store`) with `MACOS_DEVELOPER_ID_P12` (base64) + password imported into a temporary runner keychain, and the existing `ASC_*` key; upload the notarized image as an artifact | assistant seat + operator (secrets) | M |
| 9 | Where downloads live and how a bundle install updates (the gateway's Update card manages the pip package only): e.g. GitHub Releases asset plus a "download the new version" note on the card for bundle installs | operator decision, then assistant + gateway seats | M |
| 10 | `hdiutil create` warns "deprecated, use `diskutil image create`" on macOS 27: switch when `diskutil image` is available on the minimum build host | assistant seat | XS |
| 11 | README / INSTALLATION: a download link once a notarized release exists | assistant seat | XS |

If the desktop host becomes Rust/Tauri 2 (ADR 0006 section 6), steps 1-2 carry over unchanged;
steps 3-5 and 8 are replaced by Tauri's bundler (`signingIdentity`, `APPLE_API_*`), with
entitlements reduced to `device.audio-input`.

## Validation and ADR state

`python -m pytest tests/basic/test_macos_signing.py tests/basic/test_build_macos_app.py`.

Each guard was mutation-checked; each of these breakages turns a test red:
- signing on by default, or no hardened runtime;
- an assessment that accepts anything, or an `Invalid` notarization passing;
- the key file left behind, or the bundle id drifting between spec and module;
- (review fixes) a `--deep` reseal restored, a nested check that ignores the runtime flag, an
  empty bundle passing, a development identity allowed for a release, the person-id parenthetical
  read as the team, no strict codesign in the build or the spec, a local test that can be
  notarized, and a dry run claiming a built app.

With `--notarize --dmg`, two submissions are kept on purpose (the app inside the image carries its
own ticket and opens offline; ADR 0006 section 5): review fix 12, declined.

ADR 0006 Proposed; ADR 0002/0005 unchanged.

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
- the spec signs with `ABSTRACTASSISTANT_CODESIGN_IDENTITY` when set (unset = the old build);
- `build-macos-app --sign / --notarize / --dmg / --dry-run`, with `--identity`, `--notary-profile`,
  the iPhone pipeline's `ASC_KEY_ID` / `ASC_ISSUER_ID` / `ASC_KEY_P8` (or `ASC_KEY_PATH`) and
  `TEAM_ID`; a preflight for `webrtcvad-wheels` (an environment without it failed 7 min 22 s into
  PyInstaller);
- `tests/basic/test_macos_signing.py` (33 tests, pure, run on Linux CI);
- the operator checklist `docs/macos-signing.md`, host-independent Apple steps first.

Proven locally: the entitlements lint; a PyInstaller 6.21 `.app` signed through the real executor
(ad-hoc identity, hardened runtime, the entitlements) verifies `--deep --strict`, carries
`flags=0x10002(adhoc,runtime)` and the new identifier; a tampered file fails verification and stops
the run; `spctl` rejects the ad-hoc build and the strict check fails it; the disk-image commands
produce a UDZO image. Not proven: a Developer ID signature, notarization, or a launch of a signed
build. No Developer ID identity exists on this Mac yet (only "Apple Development").

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
| 3 | A build environment that can build: neither this Mac's pyenv 3.12 (has `webrtcvad` 2.0.10, not `webrtcvad-wheels`) nor the repo `.venv` (abstractassistant 0.12.3, no `webrtcvad-wheels`) can build the bundle today. Fresh venv, `pip install -e ".[macos-app]"`, unsigned build, then `--sign` | assistant seat | S |
| 4 | First `build-macos-app --notarize --dmg`; Part 3 checks on a second Mac (downloaded copy, quarantine on); launch smoke: tray, palette, voice conversation (microphone prompt), spoken reply (numba/JIT path), hotkey (Accessibility), attachments, Open from the gateway console (handover). Evidence in `docs/backlog/evidence/1055/` | operator + assistant seat | M |
| 5 | Minimise entitlements on the signed build: try without `allow-unsigned-executable-memory` on every voice path; read Console for library-validation refusals; keep `--deep` on the outer seal only if notarization accepts it (Apple advises inside-out signing without it) | assistant seat | S |
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

`python -m pytest tests/basic/test_macos_signing.py tests/basic/test_build_macos_app.py`; each
guard mutation-checked (signing on by default, no hardened runtime, an assessment that accepts
anything, an `Invalid` notarization passing, the key file left behind, the bundle id drifting
between spec and module: each turns a test red). ADR 0006 Proposed; ADR 0002/0005 unchanged.

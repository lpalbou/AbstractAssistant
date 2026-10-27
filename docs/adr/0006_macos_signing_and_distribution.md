# ADR 0006 — Signing and distributing the macOS app

Status: Proposed (operator decisions open: the bundle id and the channel, see the end)
Date: 2026-10-26
Related: [ADR 0001](0001_gateway_native_assistant_v2.md) (thin client),
[ADR 0003](0003_unified_apple_product.md) and [ADR 0005](0005_one_apple_project.md) (the Apple family)

## Context

AbstractAssistant is a **cross-platform** desktop app: a Qt (PyQt5) tray and palette that runs from
`pip install abstractassistant` on macOS, Linux and Windows. On macOS it is also packaged as
`AbstractAssistant.app`, a PyInstaller bundle (`packaging/macos/AbstractAssistant.spec`, built by
`build-macos-app`). That bundle has always been **ad-hoc signed and not notarized**: it runs on the
machine that built it, but Gatekeeper blocks a copy downloaded anywhere else ("cannot verify the
developer"), and its designated requirement is a bare code hash
(`codesign -d -r-` → `designated => cdhash H"…"`), so macOS privacy grants (microphone,
Accessibility for the hotkey) are tied to one build and are asked again after a rebuild.

Signing and notarization are a **macOS distribution concern layered on that cross-platform app**.
Nothing in the app reads its bundle id at run time (the id appears only in the spec and in
`abstractassistant/build_macos_app.py`), and nothing added here is imported by the app: the Linux
and Windows runs, and the source-run macOS tray, are unaffected.

The iPhone and watch apps are one Apple product on team `K3R4D6HP2A`: `ai.abstractframework.assistant`
(iOS), `….watchkitapp`, `….notifications`, app group `group.ai.abstractframework.assistant`, with
a credential-free CI and a human-approved App Store Connect upload (ADR 0002, ADR 0005). The Mac
bundles released through 0.14.3 carried the id of another namespace, `ai.abstractcore.abstractassistant`
(0.15.0, unreleased, is the first built with the new one).

## Decision

### 1. Bundle id: `ai.abstractframework.assistant.mac`

- **In the family namespace.** `ai.abstractframework.assistant` is the product; `ai.abstractcore`
  is the library's namespace, which the app outgrew with ADR 0001. Every Apple identifier of the
  product then shares one prefix under one team, which is what "the same product family" means
  to the developer portal, to App Store Connect and to anyone reading a crash report.
- **Not the iOS id itself.** Reusing `ai.abstractframework.assistant` would make the Mac app part
  of the iPhone + watch App Store record (Universal Purchase), which only exists through the Mac
  App Store, rejected below. A Developer ID app with the iOS app's id would put two unrelated
  binaries behind one identifier in Apple's records.
- **`.mac`, a plain suffix.** Short, says the platform, mirrors `.watchkitapp`. It is not an
  embedded bundle of the iOS app (Apple's prefix rule applies only to bundles embedded in a
  container), so the prefix imposes nothing on it. `.macos` would be equally valid; `.mac` is
  chosen for brevity.
- **Cost, paid once.** macOS keys privacy grants by bundle id and code requirement, so a new id is
  a new app to it: people grant the microphone and Accessibility (hotkey) again once. Today's
  ad-hoc builds already lose those grants at each rebuild (the cdhash requirement above). A
  Developer ID build's requirement is "this identifier, signed by this team", so the grants then
  survive every later update. The app's own state lives in `~/.abstractassistant`
  (`preferences.json`, `gateway_connection.json`, sessions), which the id does not name, so
  **nothing migrates**. Left behind: the Cocoa defaults domain
  `~/Library/Preferences/ai.abstractcore.abstractassistant.plist` (Cocoa/Qt defaults, not the
  app's settings).
- **Seam with the root installer.** `scripts/install.sh --purge` in the framework root (framework
  seat) deletes that plist and runs `defaults delete` by the old id; it must also clear the new id
  (and keep the old one for existing machines). Recorded in backlog 1055 step 6.

### 2. Channel: Developer ID + notarization, downloaded directly (zip or disk image)

The Mac App Store requires the App Sandbox (App Review Guideline 2.4.5(i)). The app, as it is, does
not fit in one:

| What the app does | Evidence | Under the App Sandbox |
|---|---|---|
| Global hotkey through a keyboard event tap, gated on Accessibility trust | `abstractassistant/hotkey.py` (`AXIsProcessTrusted`, pynput `keyboard` listener) | Apple lists "use of accessibility APIs in assistive apps" as incompatible with the sandbox, and a manual grant does not help a sandboxed app. A listen-only event tap under Input Monitoring, or a Carbon `RegisterEventHotKey` hotkey, would be allowed: a redesign, not a setting. |
| Finds the local gateway from `~/.abstractframework/gateway.json` | `abstractassistant/config.py` (`gateway_pointer_path`) | The sandbox makes `~` the app's container: the file is not there. |
| Receives its sign-in from a handover file in the gateway's data folder | `abstractgateway/docs/apps.md` (The Assistant), `controller.read_desktop_handover_file` | A file outside the container that no user picked: not readable. |
| Keeps its state in `~/.abstractassistant`, shared with the `assistant` CLI | `controller.py` (`data_dir`) | Moved into the container; the CLI and the app would stop sharing it. |
| Reveals and opens files the agent wrote anywhere in the workspace | `app.py` (`open -R`, `open -t`) | Only paths the user picked in an open panel are reachable. |
| Installed and updated by the gateway (`pip`, `open -a … --args`) | `abstractgateway/docs/apps.md` (Install, Update, Open) | The Store owns installs and updates. |

Tool execution is not on this list: tools run on the gateway (ADR 0001), not in the app.
PyInstaller and PyQt5 bundles can be sandboxed in principle; it is the behaviours above that would
each need a redesign or a temporary exception, which App Review discourages.

Developer ID needs no App Review. Notarization is Apple's automated check of a signed, hardened
build; the stapled ticket lets Gatekeeper open it offline. The artifacts are
`AbstractAssistant-<version>.zip` (stapled app) or `AbstractAssistant-<version>.dmg` (stapled image
holding the stapled app). The Mac App Store stays possible later, for a sandboxed redesign.

### 3. Hardened runtime entitlements (`packaging/macos/entitlements.plist`)

Notarization requires the hardened runtime on every executable, which turns off what a plain
Python process takes for granted. The file keeps only what the bundle needs:

| Entitlement | In | Why | What breaks without it |
|---|---|---|---|
| `com.apple.security.cs.allow-unsigned-executable-memory` | yes, for now | The bundle ships `llvmlite`/`numba` (pulled in by `unstructured`, an abstractcore media dependency; librosa is optional and absent), whose LLVM JIT writes code into pages it then executes. **Measured (probe C, 2026-10-26):** a PyInstaller app signed with this team's identity that JIT-compiles through llvmlite's MCJIT runs with the entitlement and is SIGKILLed without it (exit 137; kernel: `CODE SIGNING: … rejecting invalid page … signed:0`). Callbacks do NOT need it: cffi, ctypes and pyobjc-block callbacks, Qt, numpy and PortAudio all ran without it (probe B). No run-time path from the app into numba is known (no `numba`/`librosa` import in the app), so the better end state is to exclude numba/llvmlite from the bundle and drop the key (backlog 1055 step 5). | A JIT-compiling code path is killed at its first compile. Nothing else measured breaks. |
| `com.apple.security.device.audio-input` | yes | Voice conversations and dictation read the microphone (abstractvoice, PortAudio). `NSMicrophoneUsageDescription` is already in the spec's Info.plist. | The hardened runtime denies audio input and macOS never asks: recording returns nothing. |
| `com.apple.security.cs.disable-library-validation` | no | **Measured (probe A, 2026-10-26):** a PyInstaller 6.22 app with libpython, the PyQt5 frameworks and a platform plugin, numpy, cffi, pyobjc and sounddevice's PortAudio, signed by PyInstaller with this team's Apple Development identity, has 115 Mach-O files, every one re-signed by team `K3R4D6HP2A` with the hardened runtime and a secure timestamp. It launched with library validation on and every check passed. Third-party wheels' own signatures are replaced, so one team covers the whole bundle. Library validation compares teams, not certificate kinds, so a Developer ID build behaves the same. It is ad-hoc signing that fails: a hardened ad-hoc bundle cannot load its own libpython (adversarial review, "different Team IDs"), which is why the local test needs a real identity. | Only code from outside the bundle, signed by another team, fails to load. Known case: `python-magic` looks for Homebrew's `libmagic` in `/opt/homebrew/lib`, an optional library a clean Mac does not have either (python-magic then raises `ImportError`, as on a clean Mac). |
| `com.apple.security.cs.allow-dyld-environment-variables` | no | Nothing in the app or PyInstaller's bootloader sets `DYLD_*`. | `DYLD_*` variables are ignored (debugging only). |
| `com.apple.security.automation.apple-events` | no | `osascript -e "get volume settings"` (output-volume banner) sends no Apple event to another app. | If it were needed: the volume hint disappears (best-effort, already optional). |
| `com.apple.security.get-task-allow` | never | Debugger attachment. | Notarization refuses it. |
| `com.apple.security.app-sandbox` | never | Not a Mac App Store build (section 2). | n/a |

The Accessibility grant (hotkey) is not an entitlement: it is the user's choice in System Settings,
kept per bundle id and code requirement.

### 4. No shared sign-in with the iPhone and watch

The iPhone and watch apps each keep their sign-in as a Keychain item in the access group
`group.ai.abstractframework.assistant`, shared with that device's notification extension (and the
watch's complication), never between devices (ADR 0005, amended 2026-10-26). The Mac app does not
join it:

- the Mac app is a Python package, and the framework's rule for its Python packages is no OS
  keychain, the same credential store on Linux, Windows and macOS (the operator's ruling recorded
  in backlog 1053 and commit 489f1e9). It keeps `~/.abstractassistant/gateway_connection.json`,
  written owner-only (`preferences.py`, `JsonStore._write`);
- there is nothing on the Mac to share with: an app group or keychain access group does not cross
  devices, and the iPhone and watch keep theirs on their own devices;
- the Mac gets its sign-in from the gateway's desktop handover (a one-time code in a 0600 file,
  `abstractgateway/docs/apps.md`), which already works without any shared store;
- joining would need the data-protection keychain and a provisioning profile carrying the app
  group, which a Developer ID app otherwise does not need.

So the Mac App ID needs no capability and the build needs no provisioning profile. A native Mac
client (Swift, or the Rust host below) may revisit this.

### 5. The build: off by default, explicit when asked

- `packaging/macos/AbstractAssistant.spec` reads `ABSTRACTASSISTANT_CODESIGN_IDENTITY` (and
  optionally `ABSTRACTASSISTANT_ENTITLEMENTS`). Unset: exactly the old unsigned build. Set:
  PyInstaller signs **inside-out**, every collected binary first, then the bundle, with that
  identity, the hardened runtime, a secure timestamp and the entitlements. The spec then forces
  `PYINSTALLER_STRICT_BUNDLE_CODESIGN_ERROR=1`, because without it PyInstaller only warns when
  sealing the bundle fails (`PyInstaller/building/osx.py`, BUNDLE), which would let the
  environment-only path ship a broken seal.
- **No second signing pass.** An outer `codesign --force --deep` would *replace* every nested
  signature (`man codesign`: `--deep` is "DEPRECATED for signing as of macOS 13.0 … almost never
  what you want"), so `build-macos-app` does not reseal. It verifies what PyInstaller made:
  `codesign --verify --deep --strict` (verification with `--deep` is not deprecated),
  `codesign -dv` (checked against `TEAM_ID` when set), the entitlements, then **every nested
  Mach-O** (found by magic number) for the hardened runtime, a secure timestamp and the team. That
  last check is the notarization requirement, and a bundle with no binaries fails it. One caveat:
  PyInstaller's own BUNDLE step passes `--deep` when sealing the bundle (`sign_binary(…,
  deep=True)`), with the same identity, flags and entitlements as its per-binary pass, so the
  replacement there is like for like. Measured on probe A: 115/115 nested binaries correct.
- `build-macos-app --sign` (Developer ID only) runs those checks, then `spctl --assess`. Signed
  but not notarized, the one accepted answer is "Unnotarized Developer ID".
- `build-macos-app --local-test` accepts an **Apple Development** identity as well (never ad-hoc,
  never an App Store certificate). It runs the same checks, skips Gatekeeper (saying so) and
  prints the launch test. It cannot be combined with `--notarize` or `--dmg`. This is how the
  entitlements are tested on this Mac before any Developer ID build.
- `--notarize` (signs first) zips with `ditto`, runs `xcrun notarytool submit --wait`, reads the
  JSON verdict (anything but `Accepted` fails, naming the submission for `notarytool log`),
  staples and validates the ticket, then requires Gatekeeper's "Notarized Developer ID".
  Credentials: a notarytool keychain profile (`ABSTRACTASSISTANT_NOTARY_PROFILE`), or the iPhone
  pipeline's App Store Connect key names `ASC_KEY_ID`, `ASC_ISSUER_ID` and `ASC_KEY_P8` (key text,
  written to a private temporary file only for the submission), or `ASC_KEY_PATH`.
- `--dmg` builds the disk image (signed, notarized and stapled with the flags above);
  `--dry-run` validates the configuration and prints every command, running none. With
  `--notarize --dmg` the app is notarized and stapled *before* the image is built, then the image
  is notarized and stapled: two submissions, not one. One dmg submission would cover the app's
  code too, but a ticket cannot be stapled into an image after it is built, so the app inside
  would carry none and would need Apple's servers the first time it is opened after being copied
  out. Minutes of notary time buy an app that opens offline.
- Every step prints the command it runs and stops on the first failure with the tool's output. A
  configuration that cannot work is refused before PyInstaller starts: no identity, an Apple
  Development certificate without `--local-test`, ad-hoc, a partial API key, a Developer ID team
  other than `TEAM_ID`. So is a build environment without `webrtcvad-wheels`.

The operator's checklist is [docs/macos-signing.md](../macos-signing.md); the remaining steps are
backlog 1055.

### 6. If the desktop host becomes Rust (Tauri 2)

The operator is considering a Rust desktop host (Tauri 2 around the web front end). Most of this
ADR does not depend on the host:

- **Unchanged, done once:** the bundle id `ai.abstractframework.assistant.mac` (keep it, so the
  privacy grants and the App ID carry over), the Developer ID Application certificate, the Team ID,
  the notarization credentials (an App Store Connect team key or a notarytool profile), the
  channel decision, and the no-shared-sign-in decision for as long as the credential store follows
  the framework's no-keychain rule.
- **Tauri does the signing itself.** `bundle.identifier` and `bundle.macOS.signingIdentity` in
  `tauri.conf.json` (or `APPLE_SIGNING_IDENTITY`); `bundle.macOS.hardenedRuntime` defaults to
  `true`; `bundle.macOS.entitlements` names the plist. On CI it imports the certificate from
  `APPLE_CERTIFICATE` (base64 `.p12`) and `APPLE_CERTIFICATE_PASSWORD`. It notarizes and staples
  during `tauri build` when `APPLE_API_ISSUER`, `APPLE_API_KEY` (key id) and `APPLE_API_KEY_PATH`
  are set (or `APPLE_ID`, `APPLE_PASSWORD`, `APPLE_TEAM_ID`). These map one-to-one onto
  `ASC_ISSUER_ID`, `ASC_KEY_ID` and the `.p8`; only the variable names differ.
- **Different entitlements.** A WKWebView app runs JavaScript's JIT in WebKit's own Apple-signed
  processes and loads no third-party dylibs, so it needs neither
  `allow-unsigned-executable-memory` nor `disable-library-validation`. It keeps `audio-input`
  (microphone through `getUserMedia` or native capture) with `NSMicrophoneUsageDescription`, and
  adds `com.apple.security.network.client` only if it is ever sandboxed (Mac App Store).
- **The channel question reopens.** A Rust host that registers its hotkey with Carbon, keeps its
  state in its container and takes its sign-in in the app could be sandboxed, which would make the
  Mac App Store, and Universal Purchase with the iPhone record, a real option. That would be a new
  decision, with its own bundle-id question.

## Consequences

- One rebuild re-keys the privacy grants (microphone, Accessibility) once; with Developer ID they
  then persist across updates.
- The unsigned local build is unchanged; signing is opt-in per build.
- Notarizing needs network access to Apple and an Apple Developer Program membership; it is
  performed by a human (or a protected CI job, backlog 1055), never on a push.
- The gateway's Install/Update cards keep managing the pip package; a downloaded signed `.app`
  has no update channel of its own yet (backlog 1055).
- Signing is PyInstaller's inside-out pass alone (section 5), with no outer `--deep` reseal, and
  every nested binary is checked rather than trusted. The first proposal resealed with
  `codesign --force --deep`, which replaces every nested signature; it was dropped after review.
- `allow-unsigned-executable-memory` stays only while numba/llvmlite are bundled. Excluding them
  (no known run-time path) removes the last reason for it.

## Operator decisions (to accept this ADR)

1. The bundle id `ai.abstractframework.assistant.mac` (or name another one before the first signed
   build: after it, a change costs everyone another round of privacy grants).
2. Developer ID + notarization as the channel, and zip or disk image as the download.

## References

- [Operator checklist](../macos-signing.md), [backlog 1055](../backlog/planned/1055_macos_signing_and_notarization.md)
- [iPhone distribution](../../phone/iphone/docs/distribution.md) (secrets, team, approval gate)
- Apple: [Notarizing macOS software before distribution](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution),
  [Hardened Runtime](https://developer.apple.com/documentation/security/hardened-runtime),
  [App Sandbox](https://developer.apple.com/documentation/security/app-sandbox),
  [App Review Guidelines 2.4.5(i)](https://developer.apple.com/app-store/review/guidelines/),
  [Protecting user data with App Sandbox](https://developer.apple.com/documentation/security/protecting-user-data-with-app-sandbox)
  ("Review functionality that is incompatible with App Sandbox"),
  Developer Forums on Accessibility in sandboxed apps ([749494](https://developer.apple.com/forums/thread/749494),
  [780626](https://developer.apple.com/forums/thread/780626)), on notarytool team keys
  ([768634](https://developer.apple.com/forums/thread/768634))
- PyInstaller: `PyInstaller/utils/osx.py` `sign_binary` (`--options=runtime --timestamp`), 6.21.0
- Tauri 2: [macOS code signing](https://v2.tauri.app/distribute/sign/macos/), [configuration](https://v2.tauri.app/reference/config/)

# Signing and notarizing the macOS app

`build-macos-app` builds `AbstractAssistant.app` **unsigned** by default (ad-hoc signed by
PyInstaller): fine on the Mac that built it, blocked by Gatekeeper anywhere else. This page is the
operator's checklist for a **Developer ID signed, notarized** build that anyone can download and
open. The decision behind it (bundle id, channel, entitlements) is
[ADR 0006](adr/0006_macos_signing_and_distribution.md); the remaining work is
[backlog 1055](backlog/planned/1055_macos_signing_and_notarization.md).

Signing is macOS packaging only. AbstractAssistant itself is a cross-platform Qt app: nothing
here changes how it runs from `pip` on Linux, Windows or macOS.

- Bundle id: **`ai.abstractframework.assistant.mac`** (the AbstractAssistant Apple family: the
  iPhone app is `ai.abstractframework.assistant`, the watch app `….watchkitapp`)
- Team: the family's team, **`K3R4D6HP2A`** (as in the [iPhone pipeline](../phone/iphone/docs/distribution.md))
- Channel: Developer ID + notarization, downloaded directly (not the Mac App Store)

## What this Mac already has (2026-10-26)

So that nothing below is redone. Names only; no secrets are kept in this repository.

- **Developer ID Application: Laurent-Philippe Albou (K3R4D6HP2A)**, created in Xcode on
  2026-10-26 and in the login keychain (`security find-identity -v -p codesigning` lists it).
  Part 1 step 4 is done, except the `.p12` backup.
- **Apple Development: Laurent-Philippe Albou (…)**, also team `K3R4D6HP2A` (measured on a
  signed probe: `TeamIdentifier=K3R4D6HP2A`). It is the identity for the local launch test below,
  never for a release.
- **Apple Distribution**: issued on 2026-10-16, but its `.cer` was never imported, so Keychain
  shows it as "Not in Keychain". It is a Mac/iOS **App Store** certificate: not needed for this
  app (ADR 0006 section 2).
- `~/Desktop/apple-csr/` (`make-csr.sh`, `import-certificates.sh`) and `~/.apple-signing/keys/`:
  the 2026-10-16 certificate-request scripts and the private keys they generated.
- `untracked/apns/` holds the **APNs push key** (`.p8` with a key id and team id, no issuer). It
  is **not** an App Store Connect API key and cannot notarize.
- The **App Store Connect team API key** exists only as the GitHub secrets `ASC_KEY_ID`,
  `ASC_ISSUER_ID`, `ASC_KEY_P8` (the iPhone pipeline's `app-store` environment). A secret cannot
  be read back from GitHub, so local notarization needs its own credentials (Part 1 step 5).
- The build environment: this Mac's pyenv Python and the repo `.venv` cannot build the bundle (no
  `webrtcvad-wheels`; and `numba` there refuses NumPy 2.5: "Numba needs NumPy 2.4 or less").
  **Rebuild the build venv before any signed build** (Part 2).

## Part 1 — Apple account setup (once, whatever builds the app)

These steps do not depend on how the app is built. If the desktop host later changes (for
example to a Rust/Tauri 2 shell, ADR 0006 section 6), **keep the same bundle id and reuse
everything made here**; only Part 2 changes.

1. **Account Holder or Admin of team `K3R4D6HP2A`** in the Apple Developer Program. Accept any
   pending agreements in the [developer account](https://developer.apple.com/account) and in App
   Store Connect, or certificate creation and notarization are refused.
2. **Find the Team ID**: developer account → Membership details → Team ID. It must be
   `K3R4D6HP2A`, the iPhone app's team, for the Mac app to be in the same family.
3. **Register the App ID** (reserves the identifier for the family; the current build needs no
   capability and no provisioning profile): Certificates, Identifiers & Profiles → Identifiers →
   **+** → App IDs → App → Platform **macOS** → Description "AbstractAssistant for Mac" →
   Bundle ID **Explicit** `ai.abstractframework.assistant.mac` → Capabilities: none → Register.
   Do not enable App Groups or Keychain Sharing: the Mac app does not share the iPhone/watch
   sign-in (ADR 0006 section 4).
4. **Create the "Developer ID Application" certificate** (only Account Holder or Admin can):
   1. On the Mac that will sign: Keychain Access → Certificate Assistant → *Request a Certificate
      From a Certificate Authority…* → your email, "Saved to disk" → `CertificateSigningRequest.certSigningRequest`.
      (Or Xcode → Settings → Accounts → the team → Manage Certificates → **+** → Developer ID
      Application, which does all of this.)
   2. Certificates → **+** → **Developer ID Application** → profile type **G2 Sub-CA** → upload the
      request → download `developerID_application.cer` → double-click to add it to the login
      keychain.
   3. Check: `security find-identity -v -p codesigning` lists
      `"Developer ID Application: <Name> (K3R4D6HP2A)"`. That quoted string is the identity.
   4. Back it up: Keychain Access → My Certificates → the certificate with its private key →
      Export → `.p12` with a strong password, stored in your password manager. It is the only
      copy of the private key; Apple allows a handful of Developer ID certificates per team.
   - "Developer ID **Installer**" is needed only for a `.pkg` installer. This app ships as a zip
     or a disk image, so skip it.
5. **Notarization credentials, one of** (the Apple ID + app-specific password method also exists,
   but team keys are what the iPhone pipeline already uses):
   - **App Store Connect team API key (recommended, works on CI too).** App Store Connect → Users
     and Access → Integrations → App Store Connect API → **Team Keys** → Generate → role
     **Developer** is enough for notarization (an *Individual* key cannot notarize). Note the
     **Key ID** and the **Issuer ID**, download `AuthKey_<KEYID>.p8` (downloadable once). The
     iPhone pipeline's existing team key (`ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_KEY_P8` in the
     `app-store` GitHub environment) already has a higher role and works as-is.
   - **A notarytool keychain profile (local only).** Saves the credentials in your login keychain
     under a name:
     ```bash
     xcrun notarytool store-credentials abstractassistant-notary \
       --key ~/private/AuthKey_<KEYID>.p8 --key-id <KEYID> --issuer <ISSUER-UUID>
     ```
     (or `--apple-id <email> --team-id K3R4D6HP2A --password <app-specific password>`).
   Check either with `xcrun notarytool history --keychain-profile abstractassistant-notary`
   (or `--key … --key-id … --issuer …`).

The certificate and the notary profile live in **your** login keychain, used by Apple's own
tools. That is not in conflict with the framework's no-keychain rule, which is about where its
Python packages keep credentials at run time; the app still keeps its gateway sign-in in
`~/.abstractassistant/gateway_connection.json`.

## Part 2 — Build, sign, notarize (the PyInstaller app of today)

Set the variables once per shell (these names are the iPhone pipeline's where one exists):

| Variable | Value | Needed for |
|---|---|---|
| `ABSTRACTASSISTANT_CODESIGN_IDENTITY` | `Developer ID Application: <Name> (K3R4D6HP2A)` (or its SHA-1) | `--sign` (or pass `--identity`) |
| `TEAM_ID` | `K3R4D6HP2A` | optional: refuses an identity or a signed app of another team |
| `ABSTRACTASSISTANT_NOTARY_PROFILE` | `abstractassistant-notary` | `--notarize` with a keychain profile (or pass `--notary-profile`) |
| `ASC_KEY_ID`, `ASC_ISSUER_ID` | the team key's Key ID and Issuer ID | `--notarize` with an API key |
| `ASC_KEY_PATH` **or** `ASC_KEY_P8` | path to `AuthKey_<KEYID>.p8`, or its text (CI) | `--notarize` with an API key |
| `ABSTRACTASSISTANT_ENTITLEMENTS` | another entitlements plist | optional, default `packaging/macos/entitlements.plist` |

Set a profile **or** an API key, not both (the build refuses an ambiguous setup). `ASC_KEY_P8` is
written to a private temporary file only for the submission, then deleted.

```bash
# In a FRESH venv (an old one may hold the pre-0.11.4 `webrtcvad`, or a numba/NumPy pair that
# cannot import; the build refuses the first, and the second ships a broken numba):
python3.12 -m venv ~/venvs/aa-build && . ~/venvs/aa-build/bin/activate
pip install -e ".[macos-app]"
python -c "import numba" || echo "numba cannot import here: fix NumPy before building"

# 1. See exactly what will run (checks the configuration, runs nothing):
build-macos-app --skip-install --notarize --dmg --dry-run

# 2. Signed only (a quick check; Gatekeeper answers "Unnotarized Developer ID", which is expected):
build-macos-app --skip-install --sign

# 3. Signed, notarized and stapled (needs the network; Apple usually answers within minutes):
build-macos-app --skip-install --notarize          # -> dist/macos/AbstractAssistant-<version>.zip
build-macos-app --skip-install --notarize --dmg    # -> dist/macos/AbstractAssistant-<version>.dmg
```

Drop `--skip-install` to also copy the signed app into `/Applications`. Each step prints the
command it runs and stops at the first failure with the tool's output. What the steps are:

1. PyInstaller signs inside-out: every bundled binary with the identity, the hardened runtime, a
   secure timestamp and the entitlements, then the bundle. The build forces
   `PYINSTALLER_STRICT_BUNDLE_CODESIGN_ERROR=1`, so a failed seal stops it.
2. There is no second `codesign --deep` pass (it would replace every nested signature; ADR 0006
   section 5). Instead the build checks:
   - `codesign --verify --deep --strict`;
   - `codesign -dv --verbose=4`;
   - the entitlements;
   - every nested Mach-O, for the hardened runtime, a secure timestamp and `TEAM_ID`.
3. For `--notarize`: `ditto` zip → `xcrun notarytool submit --wait` → `xcrun stapler staple` →
   `xcrun stapler validate`; then `spctl --assess`.
4. With `--dmg`, the image is built from the stapled app, then signed, notarized and stapled in
   turn. That makes two submissions, so that the app inside the image carries its own ticket and
   opens offline.

### Local launch test (this Mac, no notarization)

Run this before the first Developer ID build. It proves the entitlements and the library
validation for real: the hardened runtime behaves the same for a development identity of the
same team, and an ad-hoc build cannot run under it at all (its libpython is refused).

```bash
export TEAM_ID=K3R4D6HP2A
build-macos-app --skip-install --local-test \
  --identity "Apple Development: Laurent-Philippe Albou (<id shown by find-identity>)"
# then, from Terminal (so a crash prints), NOT from /Applications:
dist/macos/AbstractAssistant.app/Contents/MacOS/AbstractAssistant
```

Exercise:
- a voice conversation (macOS asks for the microphone);
- a spoken reply;
- the hotkey (grant Accessibility to this build);
- an attachment;
- Open from the gateway console.

If it quits, Console (or `log show --last 5m --predicate 'eventMessage CONTAINS "CODE SIGNING"'`)
names the page or library that was refused.

To test without a given entitlement, copy `packaging/macos/entitlements.plist`, remove the key and
build again with `ABSTRACTASSISTANT_ENTITLEMENTS=/path/to/copy.plist`. Measured on probes
(ADR 0006 section 3): without `allow-unsigned-executable-memory`, only llvmlite's JIT is killed;
Qt, numpy, PortAudio and the cffi/ctypes/pyobjc callbacks keep working.

## Part 3 — Verify (any signed build, any host)

```bash
APP=dist/macos/AbstractAssistant.app
codesign -dv --verbose=4 "$APP"       # Identifier=ai.abstractframework.assistant.mac, TeamIdentifier=K3R4D6HP2A,
                                      # flags=0x10000(runtime), Timestamp=… (a secure timestamp, not "Signed Time")
codesign -d --entitlements - "$APP"   # exactly allow-unsigned-executable-memory and audio-input
codesign --verify --deep --strict --verbose=1 "$APP"
spctl --assess --type execute --verbose=4 "$APP"   # accepted, source=Notarized Developer ID
xcrun stapler validate "$APP"                       # The validate action worked!
# the disk image:
spctl --assess --type open --context context:primary-signature --verbose=4 dist/macos/AbstractAssistant-<version>.dmg
xcrun stapler validate dist/macos/AbstractAssistant-<version>.dmg
```

Then open it on a Mac that did not build it (download it, so it carries the quarantine
attribute): it must open without the "cannot verify the developer" dialog. On first use, grant
the microphone and, for the hotkey, Accessibility. Because the bundle id is new, these are asked
once again even on a Mac that granted them to an older build. After that they persist across
signed updates.

## When it fails

| Symptom | Cause | Fix |
|---|---|---|
| `errSecInternalComponent` from codesign | the keychain is locked or the private key is missing | unlock the login keychain; re-import the `.p12` |
| `spctl`: `rejected` / `source=no usable signature` / not Developer ID | signed ad-hoc or with an Apple Development certificate | use the Developer ID Application identity (the build refuses the others up front; `--local-test` skips spctl on purpose) |
| notarytool `Invalid` | Apple found a problem | `xcrun notarytool log <submission id> <same credentials>`: the JSON names each file |
| notarytool 401/403 | an Individual API key, a revoked key, or an agreement to accept | a Team key with role Developer or higher; accept agreements |
| the signed app is killed (exit 137), log says `CODE SIGNING: … rejecting invalid page` | JIT-compiled code (llvmlite/numba) without `allow-unsigned-executable-memory` | keep the key while numba is bundled; check `codesign -d --entitlements -` |
| the build stops at "check every nested binary" | a binary without the hardened runtime, timestamp or team (e.g. built ad-hoc, or the identity not reaching PyInstaller) | rebuild with `--sign` / `--local-test`, not by setting the identity after the build |
| Console says `… not valid for use in process: mapping process and mapped file (non-platform) have different Team IDs` | a library from outside the bundle (e.g. Homebrew's libmagic) | expected for optional outside libraries; add `com.apple.security.cs.disable-library-validation` only if a **bundled** file is named (ADR 0006 section 3) |
| microphone silent, no prompt | `audio-input` entitlement or `NSMicrophoneUsageDescription` missing | both ship in the build; check the entitlements output above |
| hotkey does nothing | Accessibility not granted to this build | System Settings → Privacy & Security → Accessibility → enable AbstractAssistant |

## If the host becomes Tauri 2

Part 1 is unchanged. In Part 2, Tauri's bundler signs, notarizes and staples on its own during
`tauri build`: set `bundle.identifier` to `ai.abstractframework.assistant.mac`, and
`bundle.macOS.signingIdentity` (or `APPLE_SIGNING_IDENTITY`) to the same identity. The hardened
runtime is on by default (`bundle.macOS.hardenedRuntime`). For notarization set
`APPLE_API_KEY` = `ASC_KEY_ID`, `APPLE_API_ISSUER` = `ASC_ISSUER_ID` and `APPLE_API_KEY_PATH` =
the `.p8`'s path; on CI, also `APPLE_CERTIFICATE` (base64 `.p12`) and
`APPLE_CERTIFICATE_PASSWORD`. Its entitlements file needs only `com.apple.security.device.audio-input`:
a WebView app has no JIT or third-party libraries of its own. Part 3 is unchanged. See
[ADR 0006](adr/0006_macos_signing_and_distribution.md) section 6 and
[Tauri's macOS signing guide](https://v2.tauri.app/distribute/sign/macos/).

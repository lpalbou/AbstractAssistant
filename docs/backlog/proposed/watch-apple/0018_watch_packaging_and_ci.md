# Proposed: Packaging and CI for watch/apple: XcodeGen, sdist exclusion, macOS runner, TestFlight

> Created: 2026-10-16 22:30:00 +0200
> Type: task
> Priority: P2
> Labels: watch, ci, packaging

## Metadata
- Created: 2026-10-16
- Status: Proposed
- Completed: N/A
- Owning packages: abstractassistant
- Track: [watch-apple](README.md) (Apple Watch client)

## ADR status
- Governing ADRs: [ADR 0001](../../../adr/0001_gateway_native_assistant_v2.md) (gateway-native thin client: the gateway owns workflows, runs, tools, policy and speech)
- ADR impact: None. The watch is one more thin client of the same gateway contract.

## Summary
Keep the Swift sub-project out of the Python distribution, build it in CI on a macOS runner
(generate, package tests, simulator build, device compile, install smoke test), and prepare the
TestFlight path once the developer account is validated.

## Why
The repository ships a Python package to PyPI; the watch app ships through Apple. The two must
not interfere, and the Swift build must not depend on a developer's machine.

## Scope
- `MANIFEST.in`: `prune watch`; verify `python -m build` output.
- `.github/workflows/watch.yml` on `macos-26` (or the newest image with Xcode 26): `xcodegen generate`, `swift test`, simulator build, `generic/platform=watchOS` release build with `CODE_SIGNING_ALLOWED=NO`, `simctl install` smoke test; pick the simulator name dynamically.
- Versioning: `MARKETING_VERSION` in `project.yml`, a `watch/apple/CHANGELOG.md`, tags `watch-v0.1.0`.
- TestFlight: signing with the team id once enrolment completes; a fastlane lane or `xcodebuild -exportArchive` script; App Store assets (name "AbstractAssistant", bundle `ai.abstractframework.assistant.watch`).

## Non-goals
No App Store submission in this item; no code signing on CI until the account exists.

## Current code reality
- `pyproject.toml` includes only `abstractassistant*` packages; `MANIFEST.in` does not mention `watch/` yet.
- Existing CI for the Python package runs on Linux (see `.github/workflows`); no macOS job exists.
- The install smoke test matters: a missing `WKWatchOnly` passes the build and fails only at install (`untracked/watch/research/toolchain-check.md` §C).

## Dependencies
Item 0012.

## Expected outcomes
- A PR that breaks the watch build fails CI; the Python wheel never grows because of Swift files.

## Acceptance Criteria
- [ ] `python -m build` wheel and sdist contain no `watch/` paths
- [ ] The macOS workflow runs generate, test, simulator build, device compile and install smoke test, and is green on main
- [ ] `watch/apple/CHANGELOG.md` exists with 0.1.0

## Testing
- `python -m build && tar tzf dist/*.tar.gz | grep -c watch/`
- `gh workflow run watch.yml`

## Progress (2026-10-17)
- App Store packaging built: an empty iOS container target (`application.watchapp2-container`, bundle `ai.abstractframework.assistant`) carries the watch app; Release archive and App Store Connect export succeed (`watch/apple/scripts/testflight.sh`); privacy manifest, export compliance and version keys in place.
- Upload blocked only on the App Store Connect app record (created once by the account holder). CI remains open.

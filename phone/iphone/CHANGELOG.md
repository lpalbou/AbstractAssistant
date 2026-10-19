# iPhone release history

The native iPhone client has its own version and build number. Desktop package releases are
listed in the repository’s [Changelog](../../CHANGELOG.md).

## [Unreleased]

- Unified iPhone + independent Watch Store delivery through the existing AbstractAssistant listing, with one human-approved archive and preserved developer identities.

### Added

- iPhone CI runs package and native tests and retains an unsigned Release candidate. Manual
  App Store Connect uploads require full native tests and human approval. TestFlight builds
  remain eligible for manual same-build App Store promotion.

## [0.6.21] — 2026-10-18

### Fixed

- Generated images remain visible inline after reopening a conversation, restarting the app,
  closing an image preview or switching tabs. Message rows share their image downloads.
- Opening an image also prepares its inline preview. Cleared temporary files download again;
  failed image downloads offer **Try again**.

## [0.6.20] — 2026-10-18

### Changed

- The working orb has a brighter mint/lavender rim, visible moving ribbons and a colored Stop
  symbol. It morphs continuously between sphere and rounded square over 0.65 seconds, including
  when work ends during a transition. Reduce Motion retains clear static endpoints.

## [0.6.19] — 2026-10-18

### Added

- Tool categories offer **Off / Auto / Approve** controls in Settings, session overrides and
  automations. Mixed selections are labeled, and unavailable tools remain disabled.
- Conversations group into **Today / Yesterday / Earlier**, with two-line titles, compact
  statistics, last-activity times and **Working / Needs you / Failed** states.
- Finished conversations can be archived across devices and restored from **Archived**.

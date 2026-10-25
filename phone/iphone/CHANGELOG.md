# iPhone release history

The native iPhone client has its own version and build number. Desktop package releases are
listed in the repository’s [Changelog](../../CHANGELOG.md).

## [Unreleased]

## [0.7.0] — 2026-10-25

### Added

- Your event stream reaches the iPhone: the app catches up at launch and when it comes to the front,
  then follows the gateway live while it is in front. A new approval or question is a time-sensitive
  notification (a tap opens the Inbox), a new automation result a quiet one (a tap opens
  Automations); the Inbox and Automations tabs carry badges. Nothing from before the first look is
  notified, and a gateway without the stream keeps the regular refresh.
- Unified iPhone + independent Watch Store delivery through the existing AbstractAssistant listing,
  with one human-approved archive and preserved developer identities.
- iPhone CI runs package and native tests and retains an unsigned Release candidate. Manual
  App Store Connect uploads require full native tests and human approval. TestFlight builds
  remain eligible for manual same-build App Store promotion.

## [0.6.22] — 2026-10-19

### Added

- An orange session-approval shield beside Tools revokes temporary approvals in one tap.
  Approve tools ask again; Auto and Off settings remain unchanged. Tools lists active grants
  and offers explicit review of older grants saved as Auto.

- Automations can select any runnable Gateway workflow and configure its custom inputs on
  the phone. Create/Retry and Run now use mint primary-action styling.

- Speech preparation and transcription morph the orb into a rotating geodesic; tap to cancel.
  Tool approval morphs its cords into an orange raised hand that opens the three decision choices.

- Spoken messages open in the editable text composer by default. Settings → Voice & reading
  offers automatic sending as an account-scoped opt-in; typed drafts and attachments are preserved.


- Edit and resend confirmed stopped requests, including restored conversations and original
  attachments, while retaining the earlier turn and any separate composer draft.
- Separate required Title and task fields when creating an automation.


- Dated, tappable automation runs with explanations, attempt counts, recorded errors,
  task/trigger details and expandable activity. Results refresh while the screen is active.
- Settings shows the installed version/build, installation channel, Apple update controls,
  automatic-update instructions and the native version history.

### Fixed

- New questions and replies stay visible without a manual scroll. Following adapts to media,
  activity and keyboard layout changes; reading history offers a Latest messages action
  that hides automatically when you reach the bottom.

- Provider errors distinguish missing endpoints/models from authentication, and clarify that earlier failures describe recorded runs.

- Failed automation occurrences retain the gateway’s failure details, including provider
  credential errors. Empty answers no longer leave blank result headings or status-only cards.
- Latest runs and retry attempts stay grouped as one occurrence, and Run now cannot queue another occurrence while one is active.

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

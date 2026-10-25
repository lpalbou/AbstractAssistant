# iPhone release history

The iPhone app and its Apple Watch companion share one version and build number (since 0.16.0). Desktop package releases are
listed in the repository’s [Changelog](../../CHANGELOG.md).

## [Unreleased]

### Added

- **One product with the Apple Watch (version 0.16.0, build 39).** The iPhone app is now
  AbstractAssistant (`ai.abstractframework.assistant`, the existing App Store record) and carries
  the watch app as its companion (`ai.abstractframework.assistant.watchkitapp`). One project builds
  both, their watch face complication and two notification service extensions. The iPhone and the
  watch share one version from now on: 0.16.0 for both, the next number after the desktop app's
  0.15.0, so the family reads as one release line.
- **Sign in once.** After you sign in on the iPhone (account token or emailed code), the watch takes
  the same sign-in through WatchConnectivity. A watch without its iPhone still signs in on its own;
  the latest sign-in wins on either device.
- **Notifications while the app is closed (Apple push, framework backlog 1049).** The app registers
  itself with your gateway at each sign-in, on each new push token and at most once a day, and
  forgets the registration when you sign out; there is nothing to set up and no push setting (the
  system's notification permission is the switch, asked once after your first sign-in). The
  notification service extension reads the event from your own gateway and shows it as the app
  would: "Approval needed" / "A question for you" (time-sensitive, opens the Inbox), "<automation> has
  a result" / "<automation> failed" (opens Automations), a published alert with its title. A push for
  an earlier sign-in says "From an earlier sign-in"; when the gateway cannot be read in time, the
  generic text stays. Pushes are sent only once your gateway's push relay is on.
- **Sign a development iPhone in from the Mac (Debug builds only).** `scripts/deploy-phone.sh`
  builds the signed Debug app, installs it over CoreDevice and launches it with
  `--gateway URL --token TOKEN [--user ID]`: the app checks the token with GET /api/gateway/me,
  seals the sign-in, hands it to the watch and registers for push, as the account-token sign-in does;
  `--forget-gateway` clears it. `--console` shows the app's `phone-trace` lines (sign-in, watch
  handoff, push registration) and `--dump-trace` prints the last 40 at launch. Release builds
  compile all of this out.

### Changed

- **Your sign-in is sealed in the app's own storage, no longer in the iPhone Keychain** (ChaChaPoly
  under a private key file in the app group, readable by the notification extension; framework rule:
  no OS keychain). The earlier developer app `ai.abstractframework.assistant.iphone` is retired: sign
  in once in AbstractAssistant.
- A notification for an approval, a question or a result now has the same identifier as its push
  (the gateway's collapse id), and the app never shows again what a push already showed.

### Changed

- An automation says what starts it in words: "When mail arrives in you@example.org", "When Python
  news has a new item", "When Orders is called", "By hand", or the schedule's sentence (the gateway's
  own words when it serves them); one that runs when something happens shows no next run. A run the
  gateway retries reads "The gateway will retry this run."

## [0.7.0] — 2026-10-25

### Added

- Your event stream reaches the iPhone: the app catches up at launch and when it comes to the front,
  then follows the gateway live while it is in front. A new approval or question is a time-sensitive
  notification (a tap opens the Inbox), a new automation result a quiet one (a tap opens
  Automations); the Inbox and Automations tabs carry badges. Each notification shown is recorded on
  your event stream (`channel: "phone"`, this iPhone's device id). Nothing from before the first look
  is notified, and a gateway without the stream keeps the regular refresh.
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

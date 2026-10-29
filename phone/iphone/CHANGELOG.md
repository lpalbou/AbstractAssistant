# iPhone release history

The iPhone app and its Apple Watch companion share one version and build number (since 0.16.0). Desktop package releases are
listed in the repository’s [Changelog](../../CHANGELOG.md).

## [Unreleased]

### Fixed

- **An automation created on the iPhone runs unattended when its tools are set to Auto** (operator QA 2026-10-29, backlog
  1079).
  - Every automation was created with "ask before each tool" (`policy.tool_approval: "ask"`, hard-coded), although
    the screen offers no such choice and says the permissions "are saved with the automation so it can run while
    this iPhone is closed". Its runs parked on a tool approval for hours.
  - The approval now follows the tool modes you chose: "ask" only when a tool is on Ask. The per-tool modes still
    ride `policy.tool_policy`.
  - Automations created before this keep their "ask" setting. Their waiting runs say so; set their tools to Auto in
    the automation's Tools.

### Added

- **Your voices, the engine's and the shared ones (AbstractGateway 0.16.0 voice library).**
  Settings → Voice & reading → Voice lists the speaking voices in three groups: **Your voices**
  (the ones you cloned or designed), **Engine voices** and **Shared voices** (the gateway's
  built-in voices and the ones its administrator shares), each with its language. **Voices that
  speak…** keeps the voices of one language when the gateway offers several (a voice with no
  language restriction always stays), and the chosen voice shows its description.
- **Create a voice on the iPhone.** **Create a voice** (in Voice & reading and at the end of the
  voice list) makes one **from a description** (words, a name and a language; the gateway designs it
  with Qwen3-TTS, the first one can take a minute) or **from a recording**: record 5 to 20 seconds
  with the microphone, or choose a WAV, FLAC, OGG, MP3, M4A or WEBM file, with an optional
  transcript, a name and the language (**Detect from the recording** by default). The request runs
  with its progress shown and the app stays usable. The new voice becomes your assistant's voice
  when it speaks on the engine your assistant uses; otherwise the screen says which engine it was
  made on and where to choose it. When the assistant's voice is on a cloning engine (qwen3-tts,
  omnivoice, f5_tts, chroma, audiodit), the recording is cloned with that engine.
- **Rename and delete your voices.** Swipe left on one of Your voices to rename or delete it.
  Shared voices are read-only; a gateway that refuses (one shared voice store: an administrator's
  act; a read-only voice) says why in its own words.

### Changed

- **The voice list is read compact** (`GET /voice/voices?compact=true`, the same voices, about a
  fifth of the bytes). A UI test against a real gateway (`TEST_RUNNER_GW_URL`, `TEST_RUNNER_GW_TOKEN`)
  opens a conversation with its messages and plays a chosen voice's sample.

- **The sign-in lives in the Keychain, shared through the app group.** A Keychain item of the
  app's service, readable after the first unlock (the notification extension reads it while the
  device is locked), bound to this device, never in a backup, never synced; the app group doubles
  as the access group so the extension (and, on the watch, the complication) read the same item.
  A sign-in kept by an earlier build (a file in the app group) moves into the Keychain at its
  first read, so nobody signs in again. The watch's kept sign-ins moved from UserDefaults into a
  second Keychain item (backlog 1053).
- **A paused reading shows a speaker, not a play triangle.** The message's read-aloud button is a
  speaker at rest, pause while it reads and a filled speaker while paused (a tap resumes): a
  play triangle never stands for reading aloud, on the iPhone as on the watch.

- **One gateway client for the iPhone and the watch (backlog 1053 step 3).** `PhoneGatewayClient`
  is gone: the app and `AssistantKit` use the watch's `AbstractGatewayClient` package
  (`watch/apple/Packages/AbstractGatewayClient`), which now holds every route both apps call, and
  `WATCH_SNAPSHOT.json` is deleted (there is no snapshot any more). The iPhone keeps reading once
  (`readTries: 1`), its own persona (`AssistantPersona.iPhone`) and its demo data
  (`MockGatewayClient(world: .phone)`). For the iPhone: a query with a `+` reaches the gateway intact;
  the slow lists (automations, waits, runs) wait up to 45–60 s like the watch's; the newest turn of
  a conversation is the one created last, not the one updated last; the tool modes saved as
  `approve` read back as Ask. The package tests need macOS 26.

### Added

- **One product with the Apple Watch (version 0.16.0, build 39).** The iPhone app is now
  AbstractAssistant (`ai.abstractframework.assistant`, the existing App Store record) and carries
  the watch app as its companion (`ai.abstractframework.assistant.watchkitapp`). One project builds
  both, their watch face complication and two notification service extensions. The iPhone and the
  watch share one version from now on: 0.16.0 for both, the next number after the desktop app's
  0.15.0, so the family reads as one release line. The earlier developer app
  `ai.abstractframework.assistant.iphone` is retired. The iPhone and the watch sign in each on
  their own: neither hands its sign-in to the other, and neither needs the other's app.
- **Notifications while the app is closed (Apple push, framework backlog 1049).** The app registers
  itself with your gateway at each sign-in, on each new push token and at most once a day, and
  forgets the registration when you sign out; there is nothing to set up and no push setting (the
  system's notification permission is the switch, asked once after your first sign-in). The
  notification service extension reads the event from your own gateway and shows it as the app
  would: "Approval needed" / "A question for you" (time-sensitive, opens the Inbox), "<automation> has
  a result" / "<automation> failed" (opens Automations), a published alert with its title. A push for
  an earlier sign-in says "From an earlier sign-in"; when the gateway cannot be read in time, the
  generic text stays. Pushes are sent only once your gateway has a push forwarder.
- **Sign a development iPhone in from the Mac (Debug builds only).** `scripts/deploy-phone.sh`
  builds the signed Debug app, installs it over CoreDevice and launches it with
  `--gateway URL --token TOKEN [--user ID]`: the app checks the token with GET /api/gateway/me,
  keeps the sign-in and registers for push, as the account-token sign-in
  does; `--forget` clears it. `--console` shows the app's `phone-trace` lines (sign-in, push
  registration) and the app's `--dump-trace` launch argument prints the last 40.
  Release builds compile all of this out.

### Changed

- **The sign-in lives in the Keychain, shared through the app group.** A Keychain item of the
  app's service, readable after the first unlock (the notification extension reads it while the
  device is locked), bound to this device, never in a backup, never synced; the app group doubles
  as the access group so the extension (and, on the watch, the complication) read the same item.
  A sign-in kept in a file by an earlier build is moved into the Keychain at its first read, so
  nobody signs in again. The watch's kept sign-ins are a second Keychain item (backlog 1053).
- A notification for an approval, a question or a result has the same identifier as its push
  (the gateway's collapse id), and the app never shows again what a push already showed.
- **A paused reading shows a speaker, not a play triangle.** The message's read-aloud button is a
  speaker at rest, pause while it reads and a filled speaker while paused (a tap resumes): a
  play triangle never stands for reading aloud, on the iPhone as on the watch.
- An automation says what starts it in words: "When mail arrives in you@example.org", "When Python
  news has a new item", "When Orders is called", "By hand", or the schedule's sentence (the gateway's
  own words when it serves them); one that runs when something happens shows no next run. A run the
  gateway retries reads "The gateway will retry this run."

### Fixed

- **The Inbox badge counts what the Inbox shows.** It counted the larger of the Inbox's list and the
  open waits of your event stream, and the stream can hold a wait the list leaves out (a flow
  editor's draft-test run, which the gateway's run list omits), so the tab read "1" over "Nothing
  needs you". The badge is now the number of rows in the Inbox; the stream only tells the app to
  read the list again, once more if it changed while a read was under way.

### Known issues

- On a development build, a push can keep its generic words ("Approval needed", "Tap to read it")
  when the notification service extension does not replace them. The extension records why in the
  app group (read with the watch's `--dump-notify` readout); the item itself is in the Inbox or
  Automations when you open the app.

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

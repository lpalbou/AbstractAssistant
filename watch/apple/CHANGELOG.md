# Changelog — AbstractAssistant for Apple Watch

The watch app has its own version (`MARKETING_VERSION` in `project.yml`) and its own release
channel (TestFlight, then the App Store); the Python package's history is in
[../../CHANGELOG.md](../../CHANGELOG.md).

## [Unreleased]

### Added

- **New automation** (top of the Automations list): the task, the workflow that runs it ("Gateway
  default" first, then the workflows the gateway offers your account), when it runs (every 5 min,
  30 min, 1 h, 8 h, 24 h or 7 days, or daily at a time), whether each run builds on the earlier
  ones, and whether it asks before using tools; Create opens its page. The request is the one the
  console, the tray app and the terminal send.

- **Share** a web page's link from the icon beside Back (Messages, Mail, …). The share icon is one
  reusable control for any text or link; the watch has no clipboard, so sharing is how a text
  leaves it.
- **About → Contact** opens a new message to that address in the watch's Mail.

### Changed

- The orb is centred on the screen on the orb and read-aloud screens; the page opens at the top
  and scrolls only when there is text below the orb.
- Settings: **Read aloud** (was "Speak answers").
- **Sessions open on the right conversation, and say which.** Opening a session shows its title on
  the orb and its last exchange; a row shows the latest question under the title when the
  conversation has moved on; titles are longer (60 characters), so conversations that start alike
  stay apart; a conversation whose last turn is still working (or waits on an approval) shows it and
  follows it; one session opens at a time; a session's newest turn is the one created last.
- From Home, the orb opens on your current conversation's last exchange and its title.
- **Share on the orb**: beside Back, share the conversation as markdown; while the orb speaks (and
  between its sentences), go back 10 seconds.
- **The orb screen at rest and at work**: "Assistant ⌄" sits below the orb and the keyboard at the
  top right, both only while the orb is at rest; while it listens, works or speaks, neither shows
  (no ✕ either).
- The orbs draw 30% fewer points (smoother on every watch).
- **A more capable Assistant**: each question now offers the agent every tool the gateway has on
  (as the desktop assistant does; before, the workflow's 9 default file and code tools), read from
  the gateway before the first question if needed; and its instructions say when to use them (live
  information, the web, email and messages, files, actions) and never to claim it cannot browse.
  Sends to other people and risky tools still ask you first.
- Automation page: Edit sits beside Run now on the schedule line; Read aloud sits on the result's
  date line.
- **Settings → Voice**: choose the speaking voice and the transcription model among those the
  gateway offers (its default first). A voice plays a short sample when chosen (a spinner on its row while the gateway makes it). The choices stay on
  this watch and ride each request; the gateway's defaults are not changed. The speaking voice is
  the Assistant's; an entity keeps its own.
- **A conversation's page**: its last 5 exchanges in order, Show older for the rest, and Read aloud
  for the latest answer beside the title (as on an automation's page).
- **One voice button beside Back** (the orb page and Read aloud): a tap plays the selected message
  or pauses / resumes the one playing; holding it rewinds, about 4 seconds per second held at first
  and faster the longer it is held. It shares the orb's state (a tap on the orb pauses it too) and
  hides while the orb listens or works, or when there is nothing to read. It replaces the rewind
  icon.
- **The conversation under the orb**, as an automation's page: the last message in full (the one
  the voice button reads), then "Earlier messages" as cards, 5 at first and Show older for the
  rest; a card opens that message, with Read aloud.
- One look for every message: an automation's results and a conversation's messages share the
  same cards (a caption line, then the text at the same size) and the same page for one message.
- Round icons dip when pressed, so a tap visibly lands; text scrolled under the top row fades out.
- The icon beside Back (share, rewind) and Back itself take a tap on a real watch; a tap in that
  top row never reaches the orb.

## [0.2.0] - 2026-10-17

### Added

- **Automations, on the wrist.** Each automation shows how often it runs and when it runs next in
  one short line ("🕐 12h ➜ 6h"; a calendar rule reads Daily, Weekly or Monthly; Paused when
  paused). Its page shows the latest result in full, with Read aloud, Edit and Run now.
- **Run now with live progress.** While an automation runs, its page says what the agent is doing
  now ("Thinking…", "Searching the web…", "Reading 4 web pages…") with a running time; the play
  button becomes stop, the automations list shows a spinner on that automation, and a notification
  brings the result if you leave the app.
- **Edit an automation**: its task (the text field opens with the current task), how often it runs,
  whether each run builds on the earlier ones, active or paused. An automation named by its task
  keeps its name in step. A change made elsewhere meanwhile is refused instead of overwritten.
- **Earlier runs**: an automation's past runs at the end of its page (five at first, then ten more
  at a time), each opened in full and readable aloud.
- **Orb styles**: six orbs (Halo, Vortex, Nebula, Rings, Liquid, Galaxy), chosen at first launch
  and in Settings → Orb style. The orb fills the screen while it listens or speaks and swirls with
  the voice; the app icon is the orb at rest.
- **Entities have a look**: an entity's colour and shape (planet, kitty, face, wave), as set on the
  gateway, give its orb.
- **Rewind 10 seconds** while an answer is read aloud (the icon beside Back).
- **Settings → About**: the app's version and build, and the AbstractFramework links.

### Changed

- **The orb screen.** "Assistant ⌄" (top left) chooses who answers, the Assistant (a one-shot
  agent) or one of your entities (long-term discussions); a small keyboard icon (top right) types
  instead of speaking. The answer appears under the orb and is spoken by it, on the same screen.
- **Approvals** say what the assistant wants to do in plain words ("Run a command", "Send an
  email") with exactly what (the command, the page, the email), and offer three icons: deny, allow
  once and, from a conversation, allow all tools for the rest of it. Answering returns to where you
  were.
- **Plain words everywhere**: statuses ("Listening…", "Thinking…", "Needs you"), errors in one
  short sentence, no internal identifiers on screen.
- **Layout**: actions sit at the bottom of a screen that fits; sign-in fits one screen ("Sign in
  with user or email" with the send arrow inside the field); every round icon has the size and
  look of the Back button.
- **Sessions**: a conversation's exchanges open their full answer; a running exchange can be
  stopped from there.
- **Notifications**: no notification while the answer is already on screen (even dimmed); tapping
  an answer notification returns to the orb; a question notification opens the question.

### Removed

- The run steps screen and the "Allowed once" confirmation screen.

## [0.1.0] - 2026-10-17

First TestFlight build.

- Ask by voice around the orb (tap to talk, 3 seconds of silence sends, tap to pause or resume the
  spoken answer), with the gateway's speech-to-text and text-to-speech; markdown answers; links
  read inside the app.
- Approvals and questions from your agents, with per-conversation trust; email drafts in full
  before a send.
- Sessions with titles, resumed in one tap; automations with Run now.
- Sign-in with a user and token, or a registered email and a one-time code.
- Answers, approvals and questions as notifications while the app is closed; the app stays awake
  while it listens, works or speaks.

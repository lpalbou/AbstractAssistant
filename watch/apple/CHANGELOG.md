# Changelog — AbstractAssistant for Apple Watch

The watch app has its own version (`MARKETING_VERSION` in `project.yml`) and its own release
channel (TestFlight, then the App Store); the Python package's history is in
[../../CHANGELOG.md](../../CHANGELOG.md).

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

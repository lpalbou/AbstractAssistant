# Changelog — AbstractAssistant for Apple Watch

The watch app has its own version (`MARKETING_VERSION` in `project.yml`) and its own release
channel (TestFlight, then the App Store); the Python package's history is in
[../../CHANGELOG.md](../../CHANGELOG.md).

## [Unreleased]

## [0.3.0] - 2026-10-18

### Added

- **Its work, live, under the orb.** While the Assistant works, the space below the orb shows its
  steps, newest first on a thin rail: thinking (with its own words when it writes some), each tool
  with what it is about (the search, the page, the file, the command), an image or a recording
  being made, and a step waiting on you (tap it to decide). The status line says what it does now
  ("Searching the web…"). The conversation returns with the answer, which carries "9 steps · 0:11"
  to open every step in order.
- **The orb shows the work.** Each tool call sends a ring of light out from the planet (parallel
  calls a few tenths apart), each new thought a softer one, an image or a recording a slow wide
  wave; a failed tool makes it shiver, and every tool running circles the planet as a small
  satellite.
- **Tools you choose.** The tools icon on the orb page (bottom right, shown with the keyboard)
  opens this conversation's tools by group (Files, Web, System, Email, …): each tool Off, Auto or
  Ask, with its risk, what it can do and the gateway's description. A group's All sets its tools at
  once (All auto keeps the tools that reach outside, can destroy, or go where the assistant picks on
  Ask). **Settings → Tools** sets the defaults; a conversation's changes sit on top of them, and
  "Use my defaults" undoes them.
- **Accept all, taken back at once.** An approval's Accept all allows this conversation's tools on
  Ask, up to the risk of the call approved (sends and tools whose destination the assistant picks
  keep asking). The watch approves them for you while it follows the run; the amber shield on the
  orb, or **Ask again** on the Tools page, ends it, and the very next call asks.
- **A workflow per conversation; images and recordings in answers.** The **Workflow** row at the
  top of a conversation's Tools page chooses what answers: the gateway's default agent, the
  Assistant's workflows ("AbstractAssistant Orchestrator" also makes images and other media), or
  another agent; **Settings → Tools** sets the one new conversations use, and a conversation
  continued from another device keeps its workflow. An image shows under its answer (tap: full
  screen, the Digital Crown zooms, drag to look around, share); a recording plays through the orb
  right after the spoken answer; a video opens full screen.
- **Search your conversations.** Sessions has a search field: it finds the words in every
  conversation's questions, answers and artifacts (an image by what it was made from, an attachment
  by its name), parts of words too, accents ignored, a typo forgiven; found words are marked and a
  matching image is shown. It needs a gateway that serves `GET /api/gateway/sessions/search`.
- **Archive a conversation.** The archive button at the right of a conversation archives it on
  the gateway after a confirmation: it leaves Sessions on all your devices and nothing is deleted. **Archived**, at the
  bottom of Sessions, restores it.
- **What is new, at a glance.** Home's Sessions and Automations rows show what is new (answers you
  have not opened on this watch, automation results you have not seen) in a filled badge, else how
  many there are; a spinner holds the place until they are read. A conversation with a new answer
  is outlined in cyan, an automation with new results in amber.
- **Automations on and off, and archived, from the list.** Each automation has a switch (the
  gateway's pause and resume) and an archive button at its right: after a confirmation it stops and
  leaves Automations on all your devices, nothing deleted; **Archived**, at the bottom, restores it.
- **How many runs, and the instructions.** Each automation's line starts with how many times it
  has run ("⟳ 44  🕐 12h  ➜ 2h"), and its name takes up to two lines in the list. An automation's
  page shows its name and its instructions in full.
- **Edit an automation's title, task and instructions apart.** Edit has a Title, a Task and an
  Instructions field, each opening with the current text. A title that is the task follows the
  task until you edit the title itself. Leaving Edit with changes asks whether to save or discard
  them.
- **An automation opens at once the second time.** Its definition and latest results are kept once
  read: its page and Edit show them at once and read again only when the list says something
  changed; a saved edit shows on its page and in the list at once.
- **New automation** (top of Automations): the task, the workflow (the gateway's default by name),
  the tools it may use (the same page as a conversation's), when it runs (every 5 min to every 7
  days, or daily at a time) and whether each run builds on the earlier ones.
- **Settings → Connection**: the gateway and its status, the account you are signed in as and its
  role, its email, and how many tools are set up for it, with "Sign in as someone else". Email tools
  follow the account.
- **Settings → Voice**: the speaking voice and the transcription model among those the gateway
  offers, a sample when you choose, and **Speed** (Normal, 1.15×, 1.3×, 1.5×, same pitch). The
  choices stay on this watch.
- **One voice button beside Back**: a tap plays, pauses or resumes the selected message; holding it
  rewinds, faster the longer it is held.
- **Share** the conversation as markdown, or a web page's link, from the icon beside Back.
- **About → Contact** opens a message to the project in the watch's Mail.

### Changed

- The orb follows the voice itself, yours and the Assistant's: its loudness within the voice's own
  range and its spectrum in 8 bands; each orb style draws it. At full voice it reaches 8% less far.
- Read aloud speaks a whole answer from one request, in whole sentences and one language for the
  reply, and starts once 1.5 s of speech is ready.
- The conversation under the orb reads like an automation's page: the last message in full, then
  earlier messages as cards (5, then Show older), each opening on its own page with Read aloud. The
  whole history is read in one request; if it cannot be read, the page says so with Retry.
- Sessions open with **New** and **Search** side by side on one line.
- Sessions are titled by their latest question as the gateway has it (a grey placeholder while it
  is read) and say how long ago they last changed ("10 h ago"); opening one shows its last exchange
  first and follows a turn still working.
- Each question offers the agent every tool the gateway has on, with instructions on when to use
  them; sends to other people and risky tools still ask you first.
- An automation's page shows its latest result in full once read (a spinner meanwhile, Retry if it
  cannot be read); Edit sits beside Run now.
- The orb is centred on its screen, with "Assistant ⌄" below it and the keyboard at the top right
  while it is at rest; round icons dip when pressed; the orbs draw fewer points.
- Settings: **Read aloud** (was "Speak answers").

### Fixed

- Home shows a spinner in place of a count, and "Loading…" in place of its line, until that
  information is in: the automations (slow on some gateways) are read with up to 60 s per request
  and retried after 2, 4 and 8 s, and the conversation titles no longer wait for them.
- The automations list, the gateway's slowest call, is read at most once a minute while the app is
  open (an action reads it at once), instead of on every 15-second refresh.
- A read that times out, loses its connection or meets a server error is tried again (3 tries,
  after 1 s then 3 s) before a screen reports it; the spinner stays up meanwhile. An automation's
  latest results are read with up to 60 s per request. Actions (send, start, archive, save) are
  sent once.
- Opening the app no longer says the gateway cannot be reached while the watch's connection is
  still coming up: Home says "Connecting…" (animated) while the first tries fail and are retried
  every 3 s, and says the gateway is unreachable only after 3 failed tries over at least 20 s. The
  conversations are read with up to 45 s per request. A poll that fails once the app is connected is
  retried quietly.

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

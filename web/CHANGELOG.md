# Changelog: AbstractAssistant for the web

All notable changes to the web Assistant (`@abstractframework/assistant` on npm) are documented
in this file. It is versioned and released independently of the Python package, whose history is
in the repository [CHANGELOG](../CHANGELOG.md). Release tags for this package are `web-vX.Y.Z`.

## [Unreleased]

### Changed

- Relocked on the published kit: `@abstractframework/ui-kit` ^0.9.28 and `@abstractframework/panel-chat` ^0.9.12 from npm; every `src/vendor` snapshot re-synced to match them (session cards and gateway voice were behind).
- **An `@` mention is a chip inside the sentence** (operator, second test round 2026-11-10): picking a
  name puts it where the typed `@cas` was ("Hi @Castor how are you doing ?"), with the entity's orb,
  no ×; deleting it in the text removes the mention. The words sent carry each chip as "@Name". Needs
  `@abstractframework/panel-chat` 0.9.12 (AbstractUIC b1a1957): the vendored snapshots
  (`src/vendor/abstractchat`, `src/vendor/abstractdocs`) are re-synced from that local build until it
  is published, then relocked from npm.

## [0.2.0] - 2026-11-10

Mention your entities in a conversation, see who wrote each reply, and see what an entity's reply
kept. Built on `@abstractframework/ui-kit` 0.9.27 and `@abstractframework/panel-chat` 0.9.11 from
npm. Mentions, reply authors and the badges need AbstractGateway 0.21.0 or later; the Assistant
answering only its part beside the entities you mention also needs AbstractAgent 0.6.1 or later. On
an older gateway the app works as in 0.1.3: replies keep their "Assistant" header, and typing `@`
says "This gateway does not offer mentions yet."

### Added

- **Mention an entity with `@`.** Type `@` in the message box and pick one of your entities (the
  ones your gateway lists for you); it becomes a chip. When you send, each entity you mentioned
  answers in turn, in the order you picked them, and its answer appears in the conversation under
  its name. Your message shows once, and the answers to it appear in the order they came. The first
  time you pick a name in a conversation, a line reminds you that it will read this conversation's
  history. A name you already picked is not offered again, an entity picked twice is asked once, and
  the list spans the message box on a phone.
- **When a mention cannot be answered, you are told.** An entity already in another conversation is
  skipped with one sentence ("Castor is in another conversation.") and the next one is still asked.
  An entity that cannot answer says why, and your words go back to the message box with only the
  entities that did not answer still as chips. A gateway without mentions says "This gateway does
  not offer mentions yet" instead of listing names.
- **Sending the same words again asks only who did not answer.** After an entity could not answer,
  sending the same words again asks only the entities still shown as chips: the Assistant is not
  asked again and an entity that already answered is not asked twice. If an answer was lost on the
  way back (a timeout, a dropped connection), sending the same words again returns the answer the
  entity already gave instead of asking it again. Different words are a new message.
- **A mention sent while the Assistant is working is answered.** In the Avatar conversation view,
  a message with mentions sent while a reply is being written (it guides the running turn), or an
  answer to the Assistant's question, asks each entity your words, and the answers show after the
  running turn.
- **Every answer says who wrote it.** The top of each reply shows the agent's name (the workflow's
  name) or the entity's name and look, with a small "agent" or "entity" tag. It comes from the
  gateway, so a reload or another device shows the same. An entity's answer without a name reads
  "Entity". On an older gateway replies keep their "Assistant" header.
- **A message to your entities does not reach the Assistant; `@Assistant` asks it too.** A message
  that mentions entities goes to them only: the gateway keeps your words as a turn of the
  conversation and the Assistant does not answer (`agent: "not_addressed"` and the turn's `turn_id`
  on `POST runs/start`; each entity is asked with `repeat_of` naming that turn). One line above the
  message box says "The assistant stays out of this message.", and the conversation shows your words
  once, then the entities' answers, with no spinner, no empty reply and no "ended without a written
  reply" line (a turn marked `agent_addressed: false` in its view is never shown as waiting for a
  reply; after a reload its words show as they did live, from the turn's own fields, and the app
  asks no run's input for it: the turn is not a run). To ask the Assistant as well, pick **Assistant**, first in the `@` list (an "agent" chip,
  sent as the reserved `agent` in `mentions`, in the order you picked): it answers only the part
  meant for it, or says nothing. A message without mentions goes to the Assistant as always. A
  message with `@Assistant` is a new message, never a resend of a stopped one. A message sent while
  the Assistant is still working (the Avatar view) still guides its running turn.
- **What an entity's reply kept, as badges under its words.** When an entity keeps something from
  the exchange (a diary entry, a question, a lesson, an interest or a realization), its reply shows
  one badge for each under the text: the kind and its title. A private diary entry reads "private
  diary entry" and shows no words; one kept when a visit closes reads "forming…". Click a badge to
  read it whole. The badges come from the gateway with the reply, so a reload or another device
  shows the same.

### Changed

- **The tool permission card offers Deny, Allow and Allow All**, the shared card of AbstractUIC.
  The per-toolset "Allow all … tools for this chat" choice is gone.
- **Built on ui-kit 0.9.27 and panel-chat 0.9.11 from npm** (from ui-kit 0.9.16 and panel-chat
  0.8.2); the shared conversation bundled with the app is panel-chat 0.9.11's.

## [0.1.3] - 2026-11-07

On `@abstractframework/ui-kit` ^0.9.16 (AbstractUIC 0.10.3).

### Fixed

- **The avatar moves smoothly while it rests.** A finished or waiting avatar was redrawn only 6 to 10
  times per second; it now moves at 24 frames per second, like a speaking one, and a small avatar is
  drawn at its real size. The picture itself is unchanged.

## [0.1.2] - 2026-11-07

The 0.1.1 contents below, published. The `web-v0.1.1` tag exists but 0.1.1 never reached npm: the
release workflow passed the package path without `./`, so npm read it as a GitHub repository.

## [0.1.1] - 2026-11-07 (tagged, not published)

Voice in the browser is easier to trust: the avatar says it is speaking only while you can hear
it, and the Avatar conversation view has one set of voice controls. Built on AbstractUIC ui-kit
0.9.15 and panel-chat 0.8.2.

### Changed

- **One set of voice controls in the Avatar conversation view.** Talk with the composer's
  microphone, and play the latest line or a message with its own speaker button. The view no
  longer adds a second Talk button or its own Read new replies aloud, Pause voice and Silence
  voice buttons. Finished answers no longer carry an accent border.
- **New browsers start with the Watch Hover avatar** (it was Watch Halo). A design you already
  chose is kept.

### Fixed

- **The avatar shows Speaking only while you can hear it.** While speech is still being prepared,
  between streamed parts, or while the output is muted, the avatar does not claim to speak.
- **When the browser holds playback back**, read aloud no longer stays on "loading": the page says
  "Audio playback is paused by the browser. Press Play to try again.", and Play continues the same
  audio from where it stopped instead of preparing it again. The notice goes away once audio
  plays, when the browser resumes by itself, or when you press Stop.
- **Clicking a reply's speaker button again while its speech is being prepared** no longer starts
  a second synthesis of the same reply.
- **The open conversation stands out in the list**: its card is tinted and outlined in the accent
  colour, with a bolder title.

## [0.1.0] - 2026-11-03

First public release on npm. AbstractGateway lists it as **Assistant (web)** and installs it from
the npm registry (`abstractgateway apps install assistant-web`, or **Install** in the console and
tray Apps menu); you can also run it yourself with `npx @abstractframework/assistant`.
It is built on AbstractUIC ui-kit 0.9.14 and panel-chat 0.8.1 (shared bundles re-synced from them) and
AbstractAvatar 0.1.1.

### Added

- **Conversations in the browser.** Your gateway conversations, grouped by recency and searchable,
  with live answers, Stop, attachments, copy and export, rendered from the gateway's replay view.
  Requests that need you are listed first.
- **Voice.** A Watch-style animated orb: tap to talk (or hold, in Voice settings), dictation into
  the draft for review or sent automatically, read aloud that follows your voice setting, and
  playback controls. The composer microphone and the orb share one recording.
- **Avatar conversation view.** A second view over the same work. Under the avatar, one line shows the
  latest thing the assistant reports while it works, replaced as soon as something new arrives; click it
  to read it in full, then **Reply to this** or **Latest** (back to following). The findings it reports
  (facts or evidence it established) accumulate in a **Findings** panel beside the avatar, a sheet
  opened with **Findings** on a phone; each opens to the results it came from. The answer appears once,
  as a message. An open question or approval stays pinned at the top of the view with its buttons on
  screen, also on a laptop-height window (1000×650); on a very short view its context scrolls inside it
  while the heading and the buttons stay visible. Needs the producer-typed public updates of AbstractAgent (`kind`) and AbstractRuntime
  (`update_kind`); older updates are shown as progress. Permission requests use plain actions with the
  assistant's public explanation when the gateway serves one. The view holds no settings: they open
  from **Settings** in the conversations sidebar (behind **Open Conversations** on a phone), as
  everywhere in the app.
- **Approvals in the conversation.** Deny, Allow once, Allow for this chat or Decide later; a
  chat's tool policy is stored on the gateway when it offers one.
- **Avatar designs.** The 44-design AbstractAvatar catalog with previews of every activity state;
  your choice is kept in this browser. Only avatars with eyes (such as the Hover robot, the Eye, the
  Rover and the Watch faces and robots) look toward the pointer while Ready, and only their eyes
  move, easing back to centre after two idle seconds; the orb and every other avatar stay still.
- **Automations, as on the Apple Watch.** **Automations** beside Conversations lists them in the
  gateway's order: the active ones first, the most recently active at the top, then **Paused · N** and
  **Archived · N**, folded until opened (with an older gateway every automation is in one list).
  Search finds them by name. An automation's page shows how many times it ran, how often and when
  next, its task and its latest ten runs as a conversation; opening it marks its new results seen.
  **Run** starts a run now and **Stop** ends the run in progress. **Edit** changes its title, task,
  whether it is active, how often it runs and whether each run builds on the earlier ones (and how
  much of them it reads). Talking on its page opens a conversation about its latest run; a run
  waiting for you opens where you answer it; a tool request is answered on its page (**Deny**,
  **Approve all**, **Approve**), and **Approve all** lists the tools under **Allowed for its runs**,
  which this browser then approves when it sees them until **Ask again**. The archive button asks
  first and **Restore** brings an archived one back. **New** creates one: its task, the flow that
  runs it, its **Tools** (each Off, Ask or Auto, from the gateway's defaults), every interval from
  30 seconds to a week or every day at a time, and whether its runs build on each other.
- **Docs drawer.** Questions about the Assistant answered from its bundled browser guide, separate
  from your main conversation.
- **The app server** (`abstractassistant-web`): serves the built app on 127.0.0.1 (port 3008 by
  default) and under the gateway at `/apps/assistant-web/`, takes the shared app flags
  (`--gateway-url`, `--port`, `--host`, `--help`), and keeps the gateway session in an HttpOnly
  cookie so the page never holds a gateway token.

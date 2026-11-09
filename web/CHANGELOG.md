# Changelog: AbstractAssistant for the web

All notable changes to the web Assistant (`@abstractframework/assistant` on npm) are documented
in this file. It is versioned and released independently of the Python package, whose history is
in the repository [CHANGELOG](../CHANGELOG.md). Release tags for this package are `web-vX.Y.Z`.

## [Unreleased]

Built on panel-chat 0.9.9 and ui-kit 0.9.26 (AbstractUIC local builds, not yet published; panel-chat
packed from AbstractUIC aca0b07, both installed together `--no-save`). Mentions need an AbstractGateway
that has the mention door (not released yet).

### Added

- **Mention an entity with `@`.** Type `@` in the message box and pick one of your entities (the
  ones your gateway lists for you); it becomes a chip. When you send, the Assistant gets your
  message as usual, then each entity you mentioned answers in turn, in the order you picked them,
  and its answer appears in the conversation under its name. Your message shows once, and the
  answers to it appear in the order they came. The first time you pick a name in a
  conversation, a line reminds you that it will read this conversation's history.
- **When a mention cannot be answered, you are told.** An entity already in another conversation is
  skipped with one sentence ("Castor is in another conversation.") and the next one is still asked.
  An entity that cannot answer says why, and your message goes back to the message box. A gateway
  without mentions says "This gateway does not offer mentions yet" instead of listing names.
- **Every answer says who wrote it.** The top of each reply shows the agent's name (the workflow's
  name) or the entity's name and look, with a small "agent" or "entity" tag. It comes from the
  gateway, so a reload or another device shows the same. On an older gateway replies keep their
  "Assistant" header.
- **The Assistant leaves what you ask an entity to that entity.** A message that mentions entities
  now tells the gateway who is mentioned when it starts the Assistant's turn (`mentions` on
  `POST runs/start`, in the order you picked them). The Assistant answers only the part meant for
  it, or says nothing: then the conversation shows your words and the entities' answers, with no
  empty reply and no "ended without a written reply" line. Needs AbstractGateway main c26d38a2 or
  later, and an agent that accepts an empty reply (AbstractAgent still asks again today).

### Fixed

- **A mention sent while the Assistant is working is answered.** In the Avatar conversation view, a
  message sent while a reply is being written (it reaches the running turn, it starts no new one)
  was refused with "the gateway did not find your message in this conversation": its mentions
  named the running turn, whose words are an earlier message. They now name no earlier turn, so the
  entity is asked your words and its answer shows after the running turn. The same for an answer to
  the Assistant's question.
- **A mention is answered once, even when sent again.** Each mention now carries its own id (your
  message's turn, the entity, its place in the message). If the answer was lost on the way back (a
  timeout, a dropped connection) and you send the same words again, the gateway returns the answer
  the entity already gave instead of asking it twice; a new message is asked as new. Needs an
  AbstractGateway that keeps mention ids (main f0f23bb0 or later).
- **Mentions, client review 2026-11-09.** When an entity could not answer (503), the box keeps the words AND
  the chips not answered (they were dropped before), and sending the same words again asks only those entities,
  with the same `repeat_of` and their first `mention_index`: it no longer starts a second turn of the Assistant
  nor asks an entity that already answered. Other words are a new message. An entity picked twice is asked once.
  An entity's answer without a name reads "Entity", never "Assistant". Kit fixes from AbstractUIC 9aad042 and
  aca0b07 (vendored copy re-synced): a chip picked while a send is in flight stays, Enter waits while the `@` list
  loads, a picked name is not offered again, and the list spans the box on a phone.

### Changed

- **The tool permission card offers Deny, Allow and Allow All**, the shared card of AbstractUIC
  (operator ruling 2026-11-07). The per-toolset "Allow all … tools for this chat" choice is gone.

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

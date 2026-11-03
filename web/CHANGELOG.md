# Changelog: AbstractAssistant for the web

All notable changes to the web Assistant (`@abstractframework/assistant` on npm) are documented
in this file. It is versioned and released independently of the Python package, whose history is
in the repository [CHANGELOG](../CHANGELOG.md). Release tags for this package are `web-vX.Y.Z`.

## [Unreleased]

## [0.1.0] - 2026-11-03

First public release on npm. AbstractGateway lists it as **Assistant (web)** and installs it from
the npm registry (`abstractgateway apps install assistant-web`, or **Install** in the console and
tray Apps menu); you can also run it yourself with `npx @abstractframework/assistant`.
It is built on AbstractUIC ui-kit 0.9.13 and panel-chat 0.8.0 (shared bundles re-synced from them) and
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
  as a message. Needs the producer-typed public updates of AbstractAgent (`kind`) and AbstractRuntime
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

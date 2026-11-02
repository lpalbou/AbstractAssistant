# Changelog: AbstractAssistant for the web

All notable changes to the web Assistant (`@abstractframework/assistant` on npm) are documented
in this file. It is versioned and released independently of the Python package, whose history is
in the repository [CHANGELOG](../CHANGELOG.md). Release tags for this package are `web-vX.Y.Z`.

## [Unreleased]

### Changed

- **Avatar view captions.** The captions under the avatar are a realtime rolling list of the
  current turn's public updates, questions and answer, newest at the bottom, rendered like the
  conversation (Markdown, links, files); they no longer split an answer into pages that cycle, and
  the Previous / Next / Pause subtitle buttons are gone. The captions and the Conversation history,
  Talk and read-aloud buttons sit above the message box at every width.
- **No settings inside the Avatar view.** Its "Assistant settings" button is gone; settings open
  from **Settings** in the conversations sidebar (behind **Open Conversations** on a phone), as in
  the rest of the app. The history beside the avatar uses plain labels (You, Update, Question,
  Answer) and no longer lists technical source ids.

### Fixed

- The selected Conversation / Avatar tab is readable in the light theme.

## [0.1.0] - 2026-11-02

First public release on npm. AbstractGateway lists it as **Assistant (web)** and installs it from
the npm registry (`abstractgateway apps install assistant-web`, or **Install** in the console and
tray Apps menu); you can also run it yourself with `npx @abstractframework/assistant`.

### Added

- **Conversations in the browser.** Your gateway conversations, grouped by recency and searchable,
  with live answers, Stop, attachments, copy and export, rendered from the gateway's replay view.
  Requests that need you are listed first.
- **Voice.** A Watch-style animated orb: tap to talk (or hold, in Voice settings), dictation into
  the draft for review or sent automatically, read aloud that follows your voice setting, and
  playback controls. The composer microphone and the orb share one recording.
- **Avatar conversation view.** A second view over the same work: the avatar shows activity, short
  subtitles carry discoveries, choices and questions, and **Conversation history** opens the full
  exchanges. Permission requests use plain actions with the assistant's public explanation when the
  gateway serves one.
- **Approvals in the conversation.** Deny, Allow once, Allow for this chat or Decide later; a
  chat's tool policy is stored on the gateway when it offers one.
- **Avatar designs.** The 44-design AbstractAvatar catalog with previews of every activity state;
  your choice is kept in this browser.
- **Docs drawer.** Questions about the Assistant answered from its bundled browser guide, separate
  from your main conversation.
- **The app server** (`abstractassistant-web`): serves the built app on 127.0.0.1 (port 3008 by
  default) and under the gateway at `/apps/assistant-web/`, takes the shared app flags
  (`--gateway-url`, `--port`, `--host`, `--help`), and keeps the gateway session in an HttpOnly
  cookie so the page never holds a gateway token.

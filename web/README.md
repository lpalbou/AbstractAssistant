# AbstractAssistant for the web

The Assistant's conversation surface in a browser: your conversations, live answers, tool
approvals and questions in the conversation, attachments, `@` mentions of your entities, dictation
and read aloud. It is a thin
client of [AbstractGateway](../../abstractgateway/docs/apps.md): the gateway keeps every
conversation, runs the Assistant's workflow and holds your sign-in. This page keeps no token and
no copy of your chats; it keeps your display and voice preferences (appearance, panel widths,
voice overrides, devices, microphone mode) in this browser.

The Watch-inspired layout centres the interaction on a living avatar: tap it to
talk (or hold, if selected in Voice settings), tap while speaking to pause/resume,
and use Stop to end playback or the current request. Dictation goes into the draft
for review unless **Send what you say automatically** is enabled. The pencil moves
focus to the message field. **Read new replies aloud** uses the same preference as
Settings → Voice; opening history stays silent. Sending a new message, choosing
another conversation or starting a new one stops the previous audio.

Settings includes the complete 44-design AbstractAvatar catalog: 34 Watch picker
designs, three additional Watch shape variants, the iPhone woven orb and six shaded
avatars. Watch Hover is the default for a new browser; existing selections are preserved.
The shared generator and AbstractUIC presenter provide previews of Ready,
Listening, Thinking, Working, Speaking, Waiting and Error, and an animation switch.
Reduced motion and hidden-page animation are handled by the shared renderer.
The phone layout keeps the orb above the conversation; wider screens give voice
and the readable conversation their own space. Conversations are searchable and
grouped by recency, with requests that need you first.

**Automations**, beside Conversations in the sidebar, does what the Apple Watch assistant does:
the active automations first and the most recently active at the top, then **Paused · N** and
**Archived · N** folded until opened (framework ADR 0048; the gateway serves the order and the
counts, and an older gateway gets every automation in one list), an automation's latest runs as a
conversation (opening it marks its new results seen), Run and Stop, Edit (title, task, active, how
often, memory; sent with the revision it was read at), archive and restore, talking about its
latest run (a new conversation, the automation unchanged), a run's tool request answered on its
page with **Approve all** filling **Allowed for its runs** (kept in this browser, per account;
this browser then approves those tools for the automation's runs when it reads the list), and New
automation with its **Tools** (Off, Ask or Auto per tool; the split rides the definition's
`policy.tool_policy`). The cards are AbstractUIC's Watch-style `AutomationCard`; the gateway
calls, the flow picker, the tool editor and the edit and Approve all rules are the kit's
(`createAutomationsClient`, `AutomationWorkflowPicker`, `ToolModeEditor`, `reviseChanges`,
`trustAfterApproveAll`). Run-finished notifications stay on the native apps.

**Mention an entity.** Type `@` in the message box and pick one of your entities (the ones the
gateway lists for your account); it becomes a chip. When you send, the Assistant gets your message
as usual, then each entity you mentioned is asked in turn, in the order you picked them, each once
the previous one answered, and its answer appears in the conversation under its name and look.
Every reply says who wrote it: the agent's name or the entity's, with an "agent" or "entity" tag,
from the gateway, so a reload or another device shows the same. An entity in another conversation
is skipped with one sentence ("Castor is in another conversation.") and the next one is asked. An
entity that cannot answer says why: the words go back into the box with only the entities that
did not answer, and sending the same words again asks only those (the Assistant is not asked
again, and an entity is never asked twice for one message). The Assistant leaves what you ask an
entity to that entity: it answers only the part meant for it, or says nothing, and then the
conversation shows your words and the entities' answers. When an entity keeps something from the
exchange (a diary entry, a question, a lesson, an interest or a realization), its reply shows one
badge for each under its words; click one to read it. Mentions, reply authors and the badges need
AbstractGateway 0.21.0 or later (the Assistant staying out of what you ask an entity also needs
AbstractAgent 0.6.1); a gateway without mentions says "This gateway does not offer mentions yet."
instead of listing names. See the
[browser guide](docs/assistant-guide.md#mention-an-entity).

The Docs drawer keeps its question field at the bottom and scrolls the conversation
above it. Its questions use Assistant documentation and stay separate from your
main conversation. The [browser guide](docs/assistant-guide.md) is bundled as
`llms.txt` for Gateway to supply to that drawer.

Technical streaming notices belong in **Details**, together with optional usage
and timing, rather than in the conversation. A structured-output model call may
deliver its answer all at once; this does not indicate a failed reply. Warnings,
errors and unanswered approval requests remain visible.

It is composed from the AbstractFramework UI kit (AbstractUIC `ui-kit` + `panel-chat`, ADR 0001
there): the app shell and its top-right cluster (docs assistant, appearance, about, who is signed
in, the connection pill), the chat (`WorkflowChat` + `useWorkflowSession`: thread, live replies,
Stop, attachment chips, `@` mentions, who answered on each reply, the badges for what an entity's
reply kept, copy/export), the one approval
panel (`presentInteraction`: Deny / Allow / Allow All / Decide later; the chat's tool policy is
stored on the gateway when it offers `session_tool_policy`), the run's tool plan, and voice (Settings → Voice, read aloud,
Tap/Hold to talk). What stays here: the gateway calls (`src/gateway/`), the conversation list and
its titles, the workflow choice and the run input (desktop parity ports).

Published on npm as [`@abstractframework/assistant`](https://www.npmjs.com/package/@abstractframework/assistant)
(release history: [CHANGELOG.md](CHANGELOG.md); design: [ADR 0007](../docs/adr/0007_web_assistant.md)).
What's new in 0.2.0: `@` mentions of your entities, who wrote each reply, and badges for what an
entity's reply kept, on ui-kit 0.9.27 and panel-chat 0.9.11 ([changelog](CHANGELOG.md#020---2026-11-10)).
Gateway's catalog and tray list it as **Assistant (web)**, next to the desktop Assistant.

## Install

Through AbstractGateway (recommended): open **Apps → Assistant (web) → Install** in the gateway
console or tray, or run

```bash
abstractgateway apps install assistant-web --launch
```

The gateway downloads the package from npm, checks it against the registry's integrity hash,
installs its one runtime dependency and starts it. Open it from **Apps → Assistant (web)**: the
one-time handover signs you in at `<gateway>/apps/assistant-web/`.

On its own, with Node.js 18 or newer:

```bash
npx @abstractframework/assistant --gateway-url http://127.0.0.1:8080
# or: npm install -g @abstractframework/assistant && abstractassistant-web
```

It serves on `http://127.0.0.1:3008/`; sign in with a gateway user id and token in the dialog.
Without `--gateway-url` it follows the local gateway pointer (`~/.abstractframework/gateway.json`),
then `http://127.0.0.1:8080`.

## Run it against a gateway (development)

Needs Node.js 18 or newer (developed on 24, CI on 22) and a running gateway.

```bash
cd web
npm install
ABSTRACTASSISTANT_GATEWAY_URL=http://127.0.0.1:8080 npm run dev     # http://127.0.0.1:3008/
```

Sign in with a gateway user id and token in the dialog. The token goes to this app's own server
(`bin/server.js`), which trades it for a gateway browser session and keeps that in an HttpOnly
cookie; the page itself never sees a token. Without the variable the server follows the local
gateway pointer (`~/.abstractframework/gateway.json`), then `http://127.0.0.1:8080`.

## Run the built app

```bash
npm run build                                   # tsc + vite build + the relative-URL check
node bin/cli.js --gateway-url http://127.0.0.1:8080 --port 3008
```

`bin/cli.js` takes the framework's shared app flags (`--gateway-url`, `--port`, `--host`,
`--help`; abstractuic `app-server`). It listens on 127.0.0.1 only. Gateway detects the
running app and serves it at `<gateway>/apps/assistant-web/`; open it through Gateway
Apps to use the signed-in handover.

Dictation needs a secure page: `http://127.0.0.1`/`localhost`, or `https://`. From another
computer over plain `http://` the microphone button says why it is off.

## Tests

```bash
npm test                     # vitest: fold, titles, run input and tool-plan parity, workflow choice, the kit transport, hosts, automations
npm run check:urls           # no root-absolute same-origin URL in the browser code
npm run build && npm run test:layout   # headless Chromium at 420/760/1024/1280 px, fake gateway
npm run test:experience      # real UI: virtual mic, draft review, speech ownership, avatar preview, keyboard, reduced motion
```

`test:layout` needs Playwright's Chromium (`npx playwright install chromium`); add
`-- --shots <dir>` to `node scripts/check_layout.mjs` to save the screenshots. Below 1024 px it
emulates a touch device and every target must reach 44 px; from 1024 px (a mouse) the rule covers
the app's own controls and the kit sizes its own for a fine pointer. It also opens a reply's
notice badge (its panel must fit), then Settings → Voice and checks that it names the gateway
default and fits, then the automations at
400/760/1024/1440 px: the list with Paused and Archived opened, an automation's page, Edit and New.

`test:experience` uses a virtual Chromium microphone, silent generated WAV data
and a fake Gateway. It performs no inference and never opens a physical microphone.
Both browser checks accept `--shots <dir>` for screenshots.

The session fold runs on the Python tests' own fixture (`tests/basic/fixtures/gateway_runs/`); the
run-input and tool-list tests run on cases generated BY the desktop's code (CI regenerates both and
fails on a difference):

```bash
PYTHONPATH=. python -P web/scripts/gen_run_input_parity.py     # from the repository root
PYTHONPATH=. python -P web/scripts/gen_tool_policy_parity.py   # needs the package's dependencies
```

## Layout

| Path | What it is |
|---|---|
| `bin/server.js`, `bin/cli.js` | The app server: built files, mount under `/apps/assistant-web/`, gateway session proxy |
| `src/host/` | What the page needs from its host (gateway URLs, authentication, native capabilities); the browser host |
| `src/gateway/` | Gateway calls (SSE over fetch, framed by the kit's `sseFrames`) and the kit's `WorkflowTransport` over them, with `replayView` (panel-chat 0.6.2: the conversation, every turn of it, is rendered from the gateway's replay view on AbstractGateway >= 0.17.0, the ledger fold otherwise) |
| `src/lib/` | Pure logic with tests: session fold, titles, workflow choice, run input, theme group, automations (the list's sections, a new automation's body, runs as messages, its tools and "Allowed for its runs") |
| `src/ui/` | The Assistant space on the kit: the conversation (`WorkflowChat`), the conversation and automation lists (the shell's navigation), an automation's page, Edit and New, Settings → Voice |
| `src/vendor/` | Generated, hash-checked AbstractUIC snapshots (`abstractchat` conversation, `abstractdocs` Docs, `abstractsessions` cards, `abstractvoice`, `abstractavatar` rendering); standalone builds use these pinned snapshots |
| `src/styles/index.css` | App styles on the design tokens of `web/design/tokens.css` |
| `design/` | Design tokens and mockups (owned separately) |

The npm package (`@abstractframework/assistant`) ships `dist/`, `bin/`, this README, the
CHANGELOG and the LICENSE; `npm run check:package` lists what a publish would ship and fails on
anything else. The Python wheel and sdist do not include `web/`.

To adopt a built shared-library update from a workspace checkout, run `npm run sync:avatars`
and `npm run sync:docs`. Both snapshots come from canonical AbstractUIC implementations. The
Docs artifact keeps React and the UI kit external so speech and application state retain one
owner. `npm run build` verifies the committed artifact hashes without needing sibling sources.

### Compact conversation cards

Conversation rows use AbstractUIC's shared Watch-style `SessionCard`: cyan marks unread
content, orange marks a pending human question or approval, and a small ring marks work.
Reading clears unread only when loaded content is visible in the focused page. It never
answers or dismisses a pending approval. Read receipts are local to this browser and account;
Code and Assistant share them when served on the same origin. Existing history is baselined
on first use. Regenerate the canonical compatibility snapshot with `npm run sync:sessions`;
the normal build verifies its provenance. Other devices keep independent read state.

### Message files and tool results

The canonical AbstractUIC conversation snapshot (`npm run sync:conversation`) supplies the
same message attachments, safe clickable links and structured tool-result viewer in both web
clients. Files accompany the original user or assistant message, including restored history
and file-only replies. File bytes load when opened through authenticated reads. The build
verifies snapshot hashes; no sibling checkout is required to build the committed web app.

Conversation unread marks use the Gateway's account-wide read ledger. Confirmed consumption
is shared with Code and native clients; failed writes retain the mark. Native clients need
a build that supports `/api/gateway/me/session-reads`. Attachment previews fit the media
with one filename, Download, and Close in the shared AbstractUIC dialog.


## Avatar conversation view

Choose **Avatar** in the conversation header for a second view over the same work.
The avatar shows activity and, under it, one live line: the latest thing the assistant
reports while it works, replaced as soon as something new arrives (nothing cycles). Click
it to read it in full, then **Reply to this** to answer it or **Latest** to follow again.
The findings it reports (facts or evidence it established) accumulate in a
**Findings** panel beside the avatar, or a sheet you open with **Findings** on a phone; open
one to see the results it came from. The answer appears once, as a message, with Markdown,
links and files like the conversation.
**Conversation** restores the ordinary chat and technical details. Switching views
preserves the current draft and attachments.

Avatar permission requests use ordinary actions, destinations and labeled decision
icons. “Why I’m asking” shows the assistant’s public explanation when it belongs to
that exact request. “Review details” opens Conversation mode for technical arguments
and standing permissions. A missing explanation is stated explicitly.

While work continues, type or speak naturally to guide it. **Reply to this** on the live line pins a
specific public update as context. Sending a correction makes it available to the
assistant; the assistant's later response shows whether it adopted the correction.
Questions use their displayed answer controls. Permission requests require an explicit
choice; an ordinary message or silence grants no permission.

Essential questions keep waiting. A clarification may state a two-to-five minute
answer deadline and what will happen without an answer. **Conversation cues** controls
visual and audio alerts independently for questions, permission requests and completion.
Audio alerts default off. Voice narration uses the existing voice preference;
holding the live line, reading the findings sheet or editing a reply silences automatic narration. Playback can be paused
or silenced without stopping the task.

Public updates require a run started in Avatar mode and a backend supporting the public
conversation protocol. Switching an already active legacy run changes its presentation;
it does not manufacture missing updates. Tool details remain available in the ordinary
view. Public updates describe the assistant's communicated conclusions, not private
reasoning, and source references establish provenance rather than proof of correctness.

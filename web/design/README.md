# AbstractAssistant for the web — design

The web Assistant is the same product as the iPhone and Watch apps, in a browser: a calm place to
ask, listen and decide, with the conversation at the centre and the orb as its one living object.
This folder is the design contract for the web client.

| File | What it is | Who uses it |
|---|---|---|
| `tokens.css` | Design tokens as CSS custom properties (`--aa-*`), light and dark | `web/src` imports it; nothing else in it |
| `mockup.html` | Static, dependency-free mockup: Assistant, Inbox, Automations and an orb/composer specimen, both themes | Open it in a browser; `?theme=light|dark`; `#inbox`, `#automations`, `#states` |
| `README.md` | Principles, information architecture, behaviour, copy | Anyone building or reviewing the web client |

`mockup.html` also carries a reference port of the orb (Canvas 2D) taken line for line from the
phone's Swift: see [The orb](#the-orb).

## Principles

1. **One conversation, one living object.** The page is the conversation; the orb is the only
   thing that moves on its own. Everything else is still until you touch it.
2. **Plain words for what happens.** "Add a calendar event", "Send an email", "When mail arrives
   in you@example.org", "By hand". Never a tool id, a workflow id, a run id, a provider or a model
   name on the first layer.
3. **Nothing acts behind your back.** Tool approvals say what will happen in full sentences and
   values; tapping the raised hand opens the decision, it never decides. A transcription is
   reviewed before it is sent unless you switched on automatic sending.
4. **The thing that needs you is the loudest thing on screen** — amber, a raised hand, a badge —
   and nothing else uses amber.
5. **Calm by default, detail on request.** Counts (2 cycles, 3 tools) sit quietly under an
   answer; the detail opens only when asked. Zero counts are not shown.
6. **The same words on every device.** The copy below is the phone's, so a person who uses the
   iPhone, the Watch and the browser never meets two names for one thing.
7. **Readable first.** 17 px answers at 1.6 line height in a 46 rem column, text at ≥ 4.5:1 in
   both themes, 44 px targets everywhere.

### What the Assistant does differently from AbstractCode web

AbstractCode's web client (`../abstractcode/web`) is a good tool for people who run agents on
code. What makes it feel technical, concretely (`e2e/artifacts/desktop.png`,
`tool-approval.png`, `src/workspace/app.tsx`):

| AbstractCode web | Assistant web |
|---|---|
| First screen: "What are we building?", "Explore this project", "Track down a bug" | "What's on your mind?", "Find a little focus", "Untangle an idea" (the phone's empty state) |
| Composer exposes the workspace (`Gateway workspace`, `session-c814b9e4-07…`), "Guide this run", "Queue next turn", "Enter to send · Shift + Enter" hints | `+`, a message box, the orb. Workspace and queueing are not concepts here |
| Approval: `write_file FILE PATH fixture-tool-approval.txt · /private/var/…`, "Allow once", "Allow all enabled tools", a paragraph about Gateway accounts | "Add a calendar event — Title: Buy herb plants — When: Saturday 1 November, 9:00 – 10:00", Approve / Approve all / Deny |
| Status bar: `Connected`, `Native tool approval`, `Run 7fb29b10`, theme name | No status bar. Connection problems appear as one sentence when they matter |
| Sidebar automations: `E2E email notify 179100716…`, `next: 2026-10-04 05:59:26`, `every 24 ho…` | "Morning digest — Every day at 07:30 — Next in 23 hours", results in a sentence |
| Pause / Conclude / View activity always in a header | One control: the orb becomes Stop while it works |
| Voice: "Hold to talk", a mic button among others | The orb: tap to speak, ribbons that answer your voice |

## Information architecture

Three small spaces, as on the iPhone (`phone/iphone/README.md`, "Three small spaces"):

- **Assistant** (first screen, icon: sparkle). The current conversation and the composer. With
  no conversation yet: "What's on your mind?" and two suggestion cards.
- **Inbox** (icon: tray; badge = what waits for you). **Needs you · N** — questions and tool
  approvals from every conversation and automation, each answerable in place — then **Recent
  activity**.
- **Automations** (icon: clock with arrow; badge = results you have not seen). Your routines in
  words, their latest result, Run now / Pause / Resume, **New automation**.

Around them, never competing with them:

- **Conversations**: on wide screens the sidebar under the spaces (Today, Yesterday, Earlier,
  two-line titles, "Needs you" / "Working" / "Failed" marks, **New conversation** in mint); on
  compact screens the stack button at the top left opens the same list as a sheet.
- **Who answers**: the name at the top of the conversation with a chevron ("Assistant ▾",
  conversation title underneath) opens the choice of Assistant or an entity.
- **Share / Files / Tools**: one small island at the top right of a conversation (wide), inside
  "More" (compact). Tools is lavender, as everywhere.
- **Settings**: the gear at the bottom of the sidebar (wide) or in "More" (compact).

## Responsive behaviour

| Width | Layout |
|---|---|
| < 600 px (phone browser) | Phone layout. Top bar: Conversations · Who answers · More. Bottom: a floating pill tab bar (Assistant, Inbox, Automations) with badges. Composer: `+`, keyboard button, space, orb — the keyboard button expands the message box across the row and hides the orb (as on the iPhone) |
| 600 – 1023 px (large phone landscape, tablet, narrow window) | Same shell; the message box is always open between `+` and the orb, so there is no keyboard button |
| ≥ 1024 px | Sidebar (17 rem): wordmark, the three spaces with badges, New conversation, conversations, Settings and Appearance (System / Light / Dark). Content column centred at 46 rem. Composer docked under the conversation, same width |
| ≥ 1440 px | Unchanged column (reading width does not grow). Proposal, not in the mockup: a right rail listing **Needs you** while a conversation is open (see open questions) |

Inbox and Automations replace the conversation in the content column; their own title replaces
the conversation bar. On compact screens the tab bar stays; it hides while the on-screen
keyboard is up.

## The orb

### Geometry (one contour, three shapes)

The phone draws one contour and morphs it (`phone/iphone/Sources/App/Design.swift:30-53`,
`OrbWeave.swift`). The web keeps the same maths:

- **Shell**: a superellipse `x = sgn(cos a)·|cos a|^e`, `y = sgn(sin a)·|sin a|^e` with
  `e = 2 / (2 + 5·squareness)`. Squareness 0 = sphere, 1 = the lit rounded square (Stop).
- **Five ribbons**: the same contour in frames of `0.53 + i·0.055 + 0.16·level` by
  `0.39 + 0.33·level + 0.16·squareness` of the orb size, rotated `i·34° + 9°/s·t`, stroked with an
  angular gradient transparent → mint → lavender → mint → transparent. With level > 0 they ripple:
  `r = 0.5·(1 + level·(0.19·sin(3a + φ) + 0.075·sin(7a − φ)))`.
- **Glass**: the shell filled dark (`--aa-orb-ground`) and lit by a radial gradient from the top
  left (mint, lavender, ground); a soft mint glow outside; a lavender outline.
- **Stop**: while working, a dark rounded inset (46 % of the orb, radius 12 %) holding a
  mint→lavender rounded square (25 %, radius 4.5 %), and a rim whose angular gradient turns
  28°/s.
- **Raised hand**: the five cords leave their orbits for a hand outline (34 control points,
  two Chaikin passes, resampled to 240 points) and blend from mint/lavender to orange `#FF9C33`,
  shimmering along their length; an orange glow.
- **Geodesic** (Transcribing, Preparing speech): the cords become a rotating subdivided
  icosahedron (`OrbWeave.swift:106-129`). Described here; not drawn in the mockup.

**The orb is dark glass in both themes.** On the light page it reads as an object, not a hole;
the only themed orb value is how much glass stays behind the hand (`--aa-orb-hand-glass`: the
phone dissolves it, 0.06, because its page is dark; the light theme keeps 0.9 so the orange hand
stays legible against white).

### States and what wins

| State | Shape | Label above the orb | Accessible name (exact phone string) | A tap… |
|---|---|---|---|---|
| Idle | sphere, breathing ±1.8 % over 7.4 s, ribbons turning | — | "Tap to speak" | starts listening |
| Reading aloud | sphere; ribbons follow playback level | — | "Reading aloud. Tap to speak" | starts listening (stops the reading) |
| Starting microphone | sphere | — | "Starting microphone" | — |
| Listening | sphere; ribbons swell and twist with your voice | Listening | "Listening. Tap to cancel" | cancels; nothing is uploaded |
| Countdown (3 s of silence) | sphere | Listening | "Preparing text in 3 seconds. Tap to cancel" (or "Sending in 3 seconds…" with automatic sending) | cancels |
| Transcribing / Preparing speech | geodesic sphere, rotating | Transcribing / Preparing speech | "Transcribing. Tap to cancel" / "Preparing speech. Tap to cancel" | cancels |
| Working | lit rounded square, Stop symbol, pulsing light (3.5 s) | — | "Stop assistant" | stops the response; afterwards **Edit and resend** appears under the stopped request |
| Stopping | square, disabled | — | "Stopping assistant" | — |
| Needs you (tool approval) | orange raised hand | **Needs you** (amber) | "Review tool approval" | opens Approve / Deny / Approve all — never approves |

Priority, from `VoicePresence` (`Design.swift:243-258`): Stopping > Needs you > Transcribing /
Preparing speech > Working > the voice phases. Every change between shapes is the same morph:
**650 ms, `cubic-bezier(0.4, 0, 0.2, 1)`** (`--aa-dur-morph`, `--aa-ease-morph`), driven from
the current interpolated value so an interrupted morph never jumps.

### In a browser

- **Render** with Canvas 2D (`createConicGradient`, `roundRect`, `filter: blur()` with a
  `shadowBlur` fallback where `ctx.filter` is missing). The canvas is 1.7× the orb so the glow is
  not clipped, scaled by `devicePixelRatio`. A CSS radial gradient on the button is the
  no-script fallback. SVG would need ~25 paths re-written per frame; WebGL is unneeded.
- **Clock**: one `requestAnimationFrame` loop for every orb; 30 fps while active (listening,
  reading, working, needs you, morphing), 12 fps at rest (`--aa-orb-fps-*`); paused when the tab
  is hidden or the orb is off screen.
- **Microphone level**: `getUserMedia({audio: {echoCancellation: true, noiseSuppression: true}})`
  → `AudioContext` → `AnalyserNode` (`fftSize` 1024) → RMS of `getFloatTimeDomainData` per frame →
  normalised to the recent range (the phone adapts to your microphone's recent volume range) with
  a soft compression knee so loud syllables stay distinct → `level` 0…1. Silence detection uses
  the raw RMS against a threshold, independently of the display level, as on the phone.
- **Playback level**: the read-aloud `<audio>` element through `createMediaElementSource` → its
  own `AnalyserNode` (its own scale). The orb shows `max(mic, playback)`.
- **Reduced motion** (`prefers-reduced-motion: reduce`, `--aa-motion-scale: 0`): geometry and
  rotation freeze (time = 0); shapes change without the morph; level still brightens the light
  and glow, as on the phone ("Reduce Motion retains signal-driven light while freezing geometry
  and rotation").
- **Input**: the orb is a `<button>` (84 × 80 px target around a 68 px orb on phones, 64 px on
  desktop). Enter/Space act like a tap. The visible label above it is `aria-hidden`; the state
  is in the button's accessible name, and the hint ("Speak, then pause to review and edit the
  transcription before sending.") in `aria-describedby`. A cancel happens on pointer-down while
  listening, like the phone's touch-down cancel.
- **Limits carried over**: eight seconds without speech times out; one-minute recording limit;
  a denied microphone permission is said in one sentence under the orb with how to allow it.

## The conversation

- **Your message**: right-aligned bubble, lavender wash (`--aa-user-bubble`), radius 22.
  Attachments above it as **small thumbnails**: 56 px tall, aspect kept, at most 132 px wide,
  rounded 12 px; a click opens the full image with **Open** and **Close**. Files with no picture
  are a chip (icon + name).
- **The answer**: no box. A mint sparkle and the quiet uppercase name of who answers
  (**ASSISTANT** or the entity), then the text (17 px / 1.6, lavender list markers, links in mint).
- **Answer actions** (one row, 44 px targets, muted; only positive counts):
  Copy · **Read aloud** (a speaker — never a play triangle; while reading it becomes Pause, with
  Stop beside it and "Reading aloud" in mint) · **Cycles N** · **Tools N** (lavender) · read and
  sent emails · files read / changed · web searches / pages fetched. Cycles and Tools open a
  sheet (compact) or a side panel (wide): the connected progression per agent, and each call
  with its input, output and timing, plus search.
- **While it works**: one quiet line, "Your assistant is working…", expandable into the activity
  (model cycles, tool calls, public results, failures). When the answer arrives the line folds
  into the counts under it.
- **Approval needed**: an inline card with an amber hairline and wash, the raised hand, "Approval
  needed", one sentence ("The assistant wants to do 2 things for you. Nothing happens until you
  decide."), then each action as **Action 1**, a plain title and labelled values; **Technical
  details** (closed) holds the raw call; **Approve** (mint primary), **Approve all**, **Deny**
  (red text); the phone's sentence under them. Compact screens may show the collapsed form
  ("Approval needed · Review tools ↗") and open the same content as a sheet.
- **A question for you** (ask_user): an inline card: the question in large type, each offered
  choice as a full-width button (with a second line when the choice has one), then "Or type an
  answer" and **Send answer**. Once answered it collapses to one line: "A question for you:
  *question* — You answered *choice*."
- **Stopped request**: **Edit and resend** (mint) under your message opens it with its text and
  attachments.
- **Latest messages**: when you scroll up while a reply arrives, a floating pill "↓ Latest
  messages" appears above the composer; it returns to the reply and resumes following. New
  submissions always reveal the latest message. A conversation opens on its latest message.

## The composer

- **`+`** (lavender, round): Choose a file · Photo or video library · Take a photo (devices with
  a camera, via `capture`). Wide screens also accept drag and drop and paste. Each file becomes a
  chip above the composer (thumbnail or icon, name, ✕) until sent or removed. 25 MB per file.
- **Message box**: placeholder "Message the Assistant"; grows to about six lines; the mint round
  Send arrow is disabled (35 % opacity) until there is text or a file. With a physical keyboard
  Enter sends and Shift+Enter is a new line; on touch, Return is a new line and Send sends.
- **Keyboard button** (< 600 px only): expands the message box across the row and hides the orb;
  tapping outside restores the controls and keeps the draft.
- **Voice**: tap the orb, speak, three seconds of silence → the transcription is added to the
  message box below any draft, for review; **Send** sends it. **Send voice messages
  automatically** (Settings → Voice & reading) sends it directly and keeps your typed draft
  separate.

## Inbox and Automations

**Inbox.** "NEEDS YOU · 2" (amber quiet label), then cards:
- "A question for you" — the source in words ("Morning digest · 07:31"), the question, choices,
  "Or type an answer", **Send answer**. Answerable right there.
- "Permission to proceed" — what it will do in words ("Add a calendar event, send an email"),
  where it comes from ("Herbs for the balcony · 2 actions"), ↗ to open it in its conversation.
  Answerable there or in place with the same card as in the conversation.
- Nothing waiting: "You're all caught up." / "Questions and approvals will find a home here."

Then "RECENT ACTIVITY": one row per conversation or automation run, a status mark (mint check,
amber hand, red cross), the title in words (never a workflow id like `deep-research`), and a
status sentence ("Done · 07:31", "Waiting for you", "Failed · The mailbox could not be reached.
It will try again at 10:00.").

**Automations.** Title and **New automation** (mint). One card per routine: an icon for its
trigger (clock, mail tray, hand), **ACTIVE** (mint) / **PAUSED** (muted), its name, its trigger
in words — "Every day at 07:30 (Europe/Paris)", "When mail arrives in you@example.org", "When
Python news has a new item", "By hand" — its latest result as a sentence, "New result" in amber
when unseen, and "Next in 23 hours" or "Last run 08:12" with **Run now** and **Pause** /
**Resume**. A card opens the routine's runs (latest 20, newest first).

## Accessibility

- **Contrast**: every text pair ≥ 4.5:1 and every control outline, focus ring and the orb's
  marks ≥ 3:1, in both themes — checked from `tokens.css` itself by
  `untracked/apple-web-wave/contrast.py` (table in that folder's report).
- **Keyboard**: a "Skip to the message box" link first; then the spaces, conversations, the
  conversation bar, the conversation (each answer's actions in order), the composer (`+`,
  message box, Send, orb). In an approval card: the actions, Technical details, Approve,
  Approve all, Deny — Approve is not focused automatically. Escape closes sheets and the image
  viewer and returns focus to what opened them. Focus is always visible (2 px
  `--aa-focus-ring`, 2 px offset).
- **Live regions**: the conversation is `role="log"` with `aria-live="polite"`. A streaming answer
  is announced when it settles (sentence or paragraph boundaries, not every token), and the
  approval card and question card are announced once when they appear ("Approval needed").
  The orb's state changes update its accessible name; "Needs you" is also announced politely.
- **Targets**: 44 × 44 px minimum for every control, including answer actions and badges' parents.
- **Reduced motion**: as above; the composer and sheet transitions drop to 0 ms
  (`--aa-dur-*`).
- **Text size**: rem-based; the layout holds at 200 % zoom (the column is 46 rem, the sidebar
  collapses below 1024 px CSS width).
- **Colour is never alone**: Needs you has the hand and words, failures have a cross and words,
  Active/Paused are words.

## Hidden on the first layer, and where an expert finds it

| Hidden | Where it is |
|---|---|
| Raw tool names and JSON arguments | **Technical details** in each approval action; Tools sheet (inputs/outputs with credentials redacted) |
| Run ids, step ids, timings | Cycles sheet → expand a step (model, tokens, finish reason, run/step identity) |
| Provider and model names | Cycles sheet step detail; **Show answer statistics** (Settings, off by default) adds wall time, tokens and tool calls under answers |
| Workflow ids (`abstractassistant.agent.v1`, `deep-research`) | Settings → Workflow; never in Inbox or activity rows |
| Gateway URL, account, connection state | Settings → Connection; a connection problem appears as one sentence when it blocks you |
| Tool policies (Off / Auto / Approve per tool) | **Tools** (lavender, conversation bar) and Settings → Default tools |

## Glossary of UI copy

Reuse these exactly (phone strings, `phone/iphone/Sources/App/*.swift` and the README):

| Where | Copy |
|---|---|
| Spaces | Assistant · Inbox · Automations |
| Empty conversation | What's on your mind? · Find a little focus — Make room for what matters · Untangle an idea — A fresh pair of eyes |
| Conversations | Conversations · New conversation · Today · Yesterday · Earlier · Working · Needs you · Failed · Archived · Restore |
| Who answers | Choose who answers · Assistant · New entity |
| Conversation bar | Share conversation · Conversation files · Tools |
| Composer | Add attachment · Choose a file · Photo or video library · Take a photo · Type a message · Message the Assistant · Send message |
| Orb | Tap to speak · Listening · Listening. Tap to cancel · Transcribing · Preparing speech · Stop assistant · Stopping assistant · Needs you · Review tool approval · Reading aloud. Tap to speak |
| Voice settings | Voice & reading · Send voice messages automatically · Gateway default |
| Answer | Copy answer · Read answer aloud · Pause or resume reading · Stop reading · N cycles. View cycles · N tool calls. View tools · Edit and resend |
| Working | Your assistant is working… · Approval needed · Review tools · Waiting for your reply · Reply |
| Approval | Approve these tools? · Action N · Approve · Approve all · Deny · Approve allows this request. Approve all also allows enabled tools in this conversation without asking again. You can change this in Tools. · Already handled or no longer waiting. |
| Question | A question for you · Send answer |
| Inbox | Needs you · N · Nothing needs you · You're all caught up. · Questions and approvals will find a home here. · Permission to proceed · Recent activity |
| Automations | New automation · Active · Paused · Run now · Pause · Resume · Next … · By hand · When mail arrives in … · When … has a new item · Every … · No runs yet. Run this automation now or wait for its next scheduled time. · Create automation |
| Following | Latest messages |
| Notifications | Approval needed · A question for you · *Name* has a result |

New web-only copy in this design (to be agreed): "Message the Assistant", "Technical details",
"The assistant wants to do N things for you. Nothing happens until you decide.", "Or type an
answer", "You answered …", the plain action titles ("Add a calendar event", "Send an email").

## Tokens in one paragraph

Dark is the phone, exactly (`Design.swift:5-13`): ground `#090B16`, surface `#131726`, ink
`#EDF2FF`, secondary `#A6B2CC`, mint `#6BE3CC` (primary action, success), lavender `#ADA6FF`
(tools, icons), amber `#FFC46E` (approval), hand orange `#FF9C33`. Light is derived: the same
hues darkened until text clears 4.5:1 (mint text `#08705E`, lavender text `#5548D6`, amber text
`#8A4F00`, primary fill `#0B7A67` with white). Decorative colours (`--aa-mint`, `--aa-lavender`,
`--aa-amber`) are for light inside the orb or marks, never text on light surfaces; use the
`*-text` tokens for words and icons. The abstractuic mapping and the desktop-theme mapping are
at the top of `tokens.css`.

## Open questions for the operator

1. **Desktop themes.** The desktop ships 22 named palettes; the web proposal ships the Assistant's
   own light and dark only. Offer "match my desktop theme" (the seed mapping is in `tokens.css`)
   or keep the web Assistant's identity fixed?
2. **Dark orb on the light theme.** The orb stays dark glass in light mode (it is the product's
   object). The alternative is a pale pearl orb with darker ribbons — weaker identity, more
   "native" on white.
3. **Plain action titles** ("Send an email" instead of "Send Email") need a per-tool phrase,
   ideally from the gateway's tool metadata. Who owns those phrases?
4. **Approval inline vs sheet.** Wide screens show the full approval card inline; the phone
   uses a collapsed row and a sheet. Keep both, or the sheet everywhere for consistency?
5. **A "Needs you" rail at ≥ 1440 px** while a conversation is open, or keep the Inbox a space
   only?
6. **A keyboard shortcut for the orb** (e.g. Alt+Space to speak). Browsers and OSes claim most
   combinations; is one wanted at all?
7. **Wordmark**: "AbstractAssistant" in the sidebar or just "Assistant" (which is also the first
   space's name)?

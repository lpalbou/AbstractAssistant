# Design: AbstractAssistant for Apple Watch

Target devices: Apple Watch Series 11, 46 mm (416 × 496 px) and 42 mm; watchOS 26 or later. Dark
palette from abstractframework.ai (ground `#0a0a12`, cards `#15151f`, hairlines `#2a2a3a`; indigo,
cyan, green, amber and red as light). System font, rounded design, with the system text styles so
the watch's text size applies.

Mockups of the first design: `../design/screens/`. Animated prototype: `../design/prototype.html`.
Orb styles: `../design/anim/orb-designs/`.

## Principles

1. **The orb is the assistant.** While it listens, thinks or speaks it fills the screen; text and
   actions are below it.
2. **Nothing consequential without a tap.** Raising the wrist, scrolling or a notification never
   approves anything. Double Tap allows only approvals that neither send nor destroy.
3. **The run waits; the watch does not.** The gateway keeps the state; lowering the wrist never
   loses anything.
4. **Same session everywhere.** A conversation started on the watch continues on the Mac, and the
   other way round.
5. **Plain words.** The screen says what the assistant does ("Searching the web", "Run a
   command"), never an internal identifier, and an error is one short sentence.
6. **Clean layout.** On a screen that fits, its actions are at the bottom. Secondary controls are
   small round icons the size of the Back button.

## Screens

| Screen | Purpose | Actions |
|---|---|---|
| Sign in | First launch, after Sign out, or when the gateway ends the session: the AbstractFramework mark, one field "Sign in with user or email" with the send arrow inside it, the server below (tap to change). A user name then asks for its token; an email gets an 8-digit code. | send · change · resend the code |
| Choose your orb | First launch: the eight orb styles, one per page, each shown speaking, "Use this" at the bottom. | swipe · Use this |
| Home | The orb (one tap to talk), what needs you (only when something does), Sessions and Automations with a count: what is new in a filled badge, else how many, a spinner until they are read; "Connecting…" while the first tries are retried, and the gateway said unreachable only after 3 failed tries over 20 s; the gear opens Settings. | talk · open |
| Ask | The orb fills the screen. At rest: "Assistant ⌄" below the orb (who answers), the keyboard icon top right and the tools icon bottom right (as far from the bottom as the keyboard from the top); while it listens, works or speaks, they hide. While it works: its steps live below the orb, a pulse per tool call, a satellite per tool running, and the amber shield (bottom right) after an Accept all. Beside Back: share the conversation, and the voice button (play, pause, hold to rewind). The answer appears below with its images and recordings, spoken by the orb; "N steps · time" opens how it worked. | tap · hold · keyboard · tools · shield · share · voice button · choose who answers |
| Tools | A conversation's tools (or the defaults, from Settings): its Workflow row, then the groups (Files, Web, System, Email, …) with their counts; after an Accept all, "Allowed for now" with Ask again. A group lists each tool with its risk, what it can do and Off · Auto · Ask, and All for the group. | choose · Use my defaults · Ask again |
| Workflow | The gateway's default agent first, then the Assistant's workflows ("Also makes images and other media"), then the other agents. | choose |
| Image | An answer's image full screen: the Digital Crown zooms, a drag looks around, a double tap fits it; share beside Back. | zoom · share |
| Work | A finished answer's steps in order (thinking, tools, media), with their durations. | read |
| Who answers | The Assistant (one-shot agent), then your entities (long-term discussions), each with its orb. | choose |
| Approval | What the assistant wants to do in plain words, then exactly what: the command and its folder, the page, or the recipient, subject and "Read the email". Three icons at the bottom. | deny · allow once · allow these tools in this conversation (from a conversation, never for sends) |
| Email | The full email the assistant wants to send. | back |
| Question | The question, its choices, or another answer typed or dictated. | choice · answer |
| Needs you | Everything waiting, oldest first; it closes when nothing is left. | open |
| Sessions | New and Search on one line, then your conversations by day with exchanges, tools and how long ago each last changed ("10 h ago"); one with an answer you have not opened is outlined in cyan; the archive button at its right archives one (after a confirmation); Archived at the bottom. | continue · search · archive · details (swipe) |
| Search | The conversations holding the words (questions, answers, artifacts), the words marked, a matching image beside them. | continue |
| Archived | Archived conversations, each with Restore. | restore |
| Session | Its last exchanges (question, then the answer); a finished answer opens in full; a running one can be stopped. Continue floats at the bottom. | open · stop · Continue |
| Read aloud | The orb speaks a text, the text below; the rewind icon beside Back goes back 10 s. | tap: pause/resume · rewind |
| Link | A tapped web link: the page's title and readable text, read aloud. | read aloud |
| Automations | New automation first, then each automation: its name with a spinner while it runs, its count of new results (outlined in amber) and its archive button; its runs and schedule ("⟳ 44 🕐 12h ➜ 6h") with the switch that turns it on or off; Archived at the bottom. | open · on/off · archive |
| Archived automations | Archived automations, each with Restore. | restore |
| Automation | Name and instructions, in full; runs and schedule line with Run now at its right (stop while it runs); Read aloud and Edit; while running, what the agent is doing now; the latest result; earlier runs (five, then more). | run now · stop · read aloud · edit · open a run |
| New automation | The task (the field opens the watch's text input), the workflow (the gateway's default by name, then the gateway's workflows for this account), its tools (the Tools page), when (the shared presets, or daily at a time), Builds on earlier runs, Create at the bottom. | create |
| Edit automation | The title, the task and the instructions, each in its own field opening with the current text (shown at once when its page has read them), how often, Active, Builds on earlier runs, Save at the bottom; Back with changes asks Save or Discard. | edit · Save · discard |
| Settings | Connection (the gateway, the account, its email and tools), Tools (the defaults), Voice (voice, speed, transcription model), Orb style, Read aloud, About, and Sign out at the bottom. | |
| About | The app's version and build; the framework's author, copyright, website, source, documentation, issues, feedback and contact. | open a link |

## Flows

### An approval arrives

1. A run reaches a tool approval on the gateway.
2. The watch learns it on the next poll (15 s on screen; background refresh when closed).
3. Haptic; the Home card "Needs you" appears with what the assistant wants to do.
4. The approval says what and how; deny, allow once, or (from a conversation) allow its tools.
5. The watch answers and goes back where the approval was opened: the orb follows the run again.
   Tools allowed this way are approved by the watch while it follows the run; the amber shield on
   the orb makes them ask again from the next call.

### Ask by voice

1. Tap the orb: the microphone records; the first half second sets the room's noise floor; a
   click marks the moment it first hears you.
2. Send: tap again, or 3 s without speech once you have spoken (5 s with nothing heard: it stops).
3. The gateway transcribes; the run starts in the current conversation (an entity: its chat).
4. Its steps appear below the orb as they happen ("Searching the web…" in the status line, a pulse
   per tool call); a person's decision on the way opens the approval or question, and answering it
   returns to the orb.
5. The answer: a haptic, the orb speaks it (then plays any recording it made), the markdown below
   with its images. If you left the app, the answer
   comes as a notification; tapping it returns to the orb.

### An automation runs

1. Run now (or the schedule) starts an occurrence; its page shows what the agent is doing, with a
   running time, and the list shows a spinner on it.
2. You can stay, stop it, or leave: the result comes as a notification.
3. When it ends: a haptic, the new result at the top, the run among the earlier ones.

## The orb

One mark stands for the assistant everywhere: the app icon, Home, the Ask screen and each row of
the responder picker. At rest it is a planet of pixel-size points turning slowly like the Earth
seen from space (a tilted axis, about one turn every fifty seconds, a lit side, a night side, a
rim). When it hears you or speaks, each point blends from its place in the resting orb toward the
style's voice shape. Its share is

    w = e · smoothstep(θ − 0.2, θ + 0.2, m),   θ = 1 − 1.05 · s

with `m` the point's mobility (its distance from the centre plus a little chance) and `s` the voice
signal (rising in about 120 ms, falling in about 600 ms). A weak voice moves only the outer band; a
stronger one draws in more and more points; one point in six follows at most 15%, so the shape
breathes yet stays. Moving points light up as they travel, and no point leaves the screen.

Eight styles, chosen at first launch and in Settings → Orb style: Halo (a radial voice histogram),
Vortex (spiral arms), Nebula (a breathing cloud), Rings (three pulsing orbits), Liquid (surface
waves), Galaxy (a dense spiral with stars everywhere), and two scenes of their own (`OrbScenes`):

- **Face**: a head-and-shoulders portrait in points (smiling eyes with a catchlight, a soft
  smile, rosy cheeks). It blinks every few seconds, breathes and turns its head a little; its mouth
  opens with its own voice (wider on bright sounds) and its jaw follows; while you speak it tilts
  its head and raises its brows; while it thinks it looks up and aside.
- **Ocean**: a sea at night seen through a round window, the water in rows of equal distance that
  close up toward the horizon, a moon, its glade glittering on the water, a few stars. Three waves
  at rest (a slow swell, a crossing wave, a chop); a voice raises the swell with its low pitches
  and the chop with its high ones. The last 1.2 s of the voice travel across the water: toward you
  while it speaks, away while you do. While it thinks the waves calm and rain falls, each drop
  sending out rings.

An entity's orb takes its colour and shape (planet, kitty, face, wave) from the gateway (with
Face or Ocean chosen, an entity keeps its own shape and answers the voice as Nebula does). The microphone is open only while the orb listens.

While the assistant works, the orb shows the work: each tool call sends a ring of light out from the
centre (parallel calls a few tenths apart), a new thought a softer ring, an image or a recording
being made a slow wide wave, and a failed tool a short shiver; each tool running circles the planet
as a small satellite with a trail, dimmed as it passes behind.

## Interaction rules

- **Haptics.** A new wait, a sent answer, a failed one, an answer arriving, an automation done:
  one haptic per event.
- **Double Tap** allows once an approval that neither sends nor destroys; never anything else.
- **Wrist raise** refreshes the screen; it never acts.
- **Offline.** The last known state stays; a red line says the assistant cannot be reached.
- **Signed out (401).** The app stops polling and shows the sign-in screen with a short sentence.
- **Text.** Commands and email bodies are shown exactly as the assistant wrote them; everything
  around them is plain words.

## Approval states

An answer is *sending* (icons disabled), then the screen closes. A wait answered on another device
closes the screen without sending anything. The watch reads the run again before answering, so a
stale approval never resumes another step.

## Accessibility

VoiceOver labels on every control, the system text styles for all text, high contrast by
construction, haptics mirrored by a visible change, no colour-only state (every state has a word).

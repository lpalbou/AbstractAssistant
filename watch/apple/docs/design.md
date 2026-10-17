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
| Choose your orb | First launch: the six orb styles, one per page, "Use this" at the bottom. | swipe · Use this |
| Home | The orb (one tap to talk), what needs you (only when something does), Sessions and Automations with round count badges; the gear opens Settings. | talk · open |
| Ask | The orb fills the screen. At rest: "Assistant ⌄" below the orb (who answers) and the keyboard icon top right; while it listens, works or speaks, neither shows. Beside Back: share the conversation, and back 10 s while it speaks. Tap to talk; tap or 3 s of silence sends; the answer appears below, spoken by the orb; tap to pause or resume; hold to reply. | tap · hold · keyboard · share · back 10 s · choose who answers |
| Who answers | The Assistant (one-shot agent), then your entities (long-term discussions), each with its orb. | choose |
| Approval | What the assistant wants to do in plain words, then exactly what: the command and its folder, the page, or the recipient, subject and "Read the email". Three icons at the bottom. | deny · allow once · allow all in this session (from a conversation, never for sends) |
| Email | The full email the assistant wants to send. | back |
| Question | The question, its choices, or another answer typed or dictated. | choice · answer |
| Needs you | Everything waiting, oldest first; it closes when nothing is left. | open |
| Sessions | New conversation, then your conversations by day with exchanges, tools and age. | continue · details (swipe) |
| Session | Its last exchanges (question, then the answer); a finished answer opens in full; a running one can be stopped. Continue floats at the bottom. | open · stop · Continue |
| Read aloud | The orb speaks a text, the text below; the rewind icon beside Back goes back 10 s. | tap: pause/resume · rewind |
| Link | A tapped web link: the page's title and readable text, read aloud. | read aloud |
| Automations | New automation first, then each automation: name, "🕐 12h ➜ 6h", a spinner while it runs, a count of new results. | open |
| Automation | Name; schedule line with Run now at its right (stop while it runs); Read aloud and Edit; while running, what the agent is doing now; the latest result; earlier runs (five, then more). | run now · stop · read aloud · edit · open a run |
| New automation | The task (the field opens the watch's text input), the workflow (Gateway default, then the gateway's workflows for this account), when (the shared presets, or daily at a time), Builds on earlier runs, Ask before using tools, Create at the bottom. | create |
| Edit automation | The task (the field opens with the current text), how often, Active, Builds on earlier runs, Save at the bottom. | edit · Save |
| Settings | Orb style, Read aloud (answers are spoken by the orb), About, then who is signed in and where, and Sign out at the bottom. | |
| About | The app's version and build; the framework's author, copyright, website, source, documentation, issues, feedback and contact. | open a link |

## Flows

### An approval arrives

1. A run reaches a tool approval on the gateway.
2. The watch learns it on the next poll (15 s on screen; background refresh when closed).
3. Haptic; the Home card "Needs you" appears with what the assistant wants to do.
4. The approval says what and how; deny, allow once, or (from a conversation) allow all.
5. The watch answers and goes back where the approval was opened: the orb follows the run again.

### Ask by voice

1. Tap the orb: the microphone records; the first half second sets the room's noise floor; a
   click marks the moment it first hears you.
2. Send: tap again, or 3 s without speech once you have spoken (5 s with nothing heard: it stops).
3. The gateway transcribes; the run starts in the current conversation (an entity: its chat).
4. "Thinking…"; a person's decision on the way opens the approval or question, and answering it
   returns to the orb.
5. The answer: a haptic, the orb speaks it, the markdown below. If you left the app, the answer
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

Six styles, chosen at first launch and in Settings → Orb style: Halo (a radial voice histogram),
Vortex (spiral arms), Nebula (a breathing cloud), Rings (three pulsing orbits), Liquid (surface
waves), Galaxy (a dense spiral with stars everywhere). An entity's orb takes its colour and shape
(planet, kitty, face, wave) from the gateway. The microphone is open only while the orb listens.

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

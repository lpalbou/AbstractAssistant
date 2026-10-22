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
7. **Swipes as in a browser.** A swipe to the right (the finger moving right, as with watchOS's
   own Back) goes back one page, down to Home; a swipe to the left goes forward to a page you came
   back from, and does nothing when there is none. On Home at launch, neither goes anywhere.
   Swipes move between the app's own pages; a page opened from content (a message, its steps, a
   picture, a link, a form) opens with a tap only.
8. **One corner button.** The button at the top left is the same on every page and never moves:
   the gear on Home, Back everywhere else, morphing from one to the other; the page's title sits
   beside it, the time at the right. Settings opens from the left, where its gear is, and its
   pages (Connection, Orb style, Voice, Tools, About) follow from the left and leave to the left;
   every other page comes from the right. Nothing is drawn behind that row: every page starts
   below it and is cut there, scrolled or not.

## Screens

| Screen | Purpose | Actions |
|---|---|---|
| Sign in | First launch, after Sign out, or when the gateway ends the session: the AbstractFramework mark, one field "Sign in with user or email" with the send arrow inside it, the server below (tap to change). A user name then asks for its token; an email gets an 8-digit code. | send · change · resend the code |
| Choose your orb | First launch (and Settings → Orb style): the thirty-three styles in six families (Orbs, Forms, Cosmos, Nature, Faces, Machines), each row a small live orb speaking, its name and a few words; a row opens its preview, which goes through listening, thinking, working and speaking (tap a phase to hold it), "Use this" at the bottom. | scroll · open · Use this |
| Home | The orb (one tap starts a new conversation; an earlier one continues from Sessions), what needs you (only when something does), Sessions and Automations with a count: what is new in a filled badge, else how many, a spinner until they are read; "Connecting…" while the first tries are retried, and the gateway said unreachable only after 3 failed tries over 20 s; the gear opens Settings. | talk · open |
| Ask | The orb fills the screen. At rest: "Assistant ⌄" below the orb (who answers), the keyboard icon top right and the tools icon bottom right (as far from the bottom as the keyboard from the top); while it listens, Send takes the tools icon's place (what was said goes now, before a noise keeps the silence that sends from coming); while it works or speaks, they hide. While it works: its steps live below the orb, a pulse per tool call, a satellite per tool running. Beside Back, the row follows what it does: Stop while it is busy (listening, thinking or working, speaking or paused), Share at rest; while it works after an Accept all, the amber shield beside it takes the permission back; the voice button (play, pause, hold to rewind) once there is an answer. A tap on the orb listens, sends, or pauses and resumes its voice; a 1.5 s hold on the orb (a ring closes round it) does what Stop does, and at rest reads the last answer aloud; let go before, nothing happens. The answer appears below with its images and recordings, spoken by the orb; "N steps · time" opens how it worked. | tap · hold to stop · stop · keyboard · tools · shield · share · voice button · choose who answers |
| Conversation | Swiped to the left from the orb page of a conversation with at least one message: its title, its numbers (questions, tool calls, thinking steps, when it started, its last activity, its files, the questions spoken) and its files (what its turns made or were given, and what its assistant wrote into the conversation's folder), newest first, one card each (what it is, made or attached, its size and age) with its share button on the right; a tap opens its preview; Every exchange opens the conversation's exchanges. Swiped to the right, the orb page again. | swipe · open · share |
| File preview | A tap on a file of the conversation's page: one file per page, its name and where it is ("2 of 5"); a swipe up shows the next file, a swipe down the one before (or the crown). A picture shows (a tap opens it to zoom), a drawing (SVG) is drawn on the watch, a text shows its start, a recording or a video opens to play; otherwise what it is and its size. Share beside Back. | swipe · open · share |
| Tools | A conversation's tools (or the defaults, from Settings; a new conversation starts on them, and a default stays as chosen): its Workflow row, then the groups (Files, Web, System, Email, …) with their counts; after an Accept all, "Allowed for now" with Ask again. A group lists each tool with its risk, what it can do and Off · Auto · Ask, and All for the group. | choose · Use my defaults · Ask again |
| Workflow | The gateway's default agent first, then the Assistant's workflows ("Also makes images and other media"), then the other agents. | choose |
| Image | An answer's image full screen: the Digital Crown zooms, a drag looks around, a double tap fits it; share beside Back. | zoom · share |
| Work | A finished answer's steps in order (thinking, tools, media), with their durations. | read |
| Who answers | The Assistant (one-shot agent), then your entities (long-term discussions), each with its orb. | choose |
| Approval | What the assistant wants to do in plain words, then exactly what: the command and its folder, the page, or the recipient, subject and "Read the email". Three icons at the bottom, the same for a conversation's run and an automation's, wherever it was opened (the orb page, Needs you, a notification). | deny · allow once · approve all: these tools for the rest of the run's conversation, or for its automation's runs, each by its own tools (never for sends) |
| Email | The full email the assistant wants to send. | back |
| Question | The question, its choices, or another answer typed or dictated. | choice · answer |
| Needs you | Everything waiting, oldest first; it closes when nothing is left. | open |
| Sessions | New and Search on one line, then your conversations by day with exchanges, tools and how long ago each last changed ("10 h ago"); one with an answer you have not opened is outlined in cyan; the archive button at its right archives one (after a confirmation); Archived at the bottom. | continue · search · archive |
| Search | The conversations holding the words (questions, answers, artifacts), the words marked, a matching image beside them. | continue |
| Archived | Archived conversations, each with Restore. | restore |
| Session | Every exchange (from the conversation's page): its last exchanges (question, then the answer); a finished answer opens in full; a running one can be stopped. Continue floats at the bottom. | open · stop · Continue |
| Read aloud | The orb speaks a text, the text below; the rewind icon beside Back goes back 10 s; holding the voice button rewinds 8 s a second, a bump every half second. | tap: pause/resume · rewind |
| Link | A tapped web link: the page's title and readable text, read aloud. | read aloud |
| Automations | New and Search on one line, as in Sessions; then each automation: its name with a spinner while it runs and its archive button; its runs and schedule ("⟳ 44 🕐 12h ➜ 6h") with, at the right, the runs you have not seen in an orange badge (the row outlined in amber); Archived at the bottom. On or off is in Edit. | new · search · open · archive |
| Search automations | The automations whose name or task holds every word searched, as rows of the list. | open · archive |
| Archived automations | Archived automations, each with Restore. | restore |
| Automation | The same orb page as a conversation: its runs are its messages (the message its trigger sent, when, then the answer; a failed run in red), the latest in full, the earlier ones as cards; its name below the orb where a conversation shows who answers; (i) where a conversation has its tools; a run in progress is followed on the orb (its steps under it, Stop ends the run, the schedule goes on); talking opens a conversation about it, seeded with its runs, and the page goes on as that conversation (the automation's own runs never read it). A swipe forward opens its details. | talk · stop · read aloud · share · (i) · open a run |
| Automation details | Behind (i): its name, when it runs and next, Edit and Run (back to its orb page, which follows the run; Stop while it runs), its task (unless its name says it), whether it builds on its earlier runs. | edit · run · stop |
| New automation | The task (the field opens the watch's text input), the workflow (the gateway's default by name, then the gateway's workflows for this account), its tools (the Tools page), when (the shared presets, or daily at a time), Builds on earlier runs and, when it does, how much of them it reads (the gateway's default, a number only), Create at the bottom. | create |
| Edit automation | The title and the task, each in its own field opening with the current text (shown at once when its page has read them); Runs: Active and how often; Memory: Builds on earlier runs and, when it does, how much of them it reads ("Reads up to 50,000 tokens": the gateway's value, a number only); Save at the bottom; Back with changes asks Save or Discard. | edit · Save · discard |
| Clock | Swiped to from Home (to the left; to the right goes back), or where the app opens with Settings → Start on the clock: the app as a watch face. The orb in the middle (the chosen style, alive; a tap talks, as on Home), the dial round it (the rim's sixty points lit through the hour, the current minute brightest, the twelve hours, the hour as a comet orbiting the orb), the date top left, what waits for you bottom left (amber, its number; a tap opens it), the next automation bottom right (how long until it, its name; a tap opens it). No corner button. Wrist down: the orb still, the dial dimmed, redrawn every minute. | talk · open what waits · open the next automation · swipe back |
| Orb clock | A complication on the watch face, under Assistant in the face's Edit screen. Circular: the time in particles (the rim's minutes lit through the hour, a stream of light to a comet for the hour) round a small orb, cyan, or amber with the number waiting for you. Rectangular (and the Smart Stack): the same dial, then "2 need you" or "All clear", what needs you first or the results not seen, and the next automation ("Morning digest · 2h"). Corner: the dial, with what needs you or the next automation along the edge. Inline: the same line. On a tinted face, the lit points take the face's colour. | tap: opens the app |
| Settings | Connection (the gateway, the account, its email and tools), Tools (the defaults), Voice (voice, speed, transcription model), Orb style, Read aloud, Start on the clock (and how to keep it in front), Notifications (when an automation finishes a run), About, and Sign out at the bottom. | |
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

1. Its schedule (or Run, on its details) starts a run: on its orb page the orb works and its
   steps show under it, as for a question you asked; Sessions and the list show it running.
2. You can stay, stop it, or leave: the result comes as a notification.
3. When it ends: a haptic, the orb speaks the answer, the run among the earlier messages.

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

Every style draws the same five phases from one interface (`OrbPhases`: how much of each phase is
happening, summing to 1, and the voice now): at rest; listening (you speak); thinking; working
(tools running, while it thinks); speaking. Each phase has its own motif in every style, and the
change between two phases is a blend, never a cut. The points glow (a soft bloom under the
brightest), surfaces are sampled evenly (no grain) and lit from the upper left; the voice's shapes
stay inside the orb's circle.

Thirty-four styles, chosen at first launch and in Settings → Orb style, in six families: **Orbs**
(Halo, Vortex, Nebula, Rings, Liquid, Galaxy), **Forms** (Lotus, Crystal, Eclipse, Synapse, Drop,
Wave), **Cosmos** (Well, Black hole, Accretion), **Nature** (Ocean, Aurora, Murmuration), **Faces**
(Face, Imprint, Contour, Membrane, Eye) and **Machines** (Lens, Dome, Valet, Retro, Deco, Rover, Hover, Spark, Cruiser, Android, Sentinel). Five planets whose points answer
the voice: Halo (a radial voice histogram), Vortex (spiral arms), Nebula (a breathing cloud), Liquid
(surface waves), Galaxy (a dense spiral with stars everywhere). Twenty-eight scenes of their own
(`OrbScenes`, `OrbConcepts`, `OrbCosmos`, `OrbNature`, `OrbAvatars`, `OrbLines`, `OrbRobots`, `OrbMachines`). Every scene is a blend of the
five phases' shapes, each motion at a fixed pace (a phase changes how much of a motion shows, never
its speed), so a change of state is always a smooth morph:

- **State shapes**, five orbs with one shape per state, the points morphing from one to the next
  as the state changes (at rest, a calm listening shape; working is shown while tools run):
  - **Lotus**: a bud breathing with your voice over rings of light (listening); its petals open and
    twist (thinking); a branching network, a node at each tip (working); a full bloom, the petals
    opening wider and the stamens reaching up with the voice (speaking). A thread of light falls
    from its base.
  - **Crystal**: a small crystal in a haze of sparkles drawing in with your voice; a larger compound
    of two crystals, sparkles circling; orbits with small crystals travelling on them and a beam
    through it; ribbons of light spreading like wings, carrying the voice outward.
  - **Eclipse** (violet and gold): a dark disc in a corona with a bright point at its heart, the
    corona swelling with your voice; the lit crescent turning inside tilted orbits; a shutter
    opening on one half, rays fanning out; crescents on the sphere and the voice as bars on both
    sides.
  - **Synapse**: a compact network pulsing with your voice; a large tangled network with signals
    running along its links; hubs with nodes travelling on orbits around them; a starburst from a
    central node, the links lighting outward with the voice.
  - **Drop**: a drop of light wobbling over rings that ripple out with your voice; a vortex of three
    arms; fibres fanning out to nodes; a horn of streamlines opening like a bell, wider with the
    voice.
- **Thinking and working on the planets**, each its own: Halo, a crown of rays turning, lit one
  after another / light flowing out along every ray; Vortex, a whirlpool winding inward / four arms
  flinging light outward; Nebula, the cloud condensing, stars igniting / four clumps orbiting with
  tails; Liquid, a slow lava lamp / droplets thrown off and falling back; Galaxy, the disc forming,
  arms tightening / light flowing out along the arms in pulses.
- **Wave**: ribbons of light across the screen, each a band of the voice (its harmonic), coloured
  blue to violet, rose, amber and green, overlapping in light. A gentle swell at rest; the waves
  come in from the edges as you speak and travel out from the centre as it speaks; slow crossing
  undulations while it thinks; the ribbons wind into a turning swirl while it works.
- **Cosmos**, three scenes of the universe:
  - **Well**: the fabric of space as a grid of fine lines in perspective, curving down into a well
    round a glowing mass. At rest the well is shallow and breathes; listening, ripples run in from
    the edges carrying your voice; thinking, the well deepens and a second mass circles inside it;
    working, the two masses orbit close and fast and the fabric carries their gravitational waves
    out in a two-armed spiral, a ring for each step, each tool running a small body circling in the
    well; speaking, waves leave the centre with the voice, its low pitches near the mass.
  - **Black hole**: a soft ring of orange light round a dark shadow, brightest where the gas comes
    toward you, as the Event Horizon Telescope photographed it. Listening, gas spirals in along
    three streams and the ring brightens; thinking, the ring flattens into a thin disk seen almost
    edge on, its far side bent into arcs over and under the shadow; working, twin jets leave the
    poles; speaking, the ring follows the voice round its circumference and a hot spot circles it,
    flaring on loud syllables. Stars behind it are pushed aside by its lensing.
  - **Accretion**: a solar system forming, a young star in a disk of dust with dark lanes between
    its rings (as the disk round HL Tauri was photographed). Listening, streams of dust fall onto
    the disk; thinking, the dust drifts round its rings into seven clumps; working, the clumps merge
    two by two into planets that clear their lanes; speaking, each ring glows with one band of the
    voice, a spiral wave runs through the disk and the star flares.
- **Rings**: a geodesic structure of six rigid rings on the great circles that cross at the corners
  of an icosidodecahedron, each a glowing line running through the hues of light (brighter in front)
  with soft beads on it, turning slowly as one body. Each ring is driven by its own band of the
  voice (low pitches the first, high the last): its size follows that band (a quiet harmonic draws
  its ring in, a loud one pushes it out, so the voice's harmonics show as rings of different sizes),
  it sways about its own diameter and its beads spin faster; silence lets the structure settle back.
  Thinking spins it up like a gyroscope; working runs a wave across the rings, the beads racing.
- **The face's relief**, shared by Face, Imprint and Contour: the cranium round and the
  jaw tapering to the chin, a forehead, temples, a brow ridge, eye sockets deepest at their inner
  corners with the eyeball and its lid crease, a narrow nose bridge widening to a rounded tip with
  its wings and nostrils, the philtrum, lips with a cupid's bow and a fuller lower lip, tucked
  corners, the groove under the lower lip, high cheekbones over full cheeks, the folds from the
  nose to the mouth. Its mouth speaks with the voice: the jaw drops, the lips part (the lower one
  following the jaw), rounder on dark vowels, wider on bright ones.
- **Face**: a sculpted bust in light: the face's relief sampled evenly under a soft frontal light, friendly eyes (a soft white, an iris, a dark pupil, a
  catchlight, gently raised brows), a calm smile, hair flowing from a side part, neck and
  shoulders. It blinks, breathes and moves its head a little. Its lips follow its own
  voice: parting with loudness, wider than tall (the jaw following), rounded when the low bands lead,
  wide when the high ones do, the upper teeth showing on open syllables, closed in the pauses; its
  brows lift on stressed syllables and its head nods with its phrasing. Listening, it turns its head
  and cups a hand behind its ear, nodding along with your voice, its brows raised, your voice
  arriving as arcs in the hand's cone; thinking, it looks up and aside;
  working, it reads (quick glances) while a fine scan line passes down its face.
- **Imprint**: the face zoomed in and pressed against a pane of glass: only what touches the pane
  is drawn, lit by its own surface so its features read, with a bright rim. At rest most of the face
  touches it, its eyes closed and serene and a calm smile on its lips. Its voice
  presses it in and opens its mouth with the words, its head nodding with its phrasing; while you
  speak it turns to lay its cheek on the pane, pressing closer and nodding with your voice;
  thinking, it draws back so less of it touches.
- **Contour** (after Wave): the face raised in lines of light across the screen, as a line
  engraving shows depth, each line lit by the face's slope under it (the eyes, the nose and the
  lips read by their light) and hiding the lines behind it. At rest the lines breathe; listening,
  waves travel in along them from the edges carrying your voice while it nods along; thinking, the
  lines undulate slowly against each other as it looks up; working, a bright line scans down the
  face and the lines shimmer, a ring for each step; speaking, its mouth moves with its voice and
  the words leave its lips as waves along the lines.
- **Membrane** (after Well): a soft, smiling face with closed eyes pressing into a curtain of fine
  vertical threads of silk, the threads bending round the head and the nose, the face drawn by the
  light where it presses (brow, nose, cheeks, lips, chin lit, the lids and the smile darker), a
  warm light behind the silk. At rest it barely presses and breathes, a sheen crossing the silk;
  listening, it presses closer with your voice, the threads bending toward it and ripples running
  in; thinking, it draws back, whole but fainter, the silk swaying in slow waves; working, the
  threads tighten and each tool step sends a ripple out from the face; speaking, its mouth pushes
  with the voice, the lips' press lit, ribbons of light leaving the lips along the threads.
- **Eye**: one large, friendly eye in particles of light (indigo to cyan to white, or the entity's
  colour): an iris of fine fibres dim near the pupil and bright at the rim, sparkling, a ring round
  the pupil, a catchlight, lids, crease and brow as rows of particles, curling lashes. As it speaks
  it smiles, its fibres glow with its voice and its pupil narrows on loud sounds; while you speak it
  opens wide, its brow lifts and its pupil widens; thinking, it looks up and aside, its lids lower;
  working, its gaze jumps from point to point.
- **Robots**, six classic ways of picturing a talking machine, each in its own colour (an entity's
  colour wins), each showing rest, listening, speaking, thinking and working (tools running):
  - **Lens**: a warm amber-red camera lens (a brushed bezel, dark glass with a reflection and a
    glint, a soft glowing core with fine iris fibres); only the core runs white. Soft waves of
    light leave the core as it speaks and come in to it with your voice; a soft arc sweeps the
    glass as it thinks; a light runs round the bezel as it works.
  - **Dome**: a droid with a panelled dome on a barrel body and side legs, seen from a little
    above. The dome looks around at rest, turns to face you to listen (its eye lighting with your
    voice), chatters with quick turns and light panels that follow the voice's bands, spins to
    think; working, its projector casts a small hologram.
  - **Valet**: a fussy, well-mannered gilded valet, head, shoulders, arms and hands, stiff and
    proper, its head moving in small servo steps. It surveys the room at rest; bows and cocks its
    head to listen (ear lamps glowing with your voice, hands clasped); frets as it thinks (head
    aside with a little shake, eyes dim and flickering, hands wringing); works precisely (a light
    ticking across its eyes, its head snapping from task to task); talks with its hands up and its
    head bobbing on the syllables, its mouth opening with the voice.
  - **Retro**: a gentle giant of the fifties in grey-blue metal, slow and deliberate: a glass dome
    with amber works turning inside (a spindle, a ticking cog, gyro rings), ear discs on antennae,
    a grille face with seven neon tubes, ribbed arms with claws, a chest panel of dials and lamps.
    The works tick slowly at rest and whirr as it thinks; the ear discs turn to you and glow as it
    listens; claws tick, dials step and lamps chase as it works; each neon tube lights to a band of
    its voice as it talks, with a slow nod on loud syllables.
  - **Deco**: a serene art-deco machine woman in aged bronze and gold, regal and unhurried, with
    cool rings of light passing around her. Two faint rings drift up her at rest; she inclines her
    head graciously to listen, the rings drawing in and brightening with your voice; her eyelids
    half close and the rings gather close as she thinks; six rings rise fast up her body as she
    works; her eyes and crest glow with her voice as she speaks, the rings pulsing out from her
    throat, her chin lifting.
  - **Rover**: a shy, curious little rover: two binocular eye boxes that tilt on their own like
    brows, lenses that zoom, a ringed neck that stretches, arms with paddle claws, a boxy body that
    bumps along on its tracks. It looks about and lifts a brow at rest; stretches its neck and leans
    in, eyes wide, to listen (a small flinch at a sudden loud sound); tilts its head, one eye up and
    one down, a claw tapping its chin, as it thinks; scans and rolls fast as it works; bobs and
    wiggles, brows up, a claw waving, as it talks.
  - **Hover**: a small round floating robot, polite and brave: a cream and brass barrel under a
    glossy dome, a dark red visor carrying two round red-amber eyes, stubby arms, three thrusters
    whose light fades below it (it never touches the ground). It bobs and surveys at rest; drifts
    closer and lower to listen, its eyes brightening with your voice; rises, turns aside and
    narrows its eyes to think, a light circling its visor; unfolds its arms (a whirring bit, a fan
    of light) to work, its thrusters flaring; pulses its eyes and dips on emphasis as it talks.
  - **Spark**: a curious robot on tracks who wants input: two lens barrels on a long ribbed neck,
    shutter plates that double as brows (they never frown), a torso with a blue core and a bar of
    lights, a shoulder frame with grippers, an antenna with a blue tip, big tracks with rolling
    treads. It glances eagerly and blinks at rest; leans right in, shutters wide and still, to
    listen; half closes its shutters, tilts its head and flicks its eyes between spots as it thinks,
    a spark running up its antenna; rolls its treads and scans as it works, its light bar counting;
    flutters its eyes, bobs and flaps its brows as it talks, with a lightning glint on the first loud
    syllable.
  - **Cruiser**: a sleek black car seen from the front, read only by its light (the sky on its hood
    and glass, lit edges, a shimmer), slim headlights, a red scanner sweeping in a slot on its nose,
    a road glow beneath (the screen's whole width on the talk page). The scanner sweeps slowly at
    rest; comes to the centre, narrows and pulses with your voice to listen, the headlights dimming
    politely; sweeps faster and wider as it thinks, its dash glowing; lights its headlights and
    edges, streaks past the horizon and races its scanner as it works; speaks through three
    segmented red voice bars on its dash.
  - **Android**: a calm android in pale gold skin with amber eyes, dark hair combed back from a high
    forehead; composed and curious. A precise, slightly too regular blink; it turns to you and nods
    politely to listen; tilts its head and raises a brow as it thinks, eyes up and aside; its eyes
    dart rapidly and a shimmer crosses its face as it works; it speaks with precise mouth movements
    and a hint of a smile.
  - **Sentinel**: a polished chrome helmet, head and shoulders, with a crest, a black slot across
    the face carrying one soft red eye that sweeps side to side with a fading trail, cheek vents, a
    ribbed neck and a collar of lamps; a calm guardian. The eye sweeps slowly at rest; comes to the
    centre, narrows and brightens with your voice as it listens, the head tilting toward you; sweeps
    faster and wider, a second light following, as it thinks; scans in quick short sweeps as it
    works, the collar lamps stepping and a faint beam fanning down; stays near the centre, wider and
    brighter with its voice, pulsing on the syllables, the helmet nodding on emphasis, as it speaks.
- **Ocean**: an evening sea filling the frame (the screen's whole width on the talk and Read pages):
  a sky from amber to night with stars, a moon in its halo, a low island with a lighthouse, and
  solid shaded water, each row lit by the slope of its waves (the sky reflected at grazing angles,
  moonlit faces, lit crest edges, glitter on the moon's path, whitecaps on the steepest crests). The
  swell travels across the frame, mostly left to right. Listening, the swell drops and rings spread
  from the near water carrying your voice; thinking, the natural swell gives way to parallel ranks
  of waves, then two regular trains crossing into a lattice of lit peaks, which dissolves back when
  it is done; working, a wind raises chop and whitecaps, the lighthouse beam swings, a ship's light
  crosses the horizon for each running tool and each step sends a ring across the water; speaking,
  its voice's waves roll toward you (low pitches long waves, high pitches short ones), the last
  1.2 s of the voice travelling from the horizon to your feet, crests lit in the app's hues, foam on
  loud syllables.

An entity's orb takes its colour and shape (planet, kitty, face, wave) from the gateway (with one of
the scenes chosen, an entity keeps its own shape and answers the voice as Nebula does). The microphone is open only while the orb listens.

While the assistant works, the orb shows the work: each tool call sends a ring of light out from the
centre (parallel calls a few tenths apart), a new thought a softer ring, an image or a recording
being made a slow wide wave, and a failed tool a short shiver; each tool running circles the planet
as a small satellite with a trail, dimmed as it passes behind.

## Interaction rules

- **Aurora**: the northern lights, curtains of light rays green at their foot and violet at their
  top, folding slowly over a dark ridge and mirrored in a still lake under the stars. Listening,
  waves run along the curtains toward the middle carrying your voice and they brighten; thinking,
  the rays gather into a corona overhead, turning; working, the curtains pulse in patches and
  their rays dance, brightening with each step; speaking, the rays rise with the voice's spectrum
  across the sky (low pitches in the middle) and their foot flares pink on loud syllables.
- **Murmuration**: a flock of starlings, black against a dusk sky from indigo to amber over a low
  line of land. At rest a long cloud drifting and folding on itself; listening, it swells with
  your voice and dark waves sweep through it; thinking, it turns into a slow spinning ring;
  working, it streams along a figure of eight; speaking, it stretches into a ribbon across the sky
  as thick as the voice.
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

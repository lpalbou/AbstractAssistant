# Changelog — AbstractAssistant for Apple Watch

Since 0.16.0 the watch app shares the iPhone app's version (`MARKETING_VERSION` in
`../../phone/iphone/project.yml`) and its release channel (TestFlight, then the App Store, inside the
iPhone app); the Python package's history is in
[../../CHANGELOG.md](../../CHANGELOG.md).

## [Unreleased]

### Added

- **Voices in groups, with their language (AbstractGateway 0.16.0 voice library).** Settings → Voice
  lists **Your voices** (cloned or designed on the iPhone or the desktop), **Engine voices** and
  **Shared voices** (the gateway's built-in voices and the ones its administrator shares), each with
  its language, and **Voices that speak** keeps one language's voices when the gateway offers
  several. Voices are created on the iPhone or the desktop; the watch says so.

### Fixed

- **Signing out signs you out, and the watch signs in on its own.** After a sign-out the watch came
  back signed in at its next launch: it took the iPhone's sign-in, which WatchConnectivity hands
  over again at every launch. The watch and the iPhone are independent devices: neither hands its
  sign-in to the other any more, and neither needs the other's app. Sign out also checks the
  credential is really gone from the Keychain and says so if it is not, and "Sign out and forget"
  forgets the account name too.
- **"Keep my sign-in" keeps it where you can find it.** Kept accounts are filed under their
  gateway (gateway → accounts, one Keychain item): the sign-in page offers an account on its own
  gateway only, and the gateway chooser lists every gateway signed into or with a kept account
  (with how many), plus AbstractFramework's always. A gateway the watch had been signed into by the
  iPhone or a launch argument used to be missing from the chooser, and with it its kept accounts.
  A kept sign-in that cannot be written says so. Earlier builds' kept sign-ins and gateways move in
  at the first read.
- **The Digital Crown scrolls Home again after Settings.** Closing Settings left the crown with
  nothing to scroll until a finger touched Home: Settings was drawn beside the navigation stack and
  took the crown's focus with it. It is now drawn over Home inside the stack, and Home is disabled
  while Settings is in, so the crown returns to Home on its own when Settings goes.

### Changed

- **The voice list is read compact.** Settings → Voice asks `GET /voice/voices?compact=true`: the
  same voices without the engines' duplicated source catalogs (1.4 MB → 250 KB on a gateway with the
  shared voice pack), so the list loads within the watch's read timeout over the iPhone's link.

- **Finer schedule choices.** Every 30 seconds, minute, 5, 15 and 30 minutes, then every hour, 2,
  4, 6, 8 and 12 hours, day, 2 days and week, when editing an automation and when creating one. An
  interval written in seconds reads as minutes ("Every 60s" is "Every minute"). The gateway still
  refuses less than a minute for an automation that reads a mailbox or a feed, and says so.

- **A question that could not be sent keeps its recording.** When the upload or the transcription
  fails, the orb says "Not sent." with Retry and Discard under it; the recording
  waits in its own file through leaving the page and relaunching, and nothing sends it on its own.
  Retry sends the same recording; Discard deletes it. (Backlog 1054, slice 0.)
- **A haptic when listening starts**, as there was one when the microphone closes and when an
  answer arrives.
- **The sign-in lives in the Keychain, shared through the app group.** A Keychain item of the
  app's service, readable after the first unlock (the notification extension reads it while the
  device is locked), bound to this device, never in a backup, never synced; the app group doubles
  as the access group so the extension (and, on the watch, the complication) read the same item.
  Until now it was a file in the app group sealed with a key kept beside it, which protected
  nothing; that file (and the plain one of the interim builds) is moved into the Keychain at its
  first read, so nobody signs in again. The watch's kept sign-ins moved from UserDefaults into a
  second Keychain item (backlog 1053).
- **The hold on the orb is shorter and its ring smaller.** A hold toggles in about a second
  (1.05 s, 30 % less than before) and its ring closes well inside the screen instead of reaching
  past its edge.
- **The read-aloud button is a speaker, not a play button.** Beside Back on the orb page and
  on an automation's page, the voice button shows a speaker at rest (pause while it speaks, as
  before); its spoken label is "Read aloud".

- **One gateway client for the watch and the iPhone (backlog 1053 step 3).** The iPhone's copy of
  this client (`PhoneGatewayClient`) is folded back into `Packages/AbstractGatewayClient`, which now
  holds every route and wire model either app uses; the iPhone's `AssistantKit` depends on it. For
  the watch: an error the gateway explains shows its words (`detail`) instead of the generic line;
  a recording is uploaded under `voice/dictation/`, so the iPhone's file list tells it apart from a
  file; the archived conversations are read page after page instead of one page of 200; a
  workflow the gateway marks archived, deprecated or not runnable is not offered; an entity row's
  `slug` is its name when the gateway sends one; a discovery that reports an error fails the read;
  speech that meets a 401 stops the client as every other call does. The sample client takes a
  world (`MockGatewayClient(world: .watch)`); its data, launch hooks and timings are the watch's.

### Added

- **One product with the iPhone (version 0.16.0, build 39).** The watch app is now the companion of
  the AbstractAssistant iPhone app: it ships inside it (bundle id
  `ai.abstractframework.assistant.watchkitapp`, complication `….watchkitapp.orbclock`), installs on
  the paired watch with it, and runs and signs in on its own, without the iPhone app. The iPhone
  and the watch share one version from now on: 0.16.0, the next number after the desktop app's 0.15.0.
- **Notifications while the app is closed (Apple push, framework backlog 1049).** The watch
  registers its push token with your gateway at each sign-in, on each new token and at most once a
  day, and removes it at sign-out; nothing to set up. Its notification service extension fetches the
  event from your gateway and shows "Approval needed" / "A question for you" (time-sensitive; a tap
  opens what waits for you), "<automation> has a result" / "<automation> failed", or a published
  alert's title; "From an earlier sign-in" for a push meant for another sign-in. The app's own catch-up
  never shows an item a push already showed. Pushes are sent once your gateway has a push forwarder.
- **Choose the gateway on the sign-in page, and come back with one tap.** The sign-in page has two
  lines in the same capsule: the gateway (the last one signed into, else
  `gateway.abstractframework.ai`) and "Sign in with user or email". A tap on the gateway opens a
  chooser with every gateway the watch has signed into (most recent first, at most 8, the current
  one ticked) and "Another gateway…" to type an address. Sign out now asks first: "Keep my sign-in",
  "Sign out and forget" or Cancel. A kept sign-in shows on the sign-in page, for its gateway, as
  "Sign in as <user>" (at most 3), and one tap signs in with it. It is forgotten when the gateway
  refuses it, when you sign out and forget, or replaced when you sign in again as that user with a
  new credential. Kept sign-ins are a second Keychain item, beside the current one. The field starts with the user signed in last only when no kept row offers that user
  (one way into an account, never two), and empties when another gateway is chosen.
- **A readout of the notifier, for a debug build.** Launching with `--dump-notify` (the console
  attached: `xcrun devicectl device process launch --console …`) prints the system's permission,
  the toggle, when the watch last looked (the background refresh and launches, the last 40, kept
  on the watch), the runs and waits already posted, the notifications still in Notification
  Center and the face's snapshot: what to read first when a notification seems missing.

### Changed

- **The sign-in lives in the Keychain, shared through the app group.** A Keychain item of the
  app's service, readable after the first unlock (the notification extension reads it while the
  watch is locked), bound to this device, never in a backup, never synced; the app group doubles
  as the access group so the extension and the complication read the same item. A sign-in kept by
  0.5.0 or an interim build is moved into the Keychain at its first read, so nobody signs in again.
  The sign-ins kept with "Keep my sign-in" are a second Keychain item (backlog 1053).
- The project moved: one XcodeGen spec for the iPhone and the watch, `phone/iphone/project.yml`
  (`AbstractAssistant.xcodeproj`); `scripts/build.sh`, `test-watch.sh`, `deploy-watch.sh`,
  `run-live.sh` and `testflight.sh` use it. The empty iOS container target is gone.
- **The top row sits on the time's line, on every page.** Back (and the gear on Home), the page's
  title and the icons beside Back (Share, Stop, the shield, the voice button) are centred on the
  system time, 10 pt higher than before: every page starts higher. The title leaves the time its room at the right. The orb page's tools, which
  mirror the keyboard's distance from the top, follow the band.
- **The top row's icons are the time's size.** Back, Share, the voice button, Stop, the shield and
  the pencil are 28 pt circles (20 % smaller), centred on the time; the band under the row is 45 pt.
  The keyboard, tools and info icons beside the orb keep their size.
- **The hold on the orb is shorter and its ring smaller.** A hold toggles in about a second
  (1.05 s, 30 % less than before) and its ring closes well inside the screen instead of reaching
  past its edge.
- **The read-aloud button is a speaker, not a play button.** Beside Back on the orb page and
  on an automation's page, the voice button shows a speaker at rest (pause while it speaks, as
  before); its spoken label is "Read aloud".
- **A question that could not be sent keeps its recording.** When the upload or the transcription
  fails, the orb says "Not sent." with Retry and Discard under it; the recording
  waits in its own file through leaving the page and relaunching, and nothing sends it on its own.
  Retry sends the same recording; Discard deletes it. (Backlog 1054, slice 0.)
- **A haptic when listening starts**, as there was one when the microphone closes and when an
  answer arrives.
- **Settings → Connection's "Sign in as someone else" is "Sign out"**, a red button, and asks
  whether to keep the sign-in, as Sign out at the bottom of Settings (red too) now does.

### Fixed

- **A background look that could not read the event stream read nothing else.** The 15-minute
  check asked `/me/events` first and ran the older reads (`/automations`, `/waits`, which feed the
  face's badge and the "finished" notifications) only on a 404; a timeout, a 401 or a proxy's HTML
  page ended the look with nothing updated. The look now answers three ways (read, no stream,
  failed) and the older reads run in the last two. A gateway without the stream is remembered for
  a day, per gateway, so it is not asked again on every look.
- **An image opened full screen started a band too low, its Share button with it.** The image page
  and the web link page each drew the top row twice (`.screen("")` beside `.besideBack`), and each row
  took its own 58 pt band: the picture started 116 pt down, letterboxed in the half-screen left,
  and Share sat a band under Back. Each page now draws the row once; a page that draws two stops a
  debug build with a message, and the UI tests check that Share sits on Back's line.
- **An image opened full screen is centred on the page.** A wide picture is centred on the whole
  screen (its top clear of the row); a taller one sits as near the screen's centre as the row
  allows, starting right under it, not centred in the area below the row, which left it low.
  Zoom (the crown), drag and double tap keep the picture within the screen from wherever it
  rests. The UI test checks the picture's own frame against the rule.

### Known issues

- On a development build, a push can keep its generic words ("Approval needed", "Tap to read it")
  when the notification service extension does not replace them. The extension records why in the
  app group; `--dump-notify` prints it under "push extension".

## [0.5.0] - 2026-10-25

### Added

- **What happened while the app was closed, from your event stream.** The background check (about
  every 15 minutes) and each launch read your gateway's event stream once (`/me/events`, one request,
  no stream in the background): a new approval or question is a time-sensitive notification ("Approval
  needed", "A question for you"; a tap opens what waits for you), a new automation result is a quiet
  notification ("Morning digest has a result"), and the complication's "needs you" and "news" follow
  it. Nothing from before the watch first looked is posted. An older gateway keeps the previous check.
  Each notification the watch shows is recorded on your event stream (`channel: "watch"`, the watch's
  own device id; one request per notification shown, none otherwise), so your other devices can tell.

- **Your avatar on your watch face.** The Assistant complication, for the circular, corner, inline
  and rectangular slots (and the Smart Stack): the orb style you chose, as the app draws it (the
  app's own orb until the app has opened once), in three states: at rest; speaking with a dot when
  there is news (results or messages you have not seen); listening with an amber badge giving the
  number of approvals and questions waiting for you. The rectangular slot adds what needs you
  first, your next automation and the results you have not seen. Under Assistant in the face's
  Edit screen. A face that draws its complications in one tint shows the orb's light in that
  tint, as a mask, so your style keeps its shape there instead of a flat grey disc.
- **Notifications when an automation finishes.** "Morning digest finished", with the first words of
  its answer (a tap opens it): a banner when the app is open, a notification from the background
  check otherwise. Settings → Notifications turns it off.
- **An automation's page opens at once** on its latest run (as the list has it) while its ten
  latest runs are read; a large spinner shows only when there is nothing to show yet (a run never
  read, a notification's answer on its way).
- **New automation sets how much it remembers.** With "Builds on earlier runs" on, it shows how
  much of its earlier runs each run reads (the gateway's default, 50,000 tokens on yours) and takes
  a new number, as Edit does.

### Changed

- **Lens fits whole on the talk and read-aloud pages**, clear of the top row; every other design
  keeps its size.
- **Run says when it is already running**, and an automation's details read it fresh, so Stop shows
  while a run is on its way.
- **Approve all, for a conversation and an automation alike.** An approval offers Deny, Approve
  and Approve all wherever it is opened (the orb page, Needs you, a notification). Approve all is
  for the run's own owner: its conversation, by that conversation's tools, or its automation, by
  the automation's own tools; another conversation is never touched, and sends always ask. The
  watch approves what was allowed as soon as it sees it; an automation's details say what is
  allowed for its runs, with Ask again.

## [0.4.0] - 2026-10-21

### Added

- **Search automations.** The Automations page has New and Search on one line, as Sessions: Search
  lists the automations whose name or task holds the words.
- **How much an automation remembers.** When an automation builds on its earlier runs, Edit shows
  how much of them each run reads ("Reads up to 50,000 tokens", the gateway's value) and takes a
  new number (numbers only).
- **An automation is a conversation.** It opens on the same orb page as a conversation: its runs
  are the messages (what its trigger sent, when, then the answer), the orb follows a run in progress
  and speaks its answer, Share and the voice work the same. Its details (when it runs, Run now,
  Edit, its instructions) are behind (i), where a conversation has its tools, or a swipe forward.
  Talking there opens a conversation about it, seeded with its runs; the automation's own runs
  never read it.
- **Four more machines.** Hover (a small round floating robot, polite and brave, that drifts closer
  to listen and unfolds its arms to work), Spark (a curious robot on tracks with shutter brows that
  leans right in for input and flicks its eyes as it thinks), Cruiser (a sleek black car whose red
  scanner sweeps as it thinks and whose dash shows three voice bars as it talks, the screen's whole
  width on the talk page) and Android (a calm android in pale gold with amber eyes, a precise blink,
  a tilt of the head and a raised brow as it thinks) and Sentinel (a polished chrome helmet whose one
  red eye sweeps side to side, faster as it thinks, steady and bright as it talks). Thirty-four
  styles in six families.
- **One corner button.** The button at the top left is the same on every page and never moves:
  the gear on Home, Back everywhere else, morphing from one to the other. Settings opens from the
  left, where its gear is, and its pages follow it from the left too.
- **Send while it listens.** While the orb listens, a Send button sits where the tools icon is at
  rest: what was said goes now (a noise that starts would keep the silence that sends from
  coming). It works from the first moment, before the microphone has even opened.
- **Four new orb styles.** Contour (a face raised in lines of light, after Wave) and Membrane (a
  face pressing through a fabric of light, after Well) in Faces; Aurora (the northern lights over a
  lake, gathering into a corona as it thinks) and Murmuration (a flock of starlings at dusk) in a
  new Nature family, with Ocean.
- **Files previewed on the watch.** A tap on a file of the conversation's page opens it; a swipe
  up shows the next file, a swipe down the one before (or turn the crown), with its share button
  beside Back. Pictures show, drawings (SVG) are drawn on the watch, texts show their start, a
  recording or a video opens to play. An SVG picture opens drawn as well.
- **Cosmos: three new orb styles.** Well (the fabric of space bending into a well round a mass;
  ripples carry the voice, two masses circle each other and send out gravitational waves as it
  works), Black hole (a ring of light round a shadow as it was photographed: gas falls in to
  listen, a disk to think, jets to work, the ring following the voice) and Accretion (a young star's
  disk of dust: it gathers into clumps to think and merges into planets to work).
- **New orb styles: five state shapes, Face, Imprint, Hologram, Eye, six robots and Ocean** (first launch and Settings →
  Orb style).
  - **State shapes**: five orbs with one shape per state (listening, thinking, working with its
    tools, speaking), morphing from one to the next: **Lotus** (a bud that blooms), **Crystal** (a
    crystal that grows wings), **Eclipse** (a golden eclipse), **Synapse** (a network that bursts
    into a star) and **Drop** (a drop of light that pours out as a horn).
  - **Face**: a sculpted bust in light (the face's real relief lit as it turns, glowing eyes). It
    blinks, breathes and moves its head a little. Its lips follow its own voice like speech: open
    on loud sounds, rounded on dark vowels, wide on bright ones, closed in the pauses. While you speak it turns its head and cups a hand behind its ear, your voice
    arriving as arcs in the hand's cone; it looks up and aside while it thinks.
  - **Imprint**: the face, zoomed in, pressed against a pane of glass: only what touches the pane
    shows, most of the face at rest with its eyes and mouth open. It presses in and opens its mouth
    as it speaks, lays its cheek on the pane while you speak, and draws back while it thinks.
  - **Hologram**: the head as glowing scan lines, its eyes and smile over them: light pulses along
    the lines from its mouth as it speaks, they ripple while you speak, and a scan sweeps down the
    head while it thinks.
  - **Eye**: one large, friendly eye: its iris glows with its voice and it smiles as it speaks; it
    opens wide, pupil widening, while you speak; it looks up and aside while it thinks.
  - **Robots**, each in its own colour and showing every state (rest, listening, speaking,
    thinking, working): **Lens** (a glowing red camera eye), **Dome** (a dome-headed
    droid that turns to face you and chatters with its lights), **Valet** (a gilded humanoid head that
    talks with its whole head), **Retro** (a glass-domed robot whose grille of lights follows its
    voice), **Deco** (an art-deco machine woman with rings of light passing around her) and **Rover**
    (binocular eyes on a neck that lean in to listen).
  - **Ocean**: a sea at night across the screen's whole width, with a moon and its glade. Its waves are shaped
    and lit like real ones (sharp crests, the moon reflected off each wave, foam on steep crests);
    a voice raises them, toward you while it speaks and away while you speak; while it thinks the
    sea calms and rain falls.

### Changed

- **Nothing behind the top row.** Every page starts below the row of the corner button, the title
  and the time, and is cut there, scrolled or not.
- **An automation's runs you have not seen** show in an orange badge on its row; on or off moved to
  Edit, with how often it runs. Its details' play button is now "Run".
- **Instructions are gone** from an automation's details and Edit: the watch edits its title and
  its task (anything else its workflow was given stays as it is).
- **Rewinding is twice as fast:** holding the voice button goes back 8 s a second at first, with a
  bump every half second.
- **Tools follow Settings.** A default stays as you set it, even when the gateway's own choice for
  that tool changes. "Use my defaults" also puts the conversation's workflow back on the default,
  and choosing the workflow a conversation already runs is not counted as a change. An answer opened from a
  notification opens its own conversation, with that conversation's tools. A new conversation with
  an entity is a new one.
- **Membrane redone.** A soft, smiling face with closed eyes pressing into a curtain of silk
  threads, drawn by the light where it presses; it presses closer with your voice, draws back as it
  thinks, ripples as it works and pushes with its voice as it speaks.
- **Eye in particles again.** Its iris, lids, brow and catchlight are particles of light in the
  planet's colours as before, under the lids, lashes, blink and gaze it has now.
- **Ocean is a real sea.** An evening sky over solid, shaded water lit by the slope of its waves,
  a moon's path of glitter, whitecaps, a lighthouse on a low island; the swell travels across the
  frame. Listening, rings carry your voice across the near water; thinking, the waves fall into
  order (parallel ranks, then a lattice of lit peaks) and loosen again when it is done; working, a
  wind raises chop while the lighthouse beam swings and a ship's light crosses for each running
  tool; speaking, its voice's waves roll toward you with foam on loud syllables.
- **The robots have characters.** Valet is a fussy, proper gilded valet with arms and hands (it
  frets as it thinks, talks with its hands up); Retro a gentle giant of the fifties, slow and
  deliberate, the works in its dome whirring as it thinks and neon tubes flickering as it talks;
  Deco a serene, regal art-deco machine woman whose rings of light gather as she thinks and pulse
  from her throat as she speaks; Rover a shy, curious little rover, far more animated (brows that
  tilt on their own, a neck that stretches to listen, a claw tapping its chin as it thinks, a
  wiggle as it talks).
- **Every orb and avatar refined**, with Wave and Well as the reference: soft light, a gradient of
  hues, rounded friendly forms, each phase readable at a glance, smooth morphs, and less work per
  frame. The planets are shaded spheres of light with a soft limb; Halo's corona, Vortex's arms,
  Nebula's cloud and Liquid's waves are coherent shapes; Lotus, Crystal, Synapse and Drop are
  larger and brighter; Eclipse is a soft gold corona. The faces are warm portraits in light (a
  smooth skin, open friendly eyes, a smile; Imprint stays a whole face while it thinks; Contour's
  head is round and its words leave as ribbons; Membrane keeps the face while thinking); Eye has
  lashes and a warm iris; Rings are glowing lines through the hues. The robots have lit metal
  bodies and warm round eyes, Lens a warm glowing lens. Well, Black hole, Accretion, Aurora and
  Murmuration are softer; Ocean is a sea of lines of light with a moon path, rain while it thinks
  and a lighthouse while it works.
- **Home's orb starts a new conversation** every time; an earlier conversation continues from
  Sessions (the orb used to reopen the last one).
- **The faces speak and listen.** The face's relief is more anatomical (the nose's bridge and wings,
  the philtrum, a cupid's bow, the cheekbones, the folds from nose to mouth, the jaw). Face's and
  Imprint's mouths open with the voice, the jaw dropping and the lips parting as words are spoken
  (they barely moved), the teeth showing on open syllables; the brows lift on stressed syllables
  and the head nods with the phrasing; listening, they nod along with your voice.
- **Hologram is gone** (a watch that had it shows Halo).
- **Swipes as in a browser.** On every page a swipe to the right (the finger moving right, as with
  watchOS's own Back) goes back to the page before, one page at a time, down to Home; a swipe to
  the left goes forward again to a page you came back from, and does nothing when there is none
  (on Home at launch, neither swipe goes anywhere). Swipes move between the app's own pages (Home's
  lists, a conversation, an automation, the settings); a page you open from what is on one of them
  (a message, its steps, a picture, a link) opens with a tap only. A swipe across a row never opens that row. A
  conversation opened from Sessions opens on top of Sessions, so going back returns to the list.
- **The conversation's page.** From the orb page of a conversation with at least one message, a
  swipe to the left opens its numbers (questions, tool calls, thinking steps, when it started and last
  moved) and its files (what its turns made or were given, and the files its assistant wrote into
  the conversation's folder; your spoken questions left out), each card with its share button on
  the right.
  Its exchanges open from Every exchange there (the swipe on a Sessions row is gone: swipes move
  between pages). A swipe back on an automation's edit page with unsaved changes asks to save or
  discard them, as Back does; a zoomed picture pans without leaving its page.
- **Buttons that follow what it does.** Beside Back: Stop while it is busy (listening, thinking or
  working, speaking or paused), Share at rest; while it works after an Accept all, the shield that
  takes it back sits beside Stop (it was at the bottom right). A 1.5 s hold on the orb does what
  Stop does, a ring closing round it as you hold, and at rest reads the last answer aloud: one hold
  toggles between listening and reading. A hold let go early does nothing (it is not a tap).
- **The web viewer shows images**: a link to a picture shows the picture; a page shows its lead
  image above its text.
- Round icons are centred by eye (the share, back, speaker, shield and play glyphs sat a point or
  two off).
- **Every orb, refined and speaking the same phases.** All twenty-two styles show the same five
  phases (at rest, listening, thinking, working with tools, speaking), each with its own motif, and
  blend from one to the next: the planets' thinking sweeps bands across them and their working
  gathers points into a streaming ring; Face is a sculpted bust in light that reads while it works;
  Rings run a wave across their rings; Hologram and Imprint scan; Eye reads (quick fixations);
  Ocean's lighthouse sweeps the water. The points glow, surfaces are sampled evenly and lit, the
  voice's shapes stay inside the orb, and the ring a tool call sends out is a fine line.
- **Each planet thinks and works in its own way** (Halo's turning crown of rays, Vortex's
  whirlpool, Nebula's forming stars, Liquid's lava lamp, Galaxy's forming disc; and their work).
  **Rings** show the voice's harmonics: each ring grows or draws in with its own band. **Eclipse**
  speaks with a living rim (the voice's spectrum around it, a travelling crescent, a flare on loud
  syllables). **Face** and **Imprint** are friendlier: soft frontal light, real eyes with a
  catchlight (Imprint's closed and serene), a calm smile, a mouth that opens naturally.
- **New style: Wave** (Forms): ribbons of light, each a harmonic of the voice, that wind into a
  turning swirl while it works.
- **The orb styles by family.** Settings → Orb style (and the first-launch question) lists the
  styles in four families (Orbs, Forms, Faces, Machines), each with a small live orb and a few words;
  a style opens a live preview that goes through the phases, with "Use this".

- Home's orb is 20% larger; the orb on the talk and Read aloud pages is 10% smaller.
- The orb's line no longer keeps "I didn't hear anything" (or an earlier error) once the orb
  speaks.
- **Rings** is a geodesic structure of six rigid rings: each ring turns with its own part of the
  voice (low to high pitches), so the structure comes alive as you speak and settles back in the
  pauses; it spins up while it thinks.

### Fixed

- A conversation about an automation can be archived from Sessions.
- **A voice gone silent mid-answer** (a pause then a resume brought it back): the system can stop
  the player underneath, with an audio interruption, with the app suspended while the wrist is
  down, or when the keep-awake session ran out, and the reading stayed "speaking" over silence.
  An interruption now pauses the reading and resumes it when the system allows; the app coming
  back in front plays on from where the voice stopped; the keep-awake session is renewed while a
  long answer is read; a recording's row leaving the screen no longer turns the voice's audio off.
- **Battery through the night.** With the screen dimmed (wrist down) or the app in the background,
  nothing runs: the orbs hold their last frame (they drew at full rate whatever the screen showed),
  the poll in flight finishes and none follows (it went on every 15 s), the automations page reads
  nothing. The background stream that follows a question's run for a notification starts only once
  the app is left with the run still working (it started with every question, kept the radio busy
  with a keep-alive every 5 s and stayed open up to two hours), one per run, with a keep-alive every
  50 s, ended when the app sees the run end and given up after an hour. The 15-minute background
  refresh reads the waits alone unless one is new. A conversation whose question cannot be read was
  fetched again on every poll. Starting a new conversation, or dropping the voice player, let go of
  the keep-awake session (it ran its full ten minutes). The build on the wrist is optimised; the
  orbs do less work per frame (Contour, Membrane, Aurora, Murmuration) and run slower at rest.
- The tools and keyboard icons on the orb page take a tap a little beside their circle: a tap that
  missed by a few points paused or resumed the voice instead.
- Wave changes state without a jump: its motions keep their pace and only how much of each shows
  changes.
- With the Assistant's workflow, a request about the picture it just made ("make it simpler",
  "in white") starts from the conversation's newest image, as on the iPhone; the watch did not
  send it, so the Assistant asked for an image to be attached.
- The orb page keeps its layout however it is reached: coming back to it scrolled (from a message,
  for instance) no longer shifts the orb, its icons and "who answers" down the screen.
- After Accept all, the tools of the call you approved no longer ask again, including those that go
  where the assistant picks (opening web pages); sends to other people still ask every time.

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

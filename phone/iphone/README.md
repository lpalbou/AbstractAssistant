# AbstractAssistant for iPhone

A quiet place to think, ask, and pick things up again. A native SwiftUI client for your
AbstractGateway, with the conversation at the center and the controls you need close by.

**iPhone · 0.16.0 · iOS 26+** · with the [Apple Watch app](../../watch/apple/README.md) inside

AbstractAssistant is one product for iPhone and Apple Watch: install it on the iPhone and the
watch app comes with it. Sign in once on the iPhone and the watch is signed in too.

## Three small spaces

- **Assistant.** Type a message, or **tap the orb to listen**. After you speak, three seconds
  of silence prepares your transcription for review in the text composer. Edit it, then tap
  Send. Turn on **Send voice messages automatically** in **Settings → Voice & reading** for
  direct sending. Speaking again restarts the countdown; tap the orb during capture to cancel. Separate floating **+**, **keyboard** and orb controls
  keep the conversation open. The keyboard button expands the editor across the available
  width and hides the orb. Tap outside to dismiss the keyboard and restore the controls,
  preserving your draft. While listening, only a small Listening label appears above the orb.
  The orb’s ribbons react to microphone and read-aloud playback levels. While the assistant
  works, it morphs into a lit rounded square with a mint/lavender Stop symbol: tap it
  to stop the response. After confirmation, **Edit and resend** opens the stopped request
  with its original text and attachments; edit it and tap Send to start a new reply while
  keeping the earlier turn. The same contour returns to the sphere when work ends. Progress appears once
  in a collapsible activity panel. It shows model cycles, tool calls, public results and
  failures. When a tool needs approval, **Approval needed → Review tools** appears directly
  in the conversation, and the orb’s cords morph into an orange raised hand. Tap the hand
  to review **Approve**, **Deny** or **Approve all**; tapping it never approves automatically.
  Connection loss is reported separately from run failure. The orb
  returns when the gateway confirms the run has ended. Completed activity moves into cycle
  and tool-count buttons beside the answer’s speaker.
  New submissions reveal the latest messages. While following a reply, the conversation
  stays with incoming text, media and keyboard changes. Scroll up to read earlier messages;
  **Latest messages** returns to the reply and resumes following. Cycles opens a connected progression
  per agent, with expandable model details and approval context. Tools opens the individual
  calls with recorded input, output and timing, plus search.
  Positive-only file, email and web actions open compact source collections; file views
  also open the conversation’s workspace browser.
  Conversations are durable gateway sessions. Open the stack icon to continue one from
  your phone, desktop, Watch or browser. Reloading restores every turn’s public answer without
  reading old replies aloud. Tap the current name and chevron to choose **Assistant** or an entity, or create an entity.
  Share the conversation from the toolbar, copy an answer, or ask the gateway to read it
  aloud; pause, resume and stop playback.
  Review adds the transcription below any existing typed draft. Automatic sending keeps
  that draft separate. The **+** button serves text and voice.
- **Inbox.** Questions and tool approvals, followed by recent activity. Approvals show every
  action and its complete arguments. **Approve** allows the pending request; **Deny** refuses
  it. For the open conversation, **Approve all** temporarily permits its enabled Approve
  tools while this iPhone follows the conversation. An orange shield beside **Tools** removes
  those grants in one tap; Approve tools ask again from the next unanswered call. Auto and
  Off settings stay unchanged, and already approved calls may finish. Off, unavailable and
  newly added tools remain outside the grant. **Tools** also lists the temporary grants.
  Older grants saved as Auto offer a one-time review to choose which tools should ask again.
  Questions still require an answer. Decisions already made on another device cannot resume
  a different wait.
- **Automations.** See your routines, what starts each one in words ("When Python news has a new
  item", "When mail arrives in you@example.org", the schedule), and the latest 20 runs. Tap a dated run card for its explanation, attempts, recorded error and expandable activity; results refresh while the detail screen is open. Run an
  active or paused routine now, pause it, or resume it. Tap **New automation** (or **+** above an existing list) to create a routine: enter a short title, choose a workflow and its inputs, and select an
  interval or daily time, choose its tools, and decide whether it builds on earlier runs.
  Assistant workflows keep the separate task-instructions field.
  The picker includes all runnable workflows your gateway offers, including workflows without
  an Assistant interface. Selecting one loads its named inputs with defaults; fill required
  inputs before creating it. Booleans and choices have controls, and structured values accept
  JSON. **Create automation** is the mint primary action.
  Daily times use your account’s time zone, which the creation screen displays. Editing
  an existing routine’s tools is available on its detail screen; other definition changes
  remain in the gateway console.

When creating an automation, **Build on earlier runs** reveals **History token budget**.
Leave it blank to inherit the gateway’s default (50,000 tokens in the runtime shipped with
this feature), or enter a positive whole number. The displayed default comes from your
gateway. The budget limits retained history rather than the length of an individual answer.

The app uses your account’s Assistant workflow preference (`abstractassistant.agent.v1`), or
the gateway’s Assistant default when you follow the default. If it is unavailable, choose an
available workflow in **Settings → Workflow**. Saving changes the Assistant preference
for your account across devices and applies to the next message, keeping your draft and history. The phone never switches
to another agent interface or runs models locally.

## Notifications and badges

The app follows your event stream on the gateway: it reads what happened when it opens and when
you come back to it, then stays up to date while it is on screen. A new approval or question
arrives as a time-sensitive notification ("Approval needed", "A question for you"); tap it to
open the Inbox and answer. A new automation result arrives as a quiet notification ("Morning
digest has a result"); tap it to open Automations. The **Inbox** tab's badge counts what waits for
you and the **Automations** tab's badge counts results you have not seen. iOS asks for permission
the first time there is something to show. What happened before the app first looked is never
notified. A gateway without the event stream keeps the app's regular refresh; notifications then
do not appear.

## Voice and files

**Settings → Voice & reading** offers **Send voice messages automatically** (off by default),
automatic reading of new replies, the gateway’s
speaking voices and its transcription models. Voice choices stay on this iPhone, scoped
to your account and gateway. **Gateway default** sends no override; entities retain their
own speaking voice. Tap a voice to select and hear it automatically. Speed choices
**1×, 1.15×, 1.3× and 1.5×** also play a sample and apply to all read-aloud playback.
Restored history is never read automatically.

**Tap → speak → three seconds of silence → review → Send.** By default, the transcription
opens in the keyboard composer for corrections; no Assistant request starts until you tap Send.
Pending attachments remain available, and existing typed text is preserved above the transcription.
Enable **Send voice messages automatically** to send the transcription directly while preserving
your separate typed draft. This preference is saved per account on this iPhone.
Capture stays on the iPhone until the
silence countdown ends. Speaking again restarts that countdown. Tap the orb
to discard pending voice without uploading it. A tap without confirmed speech times out
after eight seconds, and the one-minute recording limit discards an unfinished message.
Leaving chat, changing conversations, opening the keyboard, backgrounding or an audio
interruption cancels pending capture. Once the countdown finishes, upload/transcription
has begun; canceling then stops the pending turn but cannot retract audio already uploaded.
The same tap interaction works with VoiceOver's double-tap activation.

The orb uses measured microphone/playback energy for its silhouette, rings and light.
Listening adapts to your microphone’s recent volume range; playback uses its own scale.
While waiting for transcription or for speech to start playing, its cords morph into a rapidly
rotating geodesic sphere with **Transcribing** or **Preparing speech** above it. Tap to cancel
the pending speech operation. It returns to the listening orb for playback or an editable
transcription for review.
Reduce Motion retains signal-driven light while freezing geometry and rotation. Silence
detection uses local microphone power; room noise and very quiet speech can affect it.

Use **+** beside the composer to attach a file, choose a photo/video, take a photo or record
a short video. Uploaded file chips remain until you send or remove them.
**Conversation files**, from the toolbar’s **folder** icon or **Browse session files** inside file
activity, includes actual workspace files and stored attachments. Open a folder to follow its
hierarchy; tap a Markdown document to read it, or preview/play/share other files. Separate
workspaces are shown when the session’s runs use different folders. Files are fetched afresh
when opened, so an edited workspace document does not show an old cached copy.

**Conversation audio** is off by default. Turn it on to see dictation, its transcripts and
read-aloud recordings. Explicit user attachments and voice files returned by the assistant
remain visible. New dictation has explicit provenance. For older recordings the app first
checks every turn’s input/output references, then uses linked upload/transcription and TTS
metadata; the modal identifies this as inference. If history cannot be fully checked, older
ambiguous files stay visible. This filtering never deletes anything.
Attachments retain their gateway artifact and owning-run references. Credentials never
travel in a share link or to an AI-provided URL.

Choose **Assistant orchestrator** in **Settings → Workflow** to generate images and voice
through the gateway’s configured providers. Ask for an image, attach one and ask for an
edit, or ask for a voice recording. Generated files belong to their AI message, including
when you reopen the conversation. Images show an inline preview: tap to enlarge, share,
or use the image as a reference for the next message. Voice files have their own play,
pause, seek and stop controls. Playback also animates the orb. Generated audio stays quiet
until you play it; automatic reading does not synthesize a second version of that reply.
The gateway must offer the requested modality; generation errors appear in activity.
Use a gateway release that supports generation through its configured media endpoint profiles.
The app uses those profiles without storing provider credentials on the phone.

Inline images reload when you reopen a conversation or relaunch the app. Opening and closing
an image or switching tabs preserves its preview. Image loading continues while its message
scrolls off screen; switching conversations cancels pending downloads. If a file cannot be
retrieved, tap **Try again**. Opening an image also restores its inline preview.

Local copies opened through Conversation files are removed when you dismiss the viewer or
open another file. Inline previews use a disposable conversation cache, bounded to six files
with a 128 MB eviction target. The current viewer, playing audio and newest download are
protected from eviction, each subject to the 256 MB file limit. Switching
accounts or conversations cancels pending downloads and clears the cache. Imported copies
are removed after upload; recordings are removed after transcription or cancellation.
Disposable files left by an interrupted app are cleared on its next launch. Your originals
and gateway attachments are preserved.

Uploads are limited to **25 MB each**; generated-media previews stream to disk with a
**256 MB per-file limit**. The gateway may impose a smaller limit.
Camera videos are capped at 30 seconds. Entity chat’s current gateway interface accepts
text only, so file messages are available in Assistant conversations. The files list shows
attachments in pages of 500 with **Load more attachments**. Workspace summaries inspect up
to 1,000 entries per workspace; a **+** count signals more or incomplete results. Folder
browsing offers **Load entire folder** when its listing is limited. Workspace discovery and
activity history each inspect up to 64 runs and disclose limits. Text previews show up to
200,000 characters; sharing retains the complete downloaded file.

## Conversation tools and answer statistics

Open **Settings → Default tools** to choose defaults for all sessions and new automations
on this iPhone, scoped to your gateway and account. Tap the **Tools** icon in the middle
toolbar island to override those defaults for that session. The same editor is
available under **Tools** when creating an automation and on its detail screen.

Available categories are highlighted and listed first. Categories needing gateway setup
follow in muted styling. Expand a category or search by category, name or description.
Tap a mode directly to create an override:

- **Off:** the agent cannot use the tool.
- **Auto:** approve automatically.
- **Approve:** ask before running it.

Session choices take precedence over Settings. Automation choices also take precedence
over Settings. Use the defaults switch to inherit again; **Save** commits the current
context and **Close** discards unsaved edits. Existing Assistant defaults from earlier
versions migrate to the shared Settings defaults.

Automations save a snapshot of the resolved tools and approval choices, so they can run
while the phone is closed. Later Settings changes apply to new automations; open an
existing automation’s **Tools**, select **Use Settings defaults**, and save to update its
snapshot. Automation saves wait for the gateway’s committed revision. This requires the
runtime’s named automation tool-policy support; older gateways report the missing support
without dropping your choices. Messaging and other gateway restrictions still apply.

Tools stay reachable while the assistant works. Saved choices apply to the next message;
they do not modify a request already running. Starting a new conversation inherits the
saved iPhone defaults. A tool choice cannot grant a capability that the gateway or entity
does not offer; unavailable tools remain disabled.
The app refreshes availability when sending, so disabled or removed tools are not offered
to the agent. If tools cannot be loaded, the app reports the problem before starting the agent.

In **Settings**, enable **Show answer statistics** for a small line below AI answers:
elapsed wall time, input/output tokens and executed tool calls. It is off by default.
Unavailable measurements stay absent. Reading controls belong to the answer being spoken;
other answers retain their own Read action.

Assistant conversation tools use the same discovery and run-start APIs as the desktop
assistant; they do not require a gateway update for a capability probe. Entity conversation
approvals require entity session-tool support. On gateways without that support, ordinary
entity chat remains available and explicit entity tool choices stay unavailable. Detailed
answer statistics appear only when the gateway supplies them.

## Entities

Tap the current name at the top of chat to open **Who answers**. Search the entities your
account can access, select one, or choose **New entity**. Switching starts a new chat view
and keeps your draft; an entity retains its ongoing memory. Send or remove staged files
before switching. Entity loading has its own retry, independently of run history.

Creation uses the gateway's default identity and models, after a name check. Entities are
permanent and cannot be deleted; the form explains this before **Create entity**. Successful
creation opens the entity. If the gateway reports incomplete setup, the entity remains
created and its warnings are shown before continuing. Existing names are not replaced.
Advanced entity configuration remains in the gateway console.

## Connect

Enter your own gateway’s address. There is no preselected public server.

- **User name + account token:** the app verifies that the token belongs to that account.
- **Registered email + one-time code:** request the code and enter it. Email sign-in must be
  enabled on your gateway, with a mailbox connected for your account.

Your sign-in is kept in the app's own protected storage on this iPhone (shared with its notification
extension and handed to your Apple Watch), outside iCloud sync and ordinary preferences. HTTPS is required outside the local network. Local HTTP
addresses are accepted for development. A phone’s `localhost` is the phone itself; use
your Mac’s LAN address to reach a gateway running there.

**Take a look around** opens a separate demo with sample data. Its navigation label stays visible;
demo actions do not contact a gateway or overwrite an existing sign-in.

## Build and try it

See [BUILD.md](BUILD.md). One project builds the iPhone app and the Watch companion it embeds,
with the iPhone's own gateway-client snapshot; the watch keeps its client in `watch/apple`.

## Testing and distribution

Store releases package iPhone and the independent Watch companion in the existing
AbstractAssistant listing. Use **Actions → Apple app (iPhone + Watch)**; standalone Watch checks
do not upload. Local developer iPhone installs retain their separate identity.

[Testing and distribution](docs/distribution.md) explains the CI checks and protected upload.
Pushes and pull requests test the client without Apple credentials. A manual upload request
on main runs the full native suite and waits for a human reviewer before sending the Release
candidate to App Store Connect. Test the processed build in TestFlight, then select that same
build for manual App Review submission and public release. The workflow never publishes to
the public App Store automatically.

## What to expect from this preview

- In front, active runs are checked every three seconds and the lists every fifteen seconds.
  While the app is closed, approvals, questions, published alerts and automation results arrive
  as notifications through Apple push once your gateway's push relay is on (nothing to set up:
  the app registers itself at sign-in; the system's notification permission is the only switch).
- Answers use the gateway’s run output; the phone does not implement token-by-token SSE.
- The conversation picker shows the most recent 60 chat/discussion runs and opens up to
  30 turns per conversation. Older history remains on the gateway.
- Entity conversations use durable gateway visits when supported. Starting a new conversation
  ends the previous owned visit; the entity retains its ongoing memory. Earlier gateways
  use the home’s existing text-chat interface.
- Voice capture is limited to one minute. Audio goes to your gateway, then the temporary
  recording is removed. Transcription and speech use the gateway providers you select;
  no model runs on the iPhone. The orb’s level response is local; the conversation still
  proceeds through recording and transcription, review unless automatic sending is enabled,
  then a gateway run and optional speech.
- Chat model overrides, editing existing automation definitions, CarPlay and iPad
  layouts remain outside this preview. The desktop and gateway console expose those controls.
- Device microphone permissions, private-network reachability and real provider audio need
  verification on your own iPhone and gateway before daily use.

[Architecture](docs/architecture.md) · [Release history](CHANGELOG.md) ·
[AbstractAssistant](../../README.md) · [AbstractFramework](https://abstractframework.ai)

MIT License — see [the repository license](../../LICENSE).

Email activity uses two directional envelope counts beside the answer’s other actions:
incoming for messages read, outgoing for messages sent. Each appears only when that direction has
confirmed activity. Repeated reads of the same message
are counted once; inbox listings/searches are not counted as reads.

Tap either count for a compact searchable message list, then open any message to inspect
sender, To/Cc/Bcc, subject, body, recorded action time, original message date and attachment
names where available. Several long messages stay easy to browse without scrolling through
all their bodies. Replies appear in Sent emails. Partial recipient refusals and headers-only
reads are explicit. Send receipts confirm mail-server submission rather than delivery;
read activity does not change mailbox read/unread flags. Missing old history fields are
identified. HTML-only messages expose inert source without loading remote resources.

The answer action row also shows optional counts for files read, files written/modified,
web searches, and web pages fetched. Tap for searchable source lists and recorded excerpts,
results or change receipts. Repeated reads/edits of a file are grouped, with individual
operations in its detail; skim/full modes and request methods remain visible. Searches
count query operations, not every returned link; pages count successfully fetched URLs.
File sources are distinct per run to preserve separate workspaces. Only confirmed tool
results count: failed skims, preview/no-op edits and opaque shell side effects stay in
full activity. Zero actions are hidden. Complex strips scroll horizontally.

File receipt views offer Browse session files for current workspace document previews.
The session-wide browser is also always available from the toolbar’s folder button; its total
is no longer presented as if it were an answer's file activity.


Activity steps expand to show their recorded public output, model/provider, token usage,
finish reason and run/step identity. Start times and elapsed durations sit under each step;
history is ordered oldest first across parent and child runs, using this iPhone’s time zone.
Routing decisions are labeled Choose response type, so they are distinct from agent cycles
and media generation. Missing legacy fields are shown as unavailable, never estimated.
Private reasoning, system prompts and raw provider traces stay out of this view.


The chat toolbar has three islands: Conversations on the left, conversation Share/Files/Tools
in the middle, and Settings on the right. Open Conversations to start a new conversation;
it keeps the selected responder. The responder chooser sits directly below the toolbar.
New conversation is highlighted in mint above the conversation history. History groups into
Today, Yesterday and Earlier, with two-line titles, exchange/tool counts, last-activity ages and
Working/Needs you/Failed indicators. A “+” marks counts from the bounded recent history.
Use the archive icon to hide a finished conversation across devices; Archived offers Restore.
Archiving preserves messages and files, and working conversations cannot be archived.
Share conversation opens the native share sheet with formatted messages currently loaded,
in order with speaker labels, plus their original attachments and recorded generated files.
Images appear beside their messages in the rich transcript; other files have a caption at
the relevant answer and accompany the share as originals. Mail and Notes receive rich-text
alternatives; each receiving app controls the final formatting and inline placement.
Conversation recordings and read-aloud audio are excluded. Workspace files use their current
saved version. Sharing supports up to 100 original files and 200 MB combined, with inline
previews for the first 12 images. If a required file cannot be retrieved, retry or share
individual files from Conversation files. Temporary export copies are removed after sharing.
Copy and speech controls remain under individual answers.
Answer action counts appear only when positive.
An unnumbered Activity icon opens missing or unavailable history, with retry when needed.
Activity requests survive scrolling away and are shared across rows; changing accounts or
conversations invalidates them so late results cannot replace the current view.

Approval hands stay amber after resolution. Tool icons use lavender throughout the app;
status labels identify failures separately. The cycle graph groups tools and approvals under
their preceding cycle within the same agent run. Separate agent runs have separate lanes.
Tool inputs redact credential fields and omit private control fields; missing inputs are
marked unavailable. Long inputs and public outputs disclose display truncation. Credential
redaction is based on field names and does not inspect secrets embedded inside ordinary
command, URL or document text.


Each Tools category has an Off / Auto / Approve selector, available even while collapsed.
A category with mixed choices shows “Mixed” with no selected segment. Choosing a mode updates all available
tools in that category, including those hidden by search, while preserving other categories.
It creates an override of inherited defaults; gateway-disabled tools remain Off. The same
category controls apply in Settings, a session, and an automation.

**Version & updates** in Settings shows the installed version/build and opens the appropriate Apple update flow. Enable beta automatic updates in TestFlight. See [run troubleshooting and updates](docs/troubleshooting.md).

# AbstractAssistant for iPhone

A quiet place to think, ask, and pick things up again. A native SwiftUI client for your
AbstractGateway, with the conversation at the center and the controls you need close by.

**Developer preview · 0.6.6 · iOS 26+**

## Three small spaces

- **Assistant.** Type a message, or **tap the orb to listen**. After you speak, three seconds
  of silence sends your voice message automatically. Speaking again restarts the countdown;
  tap the orb before sending to cancel. Separate floating **+**, **keyboard** and orb controls
  keep the conversation open. The keyboard button expands the editor across the available
  width and hides the orb. Tap outside to dismiss the keyboard and restore the controls,
  preserving your draft. While listening, only a small Listening label appears above the orb.
  The orb’s ribbons react to microphone and read-aloud playback levels. While the assistant
  works, it becomes an animated square: tap it to stop the response. Progress appears once
  in a collapsible activity panel. It shows model cycles, tool calls, public results and
  failures. When a tool needs approval, **Approval needed → Review tools** appears directly
  in the conversation. Connection loss is reported separately from run failure. The orb
  returns when the gateway confirms the run has ended.
  Conversations are durable gateway sessions. Open the stack icon to continue one from
  your phone, desktop, Watch or browser. Tap the current name and chevron to choose **Assistant** or an entity, or create an entity.
  Share or copy an answer, or ask the gateway to read it aloud; pause, resume and stop playback.
  Voice sends separately from your typed draft. The **+** button serves text and voice.
- **Inbox.** Questions and tool approvals, followed by recent activity. Approvals show every
  action and its complete arguments. **Approve** allows the pending request; **Deny** refuses
  it. For the open conversation, **Approve all** also switches its currently enabled tools
  to Auto. Off, unavailable and newly added tools remain outside that grant. Change the
  choices in **Tools** to revoke it. Questions still require an answer. Decisions already
  made on another device cannot resume a different wait.
- **Automations.** See your routines, their latest answers and five earlier runs. Run an
  active or paused routine now, pause it, or resume it. Tap **New automation** (or **+** above an existing list) to create a routine: describe the task, choose a workflow and
  interval or daily time, and decide whether it builds on earlier runs and asks before tools.
  Daily times use your account’s time zone, which the creation screen displays. Editing
  an existing routine’s definition remains in the gateway console.

When creating an automation, **Build on earlier runs** reveals **History token budget**.
Leave it blank to inherit the gateway’s default (50,000 tokens in the runtime shipped with
this feature), or enter a positive whole number. The displayed default comes from your
gateway. The budget limits retained history rather than the length of an individual answer.

The app uses your account’s Assistant workflow preference (`abstractassistant.agent.v1`), or
the gateway’s Assistant default when you follow the default. If it is unavailable, choose an
available workflow in **Settings → Workflow**. Saving changes the Assistant preference
for your account across devices and applies to the next message, keeping your draft and history. The phone never switches
to another agent interface or runs models locally.

## Voice and files

**Settings → Voice & reading** offers automatic reading of new replies, the gateway’s
speaking voices and its transcription models. Voice choices stay on this iPhone, scoped
to your account and gateway. **Gateway default** sends no override; entities retain their
own speaking voice. Tap a voice to select and hear it automatically. Speed choices
**1×, 1.15×, 1.3× and 1.5×** also play a sample and apply to all read-aloud playback.
Restored history is never read automatically.

**Tap → speak → three seconds of silence → send.** Capture stays on the iPhone until the
silence countdown ends. Speaking again restarts that countdown. Tap the orb
to discard pending voice without uploading it. A tap without confirmed speech times out
after eight seconds, and the one-minute recording limit discards an unfinished message.
Leaving chat, changing conversations, opening the keyboard, backgrounding or an audio
interruption cancels pending capture. Once the countdown finishes, upload/transcription
has begun; canceling then stops the pending turn but cannot retract audio already uploaded.
The same tap interaction works with VoiceOver's double-tap activation.

The orb uses measured microphone/playback energy for its silhouette, rings and light.
Listening adapts to your microphone’s recent volume range; playback uses its own scale.
Reduce Motion retains signal-driven light while freezing geometry and rotation. Silence
detection uses local microphone power; room noise and very quiet speech can affect it.

Use **+** beside the composer to attach a file, choose a photo/video, take a photo or record
a short video. Uploaded file chips remain until you send or remove them.
**More options (…) → Conversation files** opens your files, including files the assistant generates.
Tap a file to download it privately and preview, play or share it with the native viewer.
Attachments retain their gateway artifact and owning-run references. Credentials never
travel in a share link or to an AI-provided URL.

Local preview copies are removed when you dismiss the viewer or open another file.
Imported copies are removed after upload; recordings are removed after transcription or
cancellation. Disposable files left by an interrupted app are cleared on its next launch.
Your original files and gateway attachments are preserved.

Files are limited to **25 MB each** on the phone; the gateway may impose a smaller limit.
Camera videos are capped at 30 seconds. Entity chat’s current gateway interface accepts
text only, so file messages are available in Assistant conversations. The files list shows
the latest 100 session artifacts; older files remain on the gateway.

## Conversation tools and answer statistics

Open **Settings → Conversation tools** or **More options (…) → Tools**. With gateway defaults,
available gateway tools are enabled and approval follows the gateway's policy. Tools are grouped into expandable categories reported by
your gateway. Search by category, tool name or description. Turn off **Use gateway defaults**
to set each available tool:

- **Off** blocks it for this conversation.
- **Auto** allows execution without asking.
- **Approve** waits for your decision before execution. Review and allow or deny in chat or Inbox.

Choices are saved on this iPhone for the signed-in gateway account, responder and conversation. They apply
to subsequent messages; starting a new conversation restores inheritance. A tool choice
cannot grant a capability that the gateway or entity does not offer. Tools disabled by the
gateway show its reason and remain Off. Unreported categories appear under **Other**.
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

Sign-in data lives in the iPhone Keychain (`WhenUnlockedThisDeviceOnly`), outside iCloud
sync and ordinary preferences. HTTPS is required outside the local network. Local HTTP
addresses are accepted for development. A phone’s `localhost` is the phone itself; use
your Mac’s LAN address to reach a gateway running there.

**Take a look around** opens a separate demo with sample data. Its navigation label stays visible;
demo actions do not contact a gateway or overwrite an existing Keychain sign-in.

## Build and try it

See [BUILD.md](BUILD.md). The project has its own bundle ID, Xcode project, build directory
and gateway-client snapshot. It neither embeds nor modifies the Watch application.

## What to expect from this preview

- Foreground updates only: active runs are checked every three seconds; the lists every
  fifteen seconds. No push notifications or background polling. The gateway continues work
  after you leave the app. Open it again to catch up.
- Answers use the gateway’s run output; the phone does not implement token-by-token SSE.
- The conversation picker shows the most recent 60 chat/discussion runs and opens up to
  30 turns per conversation. Older history remains on the gateway.
- Entity conversations use durable gateway visits when supported. Starting a new conversation
  ends the previous owned visit; the entity retains its ongoing memory. Earlier gateways
  use the home’s existing text-chat interface.
- Voice capture is limited to one minute. Audio goes to your gateway, then the temporary
  recording is removed. Transcription and speech use the gateway providers you select;
  no model runs on the iPhone. The orb’s level response is local; the conversation still
  proceeds through recording, transcription, a gateway run, then speech.
- Chat model overrides, editing existing automation definitions, push, CarPlay and iPad
  layouts remain outside this preview. The desktop and gateway console expose those controls.
- Device microphone permissions, private-network reachability and real provider audio need
  verification on your own iPhone and gateway before daily use.

[Architecture](docs/architecture.md) · [Validation](docs/validation.md) ·
[AbstractAssistant](../../README.md) · [AbstractFramework](https://abstractframework.ai)

MIT License — see [the repository license](../../LICENSE).

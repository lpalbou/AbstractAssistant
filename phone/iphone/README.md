# AbstractAssistant for iPhone

A quiet place to think, ask, and pick things up again. A native SwiftUI client for your
AbstractGateway, with the conversation at the center and the controls you need close by.

**Developer preview · 0.4.0 · iOS 26+**

## Three small spaces

- **Assistant.** Type a message, or **tap the orb to listen**. After you speak, three seconds
  of silence sends your voice message automatically. Speaking again restarts the countdown;
  tap the orb before sending to cancel. The orb stays visible while typing and reacts to
  microphone and read-aloud playback levels. Tap outside the text field to dismiss the
  keyboard and minimize your draft; tap the field to expand it again. The compact dock
  groups attachments, text and voice together without a separate Done button.
  Conversations are durable gateway sessions. Open the stack icon to continue one from
  your phone, desktop, Watch or browser. Choose an entity with the person icon to talk to it.
  Share or copy an answer, or ask the gateway to read it aloud; pause, resume and stop playback.
  Voice sends separately from your typed draft. The **+** button serves text and voice.
- **Inbox.** Questions and tool approvals, followed by recent activity. Approvals show every
  action and its complete arguments. Allow once or deny; decisions already made on another
  device cannot resume a later action. There is no blanket tool trust switch.
- **Automations.** See your routines, their latest answers and five earlier runs. Run an
  active or paused routine now, pause it, or resume it. Tap **+** to create a routine: describe the task, choose a workflow and
  interval or daily time, and decide whether it builds on earlier runs and asks before tools.
  Daily times use your account’s time zone, which the creation screen displays. Editing
  an existing routine’s definition remains in the gateway console.

The app uses your account’s Assistant workflow preference (`abstractassistant.agent.v1`), or
the gateway’s Assistant default when you follow the default. If it is unavailable, choose an
available workflow in **Settings → Workflow**. Saving changes the Assistant preference
for your account across devices and applies to the next message, keeping your draft and history. The phone never switches
to another agent interface or runs models locally.

## Voice and files

**Settings → Voice & reading** offers automatic reading of new replies, the gateway’s
speaking voices and its transcription models. Voice choices stay on this iPhone, scoped
to your account and gateway. **Gateway default** sends no override; entities retain their
own speaking voice. Restored history is never read automatically.

**Tap → speak → three seconds of silence → send.** Capture stays on the iPhone until the
silence countdown ends. Speaking again restarts that countdown. Tap the orb or **Cancel**
to discard pending voice without uploading it. A tap without confirmed speech times out
after eight seconds, and the one-minute recording limit discards an unfinished message.
Leaving chat, changing conversations, opening the keyboard, backgrounding or an audio
interruption cancels pending capture. Once the countdown finishes, upload/transcription
has begun; canceling then stops the pending turn but cannot retract audio already uploaded.
The same tap interaction works with VoiceOver's double-tap activation.

The orb uses measured microphone/playback energy for its silhouette, rings and light.
Reduce Motion retains signal-driven light while freezing geometry and rotation. Silence
detection uses local microphone power; room noise and very quiet speech can affect it.

Use **+** beside the composer to attach a file, choose a photo/video, take a photo or record
a short video. Uploaded file chips remain until you send or remove them. The **folder**
in the toolbar opens **Conversation files**, including files the assistant generates.
Tap a file to download it privately and preview, play or share it with the native viewer.
Attachments retain their gateway artifact and owning-run references. Credentials never
travel in a share link or to an AI-provided URL.

Files are limited to **25 MB each** on the phone; the gateway may impose a smaller limit.
Camera videos are capped at 30 seconds. Entity chat’s current gateway interface accepts
text only, so file messages are available in Assistant conversations. The files list shows
the latest 100 session artifacts; older files remain on the gateway.

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
- Entity conversations continue that entity’s server-side home conversation. Selecting an
  entity is not a promise to reset its memory or create a separate entity thread.
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

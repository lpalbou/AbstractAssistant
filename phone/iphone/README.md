# AbstractAssistant for iPhone

A quiet place to think, ask, and pick things up again. A native SwiftUI client for your
AbstractGateway, with the conversation at the center and the controls you need close by.

**Developer preview · 0.1.0 · iOS 26+**

## Three small spaces

- **Assistant.** Type a message, or tap the microphone to record one. Tap again to finish;
  your gateway transcribes it into the composer so you can review it before sending.
  Conversations are durable gateway sessions. Open the stack icon to continue one from
  your phone, desktop, Watch or browser. Choose an entity with the person icon to talk to it.
  Share or copy an answer, or ask the gateway to read it aloud; pause, resume and stop playback.
- **Inbox.** Questions and tool approvals, followed by recent activity. Approvals show every
  action and its complete arguments. Allow once or deny; decisions already made on another
  device cannot resume a later action. There is no blanket tool trust switch.
- **Automations.** See your routines, their latest answers and five earlier runs. Run an
  active or paused routine now, pause it, or resume it. Use the gateway console to create
  or edit routines.

The app uses your account’s Assistant workflow preference (`abstractassistant.agent.v1`), or
the gateway’s Assistant default when you follow the default. If it is unavailable, choose an
available workflow in the gateway console’s Accounts → Preferences. The phone never switches
to another agent interface or runs models locally.

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
  recording is removed. Reading uses the gateway’s voice, never a separate phone provider.
- Attachments, automation authoring, model overrides, push, CarPlay and iPad layouts are
  outside this first version. The desktop and gateway console expose the broader controls.
- Device microphone permissions, private-network reachability and real provider audio need
  verification on your own iPhone and gateway before daily use.

[Architecture](docs/architecture.md) · [Validation](docs/validation.md) ·
[AbstractAssistant](../../README.md) · [AbstractFramework](https://abstractframework.ai)

MIT License — see [the repository license](../../LICENSE).

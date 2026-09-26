# Changelog

All notable changes to AbstractAssistant are documented in this file. Entries describe what
changed for users and contributors; design history lives in `docs/adr/` and `docs/backlog/`.

## [0.6.1] - 2026-09-27

### Changed
- The default screen edge gap is 12 px (was 28 px). A gap already saved in your preferences (for
  example 28 px from 0.6.0) is kept; change it in Settings → Appearance → Screen edge gap.

### Fixed
- Settings opens fully on screen, inside the menu bar, Dock and screen edge gap: it no longer opens
  with its right side (and the Connect button) past the screen edge, including after a text size
  change. On a screen too small for it, it is shrunk to fit.

## [0.6.0] - 2026-09-26

### Added
- **Open from the gateway console, already signed in.** Clicking **Open** on the assistant's card
  in the AbstractGateway console launches the app with a one-time sign-in (`--gateway-handover-file`);
  the app exchanges it for a gateway session and remembers it. If the sign-in has expired or was
  already used, a banner tells you to open the assistant from the console again or to connect in
  Settings → Connection. An existing working sign-in is kept only when it is for the same gateway
  and the same user who clicked **Open**; a sign-in to another gateway or as another user is
  signed out and replaced, and the banner says who is signed in now and who was signed out. A
  sign-in file that does not name the user is refused and left untouched.
- **Choose the workflow.** Settings → Models → Workflow lists **Gateway default** first (the
  gateway's default for `abstractassistant.agent.v1`, or the built-in orchestrator when the gateway
  sets none), then every assistant workflow in the catalog. The choice applies from the next turn;
  choosing the gateway default follows later changes made on the gateway.
- **Live replies.** When the gateway streams, the answer appears in a bubble that grows while the
  model writes it; the model's reasoning goes in a collapsed **Thinking** area, a sub-agent's
  bubble is labelled, and the finished answer replaces the live text. A step that fails or is
  stopped removes its bubble and says why; a step that cannot stream says why in the status line.
  Settings → Models → **Stream replies** (Gateway default, On, Off) chooses per device; `assistant
  run --stream on|off` does the same for one terminal turn, writing the live text to stderr and the
  final answer once to stdout. On is sent only to a gateway that offers live replies; elsewhere it
  is shown as not supported and a chat notes it once. Off is always sent.
- **About AbstractAssistant.** Settings → About shows the application and version, AbstractFramework,
  author, licence, and links to the website, source, documentation, issue tracker, feedback form
  and contact address, plus the workflow the last turn ran. The menu-bar icon has an
  **About AbstractAssistant…** item.

### Changed
- The window is wider by default (650 px) and keeps a 28 px gap from the screen edges. Settings
  accepts a width of 420–2000 px and a gap of 0–200 px, limited only by the screen; a gap of 0
  is kept. If you still had the previous defaults (500 px,
  18 px) you move to the new ones once; values you changed are kept.
- The app no longer makes its built-in orchestrator the gateway catalog's default workflow; which
  workflow is the default is the gateway operator's setting.
- `--gateway-url` without `--gateway-token` is honoured and uses the sign-in saved for that gateway.
  `assistant run` without a sign-in tells you how to sign in.
- About and `assistant --version` always show the real version, including in the macOS app.
- Requires AbstractCore 2.16.0 or newer.

### Fixed
- The built-in orchestrator is no longer labelled "@0.0.0" in Settings → Models → Workflow and on
  the About page: its real published version is shown, or "(built-in)" when it has none yet. The
  app now publishes its first version explicitly as 0.0.1.
- HTML written by the model (tags such as `<img onerror=…>`, `<a href="javascript:…">`, an unclosed
  `<b>`) is shown as text in replies, live or finished, instead of being handed to the transcript
  as markup. Formatting from Markdown and Mermaid diagrams are unaffected.
- Switching sessions no longer shows the previous conversation underneath the new one, and a
  background attachment refresh can no longer copy one session's messages into another.

## [0.5.0] - 2026-09-23

AbstractAssistant 0.5.0 is the gateway-native release: the desktop app is a thin client of
AbstractGateway, with a redesigned palette, a hands-free voice conversation mode, a settings
window that covers what the gateway lets you configure, and tool approvals that never block the
app.

### Added
- **MTP depth for the chat model.** The chat route in Settings offers Gateway default, Off, or
  any multi-token-prediction depth the gateway's execution capability card advertises for the
  selected provider and model. The choice is sent as `_runtime.speculation`, survives restart,
  and shows when the model's MTP head is not ready or needs a reload.
- **Choose which speaker the assistant talks to.** Settings → Voice lists the devices this Mac
  can play to ("System default" or any device by name), with a **Test** button that plays a
  short tone. The choice is remembered per device, so it survives reboots and reconnections; an
  unplugged device stays selected and is shown as "not connected". AirPlay speakers are chosen in
  the macOS Sound menu with this set to "System default".
- **Clickable files and links in answers.** File paths in a reply become links, and each file
  also appears as a chip under the answer (thumbnail or icon, name, kind, size). Right-click
  offers Open, Show in Finder and Copy Path; ⌘-click shows the file in Finder. Commands and code
  listings that merely mention a path are left as written.
- **A click opens a file, never runs one.** Links in replies are treated as untrusted: media and
  documents open normally, text and source files open in your text editor, and apps, scripts,
  installers and unknown types are only revealed in Finder. Links to files on another computer
  are refused. Action buttons under an answer follow the same rules.
- **Theme picker** under Settings → Appearance, using the colour themes shared with the rest of
  the framework (Tokyo Night, Nord, Dracula, Gruvbox, Catppuccin, Rose Pine, Solarized,
  Everforest and more, dark and light). It applies to every window immediately and is remembered.
- **Measured prompt-cache reuse** in the per-turn statistics tooltip: tokens reused from cache
  versus newly processed, summed across every model call of the turn, when the execution host
  reports it.
- **Live voice histogram in the tray icon** while a reply is spoken (auto-speak, voice
  conversations and the per-message speaker button); it returns to normal when speech ends.
- **Voice conversation mode** (⌘⇧V, the waveform button, or the tray menu): the assistant
  listens, sends what you say, speaks the reply and listens again. A status strip above the
  composer shows listening / heard / thinking / speaking / paused with a live microphone meter,
  pause and end controls, and every failure names its cause. Push-to-dictate on the microphone
  button is unchanged. See [docs/voice.md](docs/voice.md).
- **Chat switcher.** The header's chat control opens a searchable list of chats grouped by
  recency. Each row carries the facts needed to pick one: topic, latest question, last activity,
  turns, tool calls, tokens, running time and workspace folder, with failed tool calls and
  unanswered questions flagged. Chats can be renamed and deleted (transcript included) from the
  row, with confirmation. The metrics are computed from local files and cached by file identity,
  so the list costs no gateway call.
- **Live run activity in the transcript.** While a run works, a card at the bottom of the chat
  shows the current step, elapsed time, and the most recent steps (reasoning cycles, tool calls
  with their arguments and durations, approvals, pauses, reconnects). It can pause, resume or stop
  the run and open the full run log. Runs that were reattached never show an invented total time.
- **Settings window with seven sections**: Connection, Models & reasoning, Voice, Workspace,
  Tools & permissions, Window & shortcuts, About. Every control states where its value comes
  from (gateway default vs. this app) and what is stored on this Mac. See
  [docs/settings.md](docs/settings.md).
- **Reasoning effort** for the chat model (Gateway default, none, minimal, low, medium, high,
  extra high), taken from the gateway's `thinking_control` contract and sent with every run.
  The page shows which model the setting applies to and the reasoning levels that model reports.
- **Workspace settings**: a workspace root, an access mode, and allowed folders that ride each run;
  the gateway's own workspace policy is shown read-only next to them. Without a chosen root,
  the folder the gateway gives the first run of a chat is reused for the rest of that chat, so
  multi-turn file work stays in one place.
- **Tool approvals as a modeless sheet.** Approving tools no longer freezes the palette. Each call
  shows the gateway's risk tier (reads only / makes changes / reaches outside / destructive) and
  capability flags, the promoted command, path or query, a preview for long content, and a
  masked full-call view. `Allow once` is the primary action (Return), `Deny` is secondary (⌘D),
  Esc means "decide later" and the question comes back when you reopen the palette. A batch that
  arrives while the sheet is open is queued. "Always allow this tool on this Mac" writes the
  per-tool preference.
- **Questions from the assistant** open in a modeless dialog with a rendered prompt and a
  multi-line answer (Return sends, Shift+Return adds a line); "Keep waiting" leaves the run
  parked, "Continue without answering" sends an empty reply.
- **Header status**: the palette title shows what the app is doing (Running, Reconnecting,
  Listening, Speaking, Not sent, Failed) and returns to the app name when idle.
- **Keyboard shortcuts**: ⌘N new chat, ⌘, settings, ⌘. stop the run, ⌘⇧V voice conversation,
  Esc stops speech first and hides the palette second.
- **Terminal turns honor the same local overrides as the tray**: chat model pin, media pins,
  reasoning effort and workspace grant apply to `assistant run` too.
- Per-answer statistics under each reply (input/output tokens, tools, files, duration, model),
  with a clickable tools segment ("Tools used") and files segment ("Files affected") hydrated
  from the run ledger.
- Local, persistent model overrides for every route the assistant drives (chat, voice output,
  voice input, image generation/edit/upscale, video, image-to-video, music, sound). Overrides
  are stored in `preferences.json` and sent per request; the gateway's shared defaults are never
  written.
- Multi-attachment layout: images render as a square-tile gallery, other files as wrapping chips;
  the composer attachment tray wraps up to three rows and then scrolls.
- A designed app icon and a coherent Lucide icon set rendered from inline SVG.

### Changed
- Reasoning effort is a row of the chat model's own form in Settings, beside its provider and
  model; it no longer appears to apply to other routes.
- Settings fits at its default size: route actions sit in the page footer, the reasoning ladder
  is a menu, and the window minimum is measured against its widest page.
- Replies use tighter vertical spacing (about 10% shorter with the same type sizes), and the
  default window is 15% shorter. A height you chose earlier is adjusted once.
- Attached files show as small thumbnails (about 56px tall) that open full size in a preview
  window; files without a preview appear as an icon-and-name chip. Generated images keep the
  full gallery.
- **Tool permission defaults come from the gateway.** The Tools page and the run policy use each
  tool's gateway `approval_default` and risk tier; the local allow-lists are only a fallback for
  gateways that do not report them. Tools the gateway has disabled are shown as such and are never
  offered to a run. Migration: tools you had never configured now follow the gateway's default
  ("ask" for anything that sends messages, writes remotely or is destructive). Your saved
  per-tool choices are unchanged.
- One visual system: a shared token-based stylesheet (`ui/styles.py`) drives every secondary
  window; gradients and drop shadows are gone; the user bubble uses the app accent instead of
  indigo; the palette honors the configured size up to the screen and gives the transcript the
  remaining height.
- The palette resizes in place and only snaps to the menu-bar corner when summoned; activating
  a secondary window (settings, approval sheet, run log, tools used) no longer hides the palette.
- Worker errors are shown as a banner and in the run status instead of a modal dialog, and only
  raise a notification when the palette is hidden. A failed attempt to answer a wait is reported
  as a warning while the run keeps going.
- A run the gateway refuses to start (for example a workspace path outside its policy) is shown
  as "Not sent" with the gateway's reason; the message returns to the composer and no phantom
  turn is left in the chat.
- Losing the gateway mid-run shows "Reconnecting…" while the run stays busy, then "Reconnected".
- The voice-style instruction used during a conversation is appended to the workflow's own
  system prompt instead of replacing it.
- Speech-to-text and text-to-speech pins are sent only when you chose an engine; the gateway's
  advertised default is never echoed back as a half-specified pin.
- Long spoken replies start playing within about a second: replies stream from the gateway's
  streaming TTS lane, and a rejected stream retries once without pins before falling back to
  whole-message synthesis (which is announced).
- Speech failures are always visible: the banner names the root cause (rejected model pin,
  timeout, unplayable audio, nothing to read aloud), the affected message card is released, and
  the banner says which output device is playing and warns when the system output is muted or
  very low.
- Conversation memory is replayed by the gateway from the durable session (the client sends only
  the prompt and artifact references).
- The assistant is gateway-native only: the local execution engine, local provider/model
  configuration, the legacy bubble UI and the separate `abstractassistantv2` package were removed.
  `assistant` launches the palette; `import abstractassistant` stays free of Qt and voice
  dependencies.
- Voice ships by default (`abstractvoice[audio-io]`); the "Voice latency" preference maps to the
  gateway's TTS quality preset when the gateway advertises it.
- Copy and tooltips were rewritten for clarity ("New chat", "Tools & permissions", "Switch chat",
  "Reply ready").

### Fixed
- Spoken replies follow the current macOS output device (or the device you picked) instead of
  the one active when the app started. When the chosen device is unavailable, replies fall back
  to the system default and say so. A reply whose audio output stops draining is stopped and
  reported, and the next reply reopens the device.
- Two builds of the app on one Mac no longer republish each other's gateway workflow on every
  launch; the workflow carries a revision and a build never replaces a newer one.
- The per-turn routing step runs without the agent's tools and at its own temperature, which
  removes a multi-second delay before every answer.
- Every tool call of a turn is listed with its own result, even when the model numbers its calls
  per reply.
- "All auto" / "All ask" apply only to tools visible under the search filter; saving tool
  permissions keeps modes for tools the gateway is not currently listing.
- On desktops without a system tray, the app shows its window and explains why instead of running
  invisibly. On Linux the tray menu no longer opens twice. `pyobjc-framework-Cocoa` is a declared
  dependency on macOS.
- The audio meter produces readings again.
- Reopening a session restores its attachments from the runtime, and attachment previews fall
  back to the gateway's stored copy when the local file is gone.
- The header names the current session; the session switcher stays open, renders correctly and
  opens quickly.
- Saving the Appearance page no longer grows the window.
- Typing a message while a voice-conversation reply is speaking or paused starts a new turn.
- The test suite scrubs gateway credentials from the environment and refuses connections to the
  gateway port and to non-local hosts.
- Blanket trust is scoped rather than blocked: "Always allow … on this Mac" is offered for the
  observe and act tiers, and "Allow all enabled tools in this chat" reaches exactly as far as the
  batch it was granted on (the menu item names the scope, so a grant made on a read-only batch
  still asks before an outreach or destructive call). "All auto" on the Tools page leaves those
  tiers on Ask.
- The activity card's "N earlier steps…" link folds the list back to the recent steps.
- In the approval sheet, Return activates the Deny or Decide later button when it has focus
  instead of allowing the batch; the same undecided wait raised twice is shown once.
- The question dialog is modeless: the palette stays usable while a question is open, and a
  deferred question comes back once when the palette is shown again.
- Voice conversation: the microphone is muted while the assistant thinks (the strip said so; now
  it is true), a turn heard while a run is closing waits for the next listening window instead
  of steering the closing run, stopping speech with Esc or the strip resumes listening, and
  ending the mode always closes the microphone.
- The Settings window fetches the gateway's workspace policy, tool inventory, routes and model
  card off the GUI thread before it opens.
- The run log no longer shows each step twice while a run is live.
- A run the gateway refused to start keeps the "Not sent" status when the follower closes, and
  text typed meanwhile is kept below the restored message.
- ⌘. does nothing when no run is active; ⌘N is refused while a run is active.
- Tools page: Save stores only the tools that differ from the gateway default and is disabled
  when the gateway reported none.
- Workspace page: the folder pickers appear only when the gateway runs on this Mac; entries a
  gateway that forbids client grants would refuse are named at Save time.
- Toggling auto-speak in the header no longer erases the saved model and voice overrides.
- Saying "stop" during dictation now closes the microphone instead of only turning the indicator
  off.
- Every route override requires both a provider and a model; half-specified overrides are dropped
  instead of sending a broken pin.
- A second tool-approval request on the same node is no longer swallowed; waits are answered by
  identity (`run_id` + `wait_key`).
- The speaker button no longer freezes the app: synthesis and download run off the GUI thread and
  completion is signalled exactly once.
- Answer statistics are aggregated across the whole run tree and survive history reseeding.
- Banners raised by one source (a workflow problem, a speech notice) are no longer cleared by an
  unrelated refresh.
- Warning banners render as warnings (the `warning` tone alias is honored).
- Test environment: sibling `abstractcore` is preferred alongside sibling `abstractruntime` and
  `abstractvoice` when the monorepo is checked out.

### Removed
- The stand-alone Tools window; it is the Tools & permissions page of Settings.
- The upscale-resolution control and free-form options JSON in the route editor, which were saved
  but never delivered to a run. The chat route keeps its optional provider base URL; the voice
  route keeps its voice picker.
- Dead client-side surfaces (client image-intent pipeline, prompt-cache negotiation, transcript
  summary, legacy selection store) and the unused `markdown`, `pymdown-extensions`, `plyer`,
  `pystray` and `pyperclip` dependencies.

### Packaging
- The macOS bundle declares `NSMicrophoneUsageDescription`, excludes `pygame`, and uses a narrow
  PyInstaller hidden-import surface. `build-macos-app` warns at build time when the local audio
  stack is missing.

### Preferences file
`~/.abstractassistant/preferences.json` gained `reasoning_effort`, `workspace_root`,
`workspace_access_mode`, `workspace_allowed_paths`, `voice_auto_send`, `voice_spoken_replies`,
`voice_mode`, `speculation`, `audio_output_device`, `audio_output_device_name`, `ui_theme`
and the reading-comfort keys (`text_size`, `line_spacing`, `paragraph_spacing`, `bullet_spacing`).
Missing keys keep their defaults (gateway default, no workspace grant, auto-send on,
spoken-style replies on, microphone paused while speaking). Each chat's `session.json` may carry
the `workspace_root` the gateway granted it.

## [0.4.11] - 2026-06-14

### Fixed
- Gateway-backed conversation snapshots now assign stable `message_id` values when persisting or replacing messages, so later UI reconciliation can key history entries deterministically instead of falling back to role/timestamp/content heuristics.
- Assistant v2 history replay now prefers those explicit message ids for deduplication, and the history viewport sync moved to the deferred scroll-apply path so early layout/show events no longer force an extra synchronous viewport pass.

## [0.4.10] - 2026-06-14

### Changed
- The tray app and `assistant run` now use one published gateway workflow, `abstractassistant-orchestrator`, as the runtime path for chat, tools, and media requests.
- Gateway capability-default editing now carries the newer vision route fields end to end, including `count` / `n`, ordered `seeds`, stacked `lora_adapters`, `guidance_2`, and `flow_shift`.
- Public documentation now explains the published assistant workflow and gateway-owned defaults directly, with release history kept in the changelog and only limited compatibility guidance in the FAQ.
- Raised dependency floors to Agent `>=0.3.12`, Voice `>=0.10.18`, and Core `>=2.13.38` so the assistant inherits the published Gateway/Core vision and voice capability surface.

## [0.4.9] - 2026-06-03

### Changed
- Raised dependency floors to Agent `>=0.3.11` and Core `>=2.13.32` so Gateway-mode media, provider-profile, and capability-default configuration inherit the latest framework release boundary.

## [0.4.8] - 2026-05-31

### Changed
- Raised dependency floors to Agent `>=0.3.10` and Core `>=2.13.31` so Gateway-mode media, provider-profile, and vision installs inherit the latest framework release boundary.

## [0.4.7] - 2026-05-29

### Changed
- Raised dependency floors to Agent `>=0.3.9`, Core `>=2.13.30`, and Voice `>=0.10.17` so Gateway-mode media and voice installs inherit the latest framework release boundary.

## [0.4.6] - 2026-05-26

### Changed
- Raised dependency floors to Agent `>=0.3.8`, Core `>=2.13.28`, and Voice `>=0.10.16` so Gateway-mode media settings inherit the latest provider/model/voice catalog contracts.

## [0.4.5] - 2026-05-13

### Fixed
- Media settings now force-refresh Gateway catalogs when opened and include cloned voices alongside provider profiles in the Voice selector.
- Gateway voice discovery now reads the concrete voice catalog route first, deduping profiles, hosted voices, and cloned voices before falling back to capability contracts.
- The media selector now shows a visible catalog error note instead of silently presenting only defaults when Gateway media discovery fails.

### Changed
- Dependency floors now require Core `>=2.13.14` and Voice `>=0.9.4`.


## [0.4.4] - 2026-05-12

### Added
- Media settings now include separate Voice, TTS, STT, and Image selectors populated from Gateway catalog routes.
- Gateway client support for `/api/gateway/audio/transcriptions/models`.

### Fixed
- Generated image messages now render real thumbnails in chat history instead of placeholder icons when the gateway returns image artifacts.
- Media selector parsing now accepts Gateway/Core catalog shapes (`models`, `data`, `tts_models`, `stt_models`, active model fields, voice profiles, and cached/provider image models) and preserves persisted selections.

### Changed
- Dependency floors now require Core `>=2.13.13` and Voice `>=0.9.3`.

## [0.4.0]

### Added
- **Agent host + durability**: new core modules for agent runs and durable state: `agent_host`, `session_index`, `session_store`, `tool_policy`, `transcript_summary`.
- **CLI**: `assistant run` for one-turn agentic runs in terminal; `assistant tray` as the explicit tray-mode entry.
- **Tests**: added basic + integration coverage for the new host/session/tool-policy/summarization components.
- **Reports**: added research notes under `reports/` (dated 2026-02-04).

### Changed
- **Docs & README**: rewritten/updated to reflect the agentic host model, tool approval boundary, and install profiles.
- **Dependencies**: updated `pyproject.toml` (profiles/requirements refined).
- **Qt bubble UI**: significant updates to `qt_bubble.py` (input/action controls, tool allowlist UI, voice-mode behaviors, theming).

### Fixed
- **Qt chat bubble input actions**: Fixed first-open layout race that caused the right-side action buttons to overlap. The action column now deterministically sizes to the input row, keeps strict 1:1 square buttons, and preserves 1px vertical spacing.
- **Tray app shutdown**: Ctrl+C (SIGINT) and SIGTERM now trigger a clean Qt shutdown path (stop timers, hide tray icon, destroy bubble) instead of an abrupt interpreter exit.
- **Voice toggle icon**: The mic indicator now defaults to a clearly struck "mic off" icon when Full Voice Mode is disabled (non-listening default).
- **Voice mode UI switch**: Exiting Full Voice Mode now reliably restores the normal interface; while listening, attachment + tools controls remain available and Send is hidden.
- **Voice mode shutdown**: Stopping Full Voice Mode now force-stops listening/speaking, turns off TTS, restores Ready (green) status, and prevents late STT/TTS callbacks from flipping the UI back to LISTENING.

### Removed
- `ROADMAP.md` (removed from the repository).

## [0.3.5] - 2026-01-07

### Fixed
- **Packaging / installability**: narrowed the default `abstractcore[...]` dependency set to avoid GPU-only stacks (notably vLLM) being installed on macOS, which could break `assistant --help` due to transitive `datasets/pyarrow` incompatibilities.


## [0.3.4] - 2025-10-27

### Improved
- **Chat History Management**: Enhanced message deletion and history dialog handling
  - Streamlined message deletion process with improved error handling
  - Removed excessive debug output for cleaner user experience
  - Enhanced widget management for better performance in history dialog
  - Improved UI consistency during message operations
  - Better error handling and widget lifecycle management

### Fixed
- **Code Cleanup**: Removed debug print statements that cluttered console output
  - Cleaner codebase with reduced unnecessary logging
  - Maintained UI integrity during message deletions
  - Enhanced performance through optimized widget management

## [0.3.3] - 2025-10-24

### Changed
- **Keyboard Behavior**: Reversed Enter/Shift+Enter behavior for more intuitive message sending
  - `Enter`: Send message (previously required Shift+Enter)
  - `Shift+Enter`: Add new line without sending (previously just Enter)
  - Updated both Qt and Tkinter chat interfaces for consistency
  - Improved user experience with standard chat application behavior

### Fixed
- **macOS App Bundle**: Consolidated and improved app bundle creation system
  - Merged `setup_macos_app.py` functionality into `create_app_bundle.py` for cleaner architecture
  - Enhanced Python environment discovery in launch script for better reliability
  - Improved custom icon preservation logic to prevent overwriting user icons
  - Fixed app bundle creation for various Python installation methods (pyenv, system, conda)
  - Removed redundant files and streamlined packaging structure

### Improved
- **Documentation**: Updated all documentation to reflect current features and behavior
  - Fixed keyboard shortcuts documentation across all guides
  - Updated installation instructions with correct app bundle creation commands
  - Verified consistency of Python version requirements (3.9+) across all docs
  - Corrected outdated references to deprecated modules

### Removed
- **Code Cleanup**: Removed deprecated `setup_macos_app.py` after consolidation
  - All functionality moved to `abstractassistant/create_app_bundle.py`
  - Updated PyPI packaging to exclude development artifacts
  - Cleaner project structure with single app bundle creation entry point

## [0.3.0] - 2025-10-22

### Fixed
- **CRITICAL: Session Persistence**: Completely eliminated unwanted session clearing that was destroying chat history
  - Sessions now persist when switching providers or models
  - TTS mode switching preserves chat history
  - Error handling preserves sessions instead of creating new ones
  - System tray actions require user confirmation and cannot bypass session control
  - Only explicit "Clear" button action in UI destroys sessions
  - Separated LLM initialization from session management
  - Added `update_session_mode()` method for history-preserving mode switches
  - Fixed automatic session loading that bypassed user control
  - Bulletproof session control: NO internal process can clear sessions
- **UI Layout**: Fixed window resizing when adding/removing file attachments
  - Window now dynamically resizes to accommodate file attachment widget
  - Base size: 630x196, expands to 630x224 when files are attached (compact)
  - Voice mode properly adjusts: 630x120 base, 630x148 with attachments
  - Maintains proper positioning relative to system tray after resize
- **Session Clearing**: Clear session now also clears attached files
  - When user clicks "Clear" button, both messages and attached files are cleared
  - Updated confirmation dialog to mention attached files will be removed
  - Ensures complete session reset including file attachments
- **File Chip Styling**: Made file attachment chips more compact and space-efficient
  - Reduced font size from 10px to 8px for better space utilization
  - Decreased border radius from 10px to 6px for tighter appearance
  - Minimized padding and margins throughout (50% reduction)
  - Smaller remove buttons (16x16 → 12x12) for cleaner look
  - Window expansion reduced from +40px to +28px (30% space savings)
- **UI Cleanup**: Removed unwanted voice control panel extension
  - Eliminated the play/pause control panel that sometimes appeared at bottom
  - Cleaner interface without unnecessary UI extensions
  - Voice controls still available through existing TTS toggle button
- **File Attachment Persistence & Visual Indicators**: Enhanced file handling for better user experience
  - Files now remain attached after sending messages, allowing for easy reuse in follow-up messages
  - Added visual file attachment indicators (📎) in chat history dialog showing file count per message
  - Enhanced message history structure to track file attachments per message
  - Clear session now properly clears both messages and file attachment tracking
  - Improved file workflow: attach once, use multiple times until manually removed

## [0.2.8] - 2025-10-21

### Added
- **macOS App Bundle**: Native macOS application bundle (`.app`) with Dock integration and system tray support
- **Automated App Creation**: `create-app-bundle` command to generate macOS app bundle post-installation
- **Streamlined Installation**: `install.py` script for one-command macOS setup with app bundle creation
- **Neural Network Icon**: Beautiful AI-inspired icon automatically generated and converted to `.icns` format

### Improved
- **Cross-Environment Compatibility**: Robust Python environment detection supporting pyenv, anaconda, homebrew, and system Python
- **Portable Launch Script**: Smart Python discovery that works across different users and system configurations
- **Error Handling**: User-friendly dialog boxes for installation and launch issues
- **Documentation**: Updated installation guides for macOS App Bundle workflow

### Fixed
- **Python Environment Detection**: Resolved issues with finding correct Python installation in GUI launch context
- **Development vs Production**: Launch script now correctly uses installed package instead of development version
- **PATH Resolution**: Fixed Python executable discovery when launched from Dock vs terminal

### Technical
- Added `MacOSAppBundleGenerator` class for programmatic app bundle creation
- Enhanced `setup_macos_app.py` with comprehensive Python environment detection
- Updated `pyproject.toml` to include app bundle creation tools as console scripts
- Improved launch script with fallback mechanisms for different Python installations
- Added proper `Info.plist` configuration for macOS app bundle standards

### Installation
```bash
# Simple one-command installation for macOS users
python install.py

# Or manual installation
pip install abstractassistant
create-app-bundle
```

### Usage
- Launch from **Applications folder** or **Dock**
- Look for neural network icon in **menu bar** (system tray)
- All existing CLI options remain available

## [0.2.5] - 2025-10-21

### Added
- **File Attachments**: Click the 📎 button to attach images, PDFs, Office docs, or data files to your messages. The AI can now analyze documents, images, spreadsheets, and more.
- **Clickable Messages**: Click any message bubble in the history panel to copy its content to clipboard. A subtle flash confirms the copy.

### Improved
- **Chat History Layout**: Reduced text size (17px → 14px), increased bubble width (320px → 400px), and tightened spacing throughout for better readability and more efficient use of screen space.
- **Markdown Rendering**: Headers, paragraphs, and lists now use minimal spacing to display more content without scrolling.

### Updated
- **AbstractCore 2.4.5**: Upgraded from 2.4.2 to leverage universal media handling system with support for images, PDFs, Office documents (DOCX, XLSX, PPTX), and data files (CSV, JSON).

### Technical
- Added `ClickableBubble` widget with visual feedback for clipboard operations
- Enhanced `LLMManager` and `LLMWorker` to handle media file attachments
- File chips display with type-specific icons and individual remove buttons
- Improved markdown processor with tighter vertical spacing

## [1.1.0] - 2024-10-16

### 🌐 Major UI Overhaul: Beautiful Web Interface

#### Added
- **Modern Web Interface**: Complete replacement of Qt/Tkinter with beautiful HTML/CSS/JavaScript
- **Glassmorphism Design**: Stunning visual effects with backdrop blur and transparency
- **WebSocket Communication**: Real-time bidirectional communication between web UI and Python backend
- **Responsive Design**: Works perfectly on desktop and mobile browsers
- **Advanced Settings Panel**: Theme selection, temperature control, and token limit configuration
- **Smooth Animations**: Professional transitions and loading states
- **Dark/Light Themes**: Automatic system theme detection with manual override

#### Enhanced
- **Web Server**: Full aiohttp-based server with WebSocket support
- **Real-time Status**: Live updates for connection status and processing state
- **Modern Typography**: Inter font family for professional appearance
- **Gradient Buttons**: Beautiful send button with hover effects
- **Message Bubbles**: Elegant chat interface with markdown rendering

#### Technical Improvements
- Added `aiohttp` and `websockets` dependencies
- Created `WebServer` class with async/await support
- Fallback to simple HTTP server if aiohttp unavailable
- Updated system tray to launch web interface instead of Qt bubble
- Maintained backward compatibility with existing configuration

## [1.0.0] - 2024-10-15

### Added
- **System Tray Integration**: Native macOS menu bar icon with neural network-inspired design
- **Modern Chat Bubble UI**: Glassy, translucent interface with 1/6th screen size
- **Multi-Provider Support**: OpenAI, Anthropic, and Ollama integration via AbstractCore
- **Toast Notifications**: Elegant collapsible notifications with markdown rendering
- **TOML Configuration**: Modern configuration management with validation
- **CLI Interface**: `abstractassistant` command with multiple options
- **Real-time Status**: Token counting and execution status display
- **Copy to Clipboard**: One-click result sharing
- **Keyboard Shortcuts**: Cmd+Enter to send, Escape to close
- **Error Handling**: Graceful fallbacks and user-friendly error messages
- **Debug Mode**: Comprehensive debugging and logging capabilities

### Features
- **Universal LLM Support**: Works with any provider supported by AbstractCore
- **Session Management**: Persistent conversation memory
- **Modern Design**: Dark theme with glassy effects and smooth animations
- **Performance Optimized**: Threaded operations and efficient resource usage
- **Cross-Platform Foundation**: Built for future Windows/Linux support

### Technical
- **Modular Architecture**: Clean separation of concerns
- **Robust Error Handling**: Comprehensive exception management
- **Configuration Validation**: Type-safe configuration with defaults
- **Package Structure**: Proper Python package with CLI entry points
- **Development Mode**: Editable installation support

### CLI Commands
```bash
abstractassistant                    # Launch with default settings
abstractassistant --provider openai # Set provider
abstractassistant --model gpt-4o     # Set model
abstractassistant --debug            # Debug mode
abstractassistant --config custom.toml # Custom config
```

### Configuration
- TOML-based configuration with validation
- Environment variable support for API keys
- Customizable UI themes and behavior
- Provider and model defaults

### Dependencies
- AbstractCore 2.4.0+ for universal LLM support
- CustomTkinter for modern UI components
- pystray for cross-platform system tray
- TOML libraries for configuration management

# Changelog

All notable changes to AbstractAssistant will be documented in this file.

## [Unreleased]

### Fixed (2026-07-18 — model/voice selection is a LOCAL override, never a gateway mutation)
- The settings "Models & Voice" tab (was "Gateway Defaults") no longer writes
  the gateway's SHARED capability defaults when you pick a provider/model. It
  now stores a LOCAL override for this app only (`route_overrides` in
  `preferences.json`) and applies it per request. Chat text rides BOTH the
  top-level `input_data.provider/model` (which reaches the router node) AND
  `_runtime.provider/model` (which the agent node reads) — an adversarial audit
  proved a `_runtime`-only override leaves the router on the gateway default, so
  an online-only default would still break the FIRST call offline. Voice
  output/input ride the TTS/STT calls (STT now sends the provider too — the
  gateway transcribe endpoint accepts it and the client was silently dropping
  it). The gateway's global default is never read-and-pinned or written.
- Root cause of the "it failed offline" report: the old tab called
  `set_capability_default`, so selecting a model changed the gateway's GLOBAL
  default. It had been pointed at an online-only endpoint
  (`endpoint:ovh-provider` / Meta-Llama-3.3-70B); offline, every chat run failed
  (DNS error → circuit breaker). Because the assistant sent no override, it
  inherited that broken global default. Now the assistant never corrupts the
  gateway default, and you can pin a local model as an offline-safe override.
- Added a "Reset to gateway" button per route, and the editor now shows two
  honest lines — the gateway's own default AND what this app pins on top —
  instead of conflating them.
- Scope: the tab now offers only the routes the assistant actually drives and
  can honor as a per-request override — Chat Model, Voice Output (TTS), Voice
  Input (STT). Media/embedding routes were removed from the thin client (the
  assistant only triggers them; configuring the gateway's media models belongs
  to the gateway console, not a thin client that must not mutate the gateway).

### Fixed (2026-07-18 — streaming TTS double-fired its completion signal)
- A successful streaming TTS playback fired `on_speech_end` + the speak()
  callback TWICE: `_finish_stream_playback` returned `None`, so the stream
  worker's `finally` saw `completion_owned` still falsey and fired the terminal
  signal a second time. Symptom: a message card reset to idle then re-armed,
  and full-voice mode saw a spurious second completion. `_finish_stream_playback`
  now returns `True` so the caller honors the exactly-once `completion_owned`
  contract. Regression test added; found while verifying end-to-end online
  voice against the live gateway.
- Verified live (127.0.0.1:8080): bare-default TTS resolves the gateway's
  configured `supertonic/supertonic-3` via the runtime voice-defaults merge;
  explicit `piper` no longer inherits a leaked `voice=M1`; streaming first
  audio ~2s; STT round-trip through the production adapter transcribes
  correctly with the gateway default model; durable session replay passes
  end-to-end (turn 2 answers from turn 1's context).

### Fixed (2026-07-17 — run activity view: shared markdown + working size)
- Model text in the Run Activity view now renders through the SHARED markdown
  renderer (same pipeline as the transcript): tables render as tables, code as
  code, lists as lists — no more raw pipe-text. Tool arguments and results
  deliberately stay monospace (they are data, not prose). The dialog opens at
  920x720 with a 760x600 floor instead of the unusable small default.

### Added (2026-07-17 — colored, clickable run activity)
- The thinking badge is now color-toned by activity — thinking (accent blue),
  tool execution (amber), waiting on you (orange) — instead of the invisible
  gray pill, and it is clickable: it opens a live Run Activity view showing,
  per cycle, the model's ACTUAL intermediate output (content + reasoning when
  the provider reports it), tool calls with their arguments, tool results, and
  waits — streaming in real time while the run progresses (the abstractcode
  unfold pattern as a modeless dialog).
- Honesty fix behind it: the "thinking" text shown previously came from the
  run-activity fallback echoing the user's own prompt. The adapter now emits
  a `cycle_result` event from the COMPLETED reason-node llm_call's RESULT
  (never the STARTED payload, whose messages are the conversation INTO the
  model), so what the view labels "Model" is what the model actually said.

### Fixed (2026-07-17 — Gateway Defaults settings: honest defaults, real catalogs)
- The Gateway Defaults route editor no longer fabricates configuration: an
  unconfigured route (e.g. Speech To Text) used to display the catalog's first
  entries ("openai / gpt-4o-transcribe") as if they were the active values — one
  accidental Save away from routing STT through a provider the gateway cannot
  serve. Each route now has an explicit mode: "Use gateway default" (pick
  controls disabled; an always-visible "Applies now:" line states the resolved
  value and its source, or says honestly that nothing is configured and the
  engine decides) versus "Set explicitly" (dropdowns populated from the
  gateway's own catalogs, placeholder-first, never auto-selected). One Apply
  button serves both modes (saving the explicit pair, or clearing the override
  so the default applies); saving without a real selection is refused inline.
  A saved model/voice is only ever shown under its own provider — switching
  provider resets to the placeholder instead of fabricating an invalid pair.
  Route list shows a configured/default state dot per route; combo dropdown
  arrows are now visible on the dark surface.
- Investigated the underlying "couldn't read a text" outage: server-side, not
  this app — all gateway TTS calls wedge (runs stuck running for hours) since
  the 23:49 stack rebuild, gateway capability defaults for voice are never
  merged into bare TTS/STT specs at the runtime layer, and the saved TTS voice
  option leaks into other providers ("Unknown voice_id: M1" from piper). All
  three filed with the owning seats (gateway/runtime/core) with evidence.

### Fixed (2026-07-16 — conversation memory: durable server-side session replay)
- The assistant remembers the conversation again. Since Jul 7 every send started a
  fresh gateway run whose model context contained ONLY the new prompt — follow-up
  questions met an assistant that had never seen its own previous answer (the
  client-side transcript seeding was removed on the assumption of a server-side
  replay that did not exist). Runs now opt in to the gateway's durable session
  replay (`use_session_history: true`): at run start the gateway seeds
  `context.messages` from the session's prior completed turns, reconstructed from
  the run store (agora `durable-sessions` contract v1, implemented with the
  gateway and runtime packages). The local transcript stays display-only; history
  is server-owned, durable, and identical to what the history bundle shows.
  Requires a gateway running abstractgateway with the seed (and
  AbstractRuntime>=0.4.30) — older gateways simply ignore the flag.

### Changed (2026-07-15 — settings redesign + run status merged into the thinking badge)
- Assistant Settings completely redesigned for density: the internal header (title/subtitle/
  separator duplicated by the window title bar) is gone, controls dropped from 38px to 26px with a
  12px type scale, cards are flat (no gradients/drop shadows/hover accents), the green primary
  buttons were replaced by the dialog's single indigo accent, action buttons are right-aligned
  (primary last), and paddings/spacings were halved throughout. The dialog now opens at 620x480
  instead of 860x640 with the same content.
- Run observability moved to the bottom of the transcript: the yellow status banner above the
  history ("Thinking — cycle 3", "Tool: read_file …", steering/pause/approval waits) now renders
  inside the thinking-dots pill as one badge — dots + status text in the dots' muted palette,
  eliding to the viewport width with the full text on hover. Non-run statuses (errors, "Run
  stopped.", bootstrap "Connecting…") keep the top line, which is the only time it appears.
- The reattach banner shows the thinking badge immediately instead of waiting for the first replay
  event.

### Fixed (2026-07-15 — empty-state truncation)
- The "Ask anything" empty state no longer clips in the collapsed palette: oversized margins
  (48px) shrank to fit the ~110px viewport, and the subtitle renders on one line (Qt's word-wrap
  heuristic folded it even with room to spare, and the folded line was what got cut).

### Fixed (2026-07-15 — GUI-thread responsiveness + run reattach)
- The send path no longer blocks the GUI thread on gateway round trips. Workflow-catalog and
  tool-inventory lookups are cached in the controller (short TTL + explicit invalidation on
  connection/route/tool-preference changes), and startup warms them on a background thread, so a
  warm send performs zero blocking gateway calls. Sends are refused (with a "Connecting…" note)
  until startup finishes rather than freezing on a cold fetch.
- After a quit or crash mid-run, relaunching now reattaches to the durable run: a still-running or
  user-waiting run resumes and streams its result, and a run that finished while the app was closed
  has its answer recovered into the transcript. Already-answered approval/ask dialogs are not
  re-opened on reattach.
- Tool-approval and ask-user prompts now bring the palette to the front and post a tray
  notification when it is hidden or in the background, so a run waiting on you is not missed.

### Added
- App icon: a designed rounded-square mark replaces the procedural icon (bundled asset;
  transparent corners).

### Changed (2026-07-15 — visual overhaul + voice-by-default + latency control)
- Icons redrawn. The ~15 hand-drawn QPainter glyphs (inconsistent stroke weights and sizes) are
  replaced by a coherent Lucide icon set rendered from inline SVG (`abstractassistant/icons.py`),
  crisp on Retina and with a loud fallback for unknown names. New glyphs are available for future
  surfaces (agent/entity, chevrons, reconnect, trash, mic-off, etc.).
- Introduced `abstractassistant/theme.py` as the single source of truth for design tokens
  (semantic colors, spacing, radii, type scale), replacing scattered color literals over time.
- Typography: the app now uses the real macOS system font (San Francisco) set programmatically,
  instead of unresolvable Qt `font-family` aliases that emitted startup warnings and fell back to
  Helvetica. Markdown headings get a compressed chat scale (were all collapsed to body size), the
  double body inset is removed, and links/blockquotes use the app accent.
- Layout: user messages now render narrower than assistant replies (a short prompt is no longer a
  full-width slab); a fresh session shows a centered empty state; the connection indicator is a
  flat status dot + ring (was a glossy sphere); the thinking dots use the app accent.
- Voice ships by default: `abstractvoice[audio-io]` (streaming TTS playback + mic capture) is now a
  base dependency, and the macOS build fails loudly if local audio I/O is missing rather than
  shipping a degraded bundle.
- New "Voice latency" preference (Balanced / Faster / Higher quality) maps to the gateway TTS
  `quality_preset`, sent only when the gateway advertises support — a client lever to shorten
  time-to-first-voice.

### Removed (2026-07-15 — gateway-native only: local execution engine removed)
- The assistant is now purely gateway-native: the unreachable local (non-gateway) execution engine
  was removed — `core/agent_host.py`, the local AbstractVoice TTS wrapper (`core/tts_manager.py`),
  and every local branch in `core/llm_manager.py` (local `generate_response`, provider/model
  selection, token-usage view, save/load session, local session titles). `LLMManager` is now a
  focused gateway session/transcript manager.
- Configuration: the `use_gateway` flag and the whole `llm` config section (`default_provider`,
  `default_model`, `max_tokens`, `temperature`) are gone — the gateway owns provider/model routing.
  A gateway URL is always required (defaults to `http://127.0.0.1:8080`).
- Dependencies: `abstractagent` is no longer required; `abstractruntime` is now declared directly
  (session-memory run-id contract). `abstractcore` no longer pulls provider extras — providers run
  on the gateway.
- Dead client-side surfaces deleted after an adversarial audit: the client image-intent pipeline in
  `gateway/generated_media.py` (ADR 0001 forbids client-side media execution; the gateway-emitted
  media events remain fully supported), `gateway/templates.py`, `gateway/session_cache.py`
  (client-side prompt-cache negotiation, also ADR-forbidden), `core/transcript_summary.py`,
  `core/gateway_selection_store.py`, test-only capability helpers, and unused controller wrappers.
- Tests: `tests/integration/` (local agent-host tests) removed; the suite is `tests/basic` (232
  tests).

### Changed (2026-07-15 — single-package consolidation, legacy UI removed)
- The desktop shell is now a single package. The gateway-native palette that shipped under
  `abstractassistantv2/` moved into `abstractassistant/` and the legacy Qt "bubble" UI was removed.
  Module map: `abstractassistantv2/app.py` → `abstractassistant/app.py`, `controller.py` →
  `abstractassistant/controller.py`, `gateway.py` → `abstractassistant/gateway_service.py` (renamed
  to avoid colliding with the `abstractassistant/gateway/` client package), and
  `assistant_workflow.py`, `hotkey.py`, `preferences.py` moved as-is.
- `AssistantV2Controller` is renamed to `AssistantController`.
- `launch_tray_app` is now exposed from the package root (`from abstractassistant import
  launch_tray_app`) with lazy GUI imports, so `import abstractassistant` and `assistant --help`
  remain free of Qt/voice dependencies.
- Removed the legacy UI modules (`ui/qt_bubble.py`, `ui/history_dialog.py`, `ui/provider_manager.py`,
  `ui/ui_styles.py`, `ui/tts_state_manager.py`, `ui/toast_window.py`, `ui/run_state.py`), the unused
  `web_server.py`, and the `pystray` and `pyperclip` dependencies they required (the palette uses the
  Qt clipboard and tray directly). No user-facing behavior changes: the shipped `assistant` command
  already launched the palette.

### Fixed (2026-07-15 — speaker-button freeze + time-to-first-voice regression)
- Clicking a message speaker button no longer freezes the app. `GatewayVoiceManager.speak()`
  now dispatches on a worker thread and returns immediately: the whole synthesis + artifact
  download (two HTTP calls with 120s timeouts) used to run on the Qt GUI thread, beachballing
  the app for the entire synthesis (~1 minute for a long reply) — the "synthesizing" spinner
  on the speaker icon was already wired but could never paint because the event loop was
  blocked. It now animates during the preload phase. The same freeze affected auto-speak on
  every long final reply.
- Restored fast time-to-first-voice. The gateway advertises streaming TTS (JSONL wav segments,
  ~3s to first audio measured live) but the client silently fell back to single-shot
  whole-message synthesis because `sounddevice` was missing from the build environment — the
  bundle built from a venv without the `[voice]` extra loses the in-process audio player, and
  with it both audio streaming and microphone capture. The degradation is now loud:
  a `#FALLBACK` warning when streaming is advertised but unconsumable, and a build-time
  preflight banner in `build_macos_app` when `sounddevice` is absent.
- Speech completion is now signalled exactly once for every dispatched speak — including
  failures and cancellations. Previously a stopped stream swallowed the completion callback,
  which could leave a message card stuck on "speaking" and full-voice mode wedged in
  PROCESSING.
- Pausing during the synthesizing phase is now honest on the artifact path: playback holds
  until resume (or cancels on stop) instead of returning False while the UI showed "paused".
- Stopping during artifact synthesis can no longer start zombie playback after the download
  completes (generation stop-gate checks between synthesis, download, and playback).
- Full-file audio meter level extraction (WAV decode + FFT per 33ms slice) is skipped when no
  meter consumer is registered (the v2 palette never registers one).
- Removed the stale in-repo `abstractassistant.egg-info` (0.4.11) that shadowed the installed
  0.5.0 metadata whenever python ran from the repo root — this is why freshly built bundles
  self-reported 0.4.11.

### Changed (2026-07-15 — message card + icon readability pass)
- Message-card speaker/copy buttons now appear only while the mouse is over the card. They keep
  their layout slot and fade via opacity (never show/hide), so revealing them cannot reflow the
  card under the cursor; while a reply is being synthesized/spoken/paused the speaker button
  stays pinned visible as a playback indicator. Hidden buttons are also disabled so an invisible
  target cannot be clicked.
- The per-message timestamp moved from its own bottom row to the upper right of each bubble,
  co-located with the hover actions (always visible, muted). The bottom stamp row is gone, which
  returns one line of vertical space per bubble.
- All symbol icons are ~15% larger across the app (message actions 15→17px in 24→28px buttons,
  header plus/capabilities/speaker/settings 14→16px in 24→28px buttons, composer attach/mic
  16→18px, send/stop 18→21px, media/tool/file card icons scaled to match).
- Symbol icons now render at 2x device-pixel-ratio (same pattern as the tray icons), so they are
  crisp instead of blurry on Retina displays.

### Added
- Assistant replies in the palette now end with a discreet per-answer stats line —
  `input : … tk | output : … tk | tools : … | files : …` — with investigation tooltips on each
  segment: token tooltips show exact counts and the number of LLM calls, the tools segment lists
  every executed tool with what it did (and stays clickable to open the full tool-usage dialog),
  and the files segment lists which files were created, modified, moved or deleted.
- File activity is derived by a new conservative classifier
  (`abstractassistant/core/file_activity.py`) that understands the dedicated file tools
  (`write_file`, `edit_file`, `delete_file`, `move_file`, …) and simple `execute_command`
  shell forms (`mkdir`, `touch`, `mv`, `cp`, `rm`, output redirects). Ambiguous commands
  (globs, substitutions) are deliberately not counted, and failed tool calls are excluded.
  When a replayed message carries no tool details, the files segment is omitted rather than
  guessed.
- User messages now have the same top-right copy button as assistant replies.
- The `files` stats segment is now clickable (like `tools`) and opens a dedicated
  "Files affected in this answer" dialog: one scrollable card per file mutation with a colored
  action chip (CREATED / MODIFIED / MOVED / DELETED), the full path (from → to for moves) and
  the tool that performed it, hydrated from the run ledger on open.
- Tool and file usage dialogs were redesigned around informative cards: each tool card shows
  the tool name, what it did, its key parameters, a per-call execution outcome chip
  (COMPLETED / FAILED) with the error message when a call failed, and a raw-payload toggle —
  all in a scrollable card list.

### Changed
- The footer metric chips (colored `IN/OUT/tools` badges) were replaced by the flat stats line
  above; duration and model remain as trailing dim segments, and the run's LLM-call count moved
  into the input-tokens tooltip.
- Persisted per-run tool details now retain each call's `success`/`error` outcome so replayed
  messages can report honest tool/file stats.

### Fixed
- Answer stats were empty for agent workflows: the final message only carried the ROOT run's
  stats bucket while llm_call/tool_calls effects execute in sub-runs. Stats are now folded by a
  shared module (`abstractassistant/gateway/run_stats.py`) and aggregated across the whole
  followed run tree (tokens/calls summed, duration as the wall-clock span across runs).
- Answers recovered from a run's history bundle (`recovered_history_answer`, e.g. after the
  final event was missed or on reattach) carried no stats at all — and history reseeding at the
  end of every run REPLACED the live message's stats with a stats-less copy. Seeded messages now
  derive `_assistant_stats` from the bundle's ledgers (root + sub-runs); other session turns are
  left untouched.
- The live-followed final answer is now authoritative: the post-run history reseed no longer
  REPLACES a transcript that already carries the run's final answer (that replace could discard
  the live message and re-materialize it through the `recovered_history_answer` path, losing
  stats when the gateway's session turns were missing). Reseeding now runs only as a gap filler
  when no final answer was observed on the stream — and seeded answers derive full stats from
  the bundle's ledgers, so even that path carries real token/tool/file numbers.
- No partial stats fallbacks: a bare workflow-meta tool count (no recorded stats) renders no
  stats segments — messages persisted before stats recording existed show only the model line.

## [0.5.0] - 2026-07-07

### Added
- The shipped palette (v2) now has a working **Stop** control: while a run is active the
  composer's send button becomes a Stop button that submits a durable gateway `cancel` for the
  run and interrupts the local follower.

### Changed
- The palette header now includes a recent-session picker with compact `yy/mm/dd - topic` labels.
  When a durable session topic is not available yet, the picker falls back to the first user
  query.
- The header connection indicator is now a larger live orb at the far right of the palette and
  reflects actual gateway connection status instead of only workflow availability.
- Ask-user prompts no longer resume the run with a silent empty answer on Cancel (both UIs):
  cancelling now asks whether to send an empty response or keep the run waiting, and a kept
  wait is re-prompted the next time the window is shown. The legacy bubble's ask dialog also
  accepts multiline answers.
- Gateway-mode connection errors now name the gateway (with its URL) instead of "the provider",
  and the legacy bubble schedules a reattach attempt once the gateway is back. Provider-discovery
  failures at startup now surface as an OFFLINE status pill (with remediation in the tooltip)
  instead of a console-only warning under a green READY pill.
- Refusing to enable text-to-speech (no backend / no TTS support) now explains why in a visible
  warning instead of silently snapping the toggle back off.

### Fixed
- The macOS app-bundle build now uses a narrower PyInstaller hidden-import surface for the
  gateway-native tray app, which avoids force-collecting the full optional `abstractcore`
  dependency tree during bundle builds.
- The PyInstaller spec now excludes `pygame` (pulled in via nltk's lazy `timit` corpus import,
  never imported by the app); its bundled SDL dylibs failed binary processing during COLLECT
  (`SystemError: ... pygame/.dylibs/libwebp.7.dylib`) and broke the macOS app build.
- Typing in the legacy Qt bubble was completely broken: `_qt_key` was declared `@classmethod`
  without a `cls` parameter, so every keypress raised `TypeError` before the character could be
  inserted. Regression-tested.
- Tool-approval and ask-user waits are now answered by identity (`run_id` + `wait_key`) instead
  of a single "last observed wait" slot, so a second approval request arriving while a dialog is
  open can no longer steal the answer and leave the first run waiting forever (shared
  `GatewayWorker`, both UIs).
- An open Messages window now receives new answers: the update path called a nonexistent
  `refresh_messages` method (swallowed `AttributeError`) and the show-path was a no-op when the
  history toggle was already checked.
- `send_message` now refuses to start while a worker run is active — the Enter key bypassed the
  disabled send button and could rebind a live `QThread` (fatal "Destroyed while thread is still
  running" class) and stream two runs into one session. Also removed a dead block referencing an
  undefined `run_id` that raised a swallowed `NameError` on every send.
- Closing the bubble mid-run no longer calls `QThread.terminate()` with an unbounded `wait()`
  (crash/hang-on-quit class); the worker is interrupted cooperatively with a bounded wait.
- "Reconnect gateway" can reattach again: the one-shot startup reattach guard was never reset, so
  every later reconnect silently skipped re-following the in-flight run.
- The gateway ledger follower now retries transient connection failures (gateway restart, network
  blip) with bounded backoff instead of dying on the first error, honors cancellation while
  streaming (per-SSE-line stop signal), and still fails fast on non-transient HTTP errors. It also
  clears the OFFLINE state on the idle-timeout path (the stream normally exits via idle, so the
  pill would otherwise stay OFFLINE for the rest of a healthy run), and an exception raised by the
  record callback is no longer misclassified as a transient transport error and retried past its
  cursor (which would silently drop the record).
- Full voice mode no longer wedges in PROCESSING when a run is already in flight: the send guard's
  refusal is now observable (`send_message` returns a bool), so the voice loop releases its busy
  latch and resumes listening instead of going deaf until the in-flight run finishes.
- Keyed wait answers require both `run_id` and `wait_key` to target a wait by identity (a lone
  kwarg falls back to the pending wait wholesale rather than stitching a mixed identity), and the
  pending-wait slot is cleared only on a full `(run_id, wait_key)` match (wait keys such as
  `voice_input` can repeat across runs). The ask-user crash fallback and legacy input-dialog path
  now also honor wait identity and the Cancel-keeps-waiting semantics.
- After a gateway drop mid-run, the legacy bubble now retries reattach with capped backoff
  (5s/15s/30s/60s) instead of a single fixed 5s attempt, matching what the error message promises.
- Gateway session snapshots are now mutated under a lock and saved through unique temp files —
  concurrent appends from the worker/wait-submit/main threads could previously lose messages or
  interleave two writers into invalid JSON (which then silently loaded as an empty transcript).
  Snapshot saves also resolve their target file from the snapshot's own session id, so a stale
  write can no longer land in another session's file.
- The input placeholder taught the wrong gesture ("Shift+Enter to send"); Enter sends and
  Shift+Enter inserts a newline. Escape now hides the bubble when voice is idle (the ⨯ button
  quits the app, so there was no keyboard way to dismiss the window).
- TTS "paused" no longer renders with the error style in the dormant `TTSStateManager` path, the
  toast module no longer prints diagnostics at import time, and the markdown code font stack is
  Menlo-first (`SF Mono` is not resolvable in Qt on macOS).
- Remote-image thumbnails in the Messages window now marshal downloaded bytes through the
  button's thread-safe signal (like artifact thumbnails); the previous `QTimer.singleShot` from a
  plain thread never fired, and its fallback touched `QPixmap` off the GUI thread.
- Restarting the gateway voice meter now uses fresh per-generation stop/pause events, so an old
  meter thread that missed the stop flag can no longer resume alongside the new one (flickering
  tray meter).

- The shipped palette (v2) now cleans up on quit: `QApplication.aboutToQuit` interrupts the
  running worker (bounded wait), stops the global hotkey listener, and cleans up voice — quitting
  mid-run no longer risks a "QThread: Destroyed while thread is still running" crash.
- Voice dictation in the palette now marshals recognizer-thread callbacks (transcription / listen
  stop) onto the Qt main thread via signals instead of mutating widgets off-thread.
- `assistant --version` now reports the installed package version instead of a hardcoded string.
- Dropped unused runtime dependencies `markdown`, `pymdown-extensions`, and `plyer` (only
  `markdown-it-py` + `pygments` are used); the macOS spec no longer force-collects `pymdownx`.

### Removed
- Deleted the dead CustomTkinter modules `ui/toast_manager.py` and `ui/chat_bubble.py`
  (unimportable: `customtkinter` is not a dependency; nothing imported them).
- Removed the Python 3.9 classifier (the package requires Python >= 3.10).

### Packaging
- The macOS bundle declares `NSMicrophoneUsageDescription` so voice mode no longer trips macOS
  TCC termination on first microphone access.

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

# ADR 0008 — The desktop host stays PyQt5 for this cycle; a Rust/Tauri shell is a gated spike

Status: Proposed (recommendation to the operator, 2026-10-26)
Date: 2026-10-26
Relates to: [ADR 0001](0001_gateway_native_assistant_v2.md) (thin client of the gateway),
[ADR 0006](0006_macos_signing_and_distribution.md) (signing, bundle id),
[ADR 0007](0007_web_assistant.md) (the web assistant and what a host must provide),
backlog [1056](../backlog/planned/1056_apple_lessons_for_the_desktop_assistant.md) (the polish
plan), backlog [0003](../backlog/proposed/0003_tauri_shell_spike.md) (the spike).

## Context

On 2026-10-26 the operator opened the door to rewriting the desktop systray assistant in Rust,
"if it could be cleaner", while stating the actual goal: the systray assistant works; it needs
aesthetic polish and alignment with the watch and iPhone apps, and it must keep working across
desktops (macOS, Linux, Windows). The operator also rejected "one UI" across web and desktop: a
browser page and a palette docked under a menu-bar icon (~420x700) are different shapes.

The wave of the same day produced the inputs this decision rests on:

- **The inventory of what any new host must carry** (W2 report §5, with file:line for each): wait
  identity `(wait_key, step_id)` and reattach after relaunch; the pending-user-waits signal and
  tray states; attachment durability through `$artifact` and owner-run download; the
  gateway-first session fold; the `/me/events` stream with `Last-Event-ID`; the voice split
  (capture, VAD, 48 kHz playback local; STT and TTS on the gateway); the hotkey; the Cocoa
  bridge; 22 themes. The desktop is 52.6k lines of Python (PyQt5) with a 31.8k-line test suite
  that is its behavioural specification.
- **The web assistant** (ADR 0007) was built host-agnostic in one day: 2.3k lines of TypeScript
  behind one host interface. The adversarial review found that this port had already dropped
  one hard-won behaviour (a stream closing without `done` was treated as finished, the exact
  "run parked on an approval nobody saw" failure the desktop fixed in September) and weakened
  another (a stale approval card could answer a newer wait on the runtime's reused wait key).
- **Platform facts for a Tauri 2 shell** (adversary §3, from wry 0.57 / Tauri 2.12 sources,
  MDN, WebKit): `MediaRecorder` is unusable on stock Ubuntu 22.04/24.04 (GStreamer too old) and
  `audio/mp4`-only on WKWebView, so dictation would need an AudioWorklet PCM path or Rust
  `cpal`; the Linux tray backend (AppIndicator) delivers no left-click events and writes a PNG
  per icon update, so a 15 fps voice badge is impossible there; global shortcuts are X11-only
  (no worse than pynput today); `backdrop-filter` silently draws nothing on WebKitGTK; the
  gateway would have to allow the `tauri://localhost` and `http://tauri.localhost` origins and
  the cookie-session browser host does not carry over (a bearer host is mandatory).
- **Size**: the Rust side is small (~1.9k lines; ~3k with audio in Rust). The cost is the
  frontend reaching parity with the inventory: months, against 2–4 weeks for the polish.
- **Signing**: Tauri's bundler signs and notarizes natively and a WebView app needs only the
  `audio-input` entitlement; ADR 0006's Apple-side decisions (Developer ID channel, the
  credentials, the `ASC_*` names, and above all the bundle id) survive a host change. The
  PyInstaller planner would become throwaway for a new app, but not while signed PyQt builds
  ship in the meantime.

## Decision

1. **The desktop host stays Python/PyQt5 for this cycle.** The stated goal is reached by
   polishing the existing app: backlog 1056 (the two confirmed bugs first, then the Inbox,
   edit-and-resend, review-before-send, the per-answer activity, Archive/Restore, the tray's
   listening/transcribing states) plus the port of the orb and the design tokens onto the Qt
   palette (a `QPainter` orb from the phone's shared geometry, `web/design/tokens.css` mapped
   onto the uic theme the desktop already reads). No Python code is removed for a rewrite.
2. **The web assistant stays host-agnostic** as ADR 0007 §4 specifies (one host interface; a
   bearer host anticipated; SSE through `fetch`). This is cheap insurance, not a commitment:
   the shared layer is the component library and the tokens, never the page layout. A compact
   ~420 px layout is a breakpoint of the web app, which the Qt palette does not consume.
3. **A Rust/Tauri 2 shell is a gated spike, not a plan.** The gate is a change of goal by the
   operator: one component codebase for web and desktop, or first-class Windows and Linux
   distribution. If the gate opens, backlog 0003 runs as a one-week spike on macOS, Windows and
   Ubuntu 24.04 (X11 and Wayland) and must prove, with measurements: a tray badge updating at
   15 fps with click handling; hotkey to a focused composer in under 150 ms; AudioWorklet PCM
   capture to gateway STT without `MediaRecorder`; streamed TTS with first audio under 1 s;
   a CHILD-run approval answered from the palette; the bearer host with gateway CORS for both
   Tauri origins; a signed and notarized `.app` with only `audio-input`, keeping the TCC grants
   under the same bundle id. A spike that fails any of these ends the question for the cycle.
4. **The bundle id `ai.abstractframework.assistant.mac` is decided now and kept whatever the
   host** (ADR 0006), so microphone and Accessibility grants carry over to any future app.
5. **Two questions stay open on the record** rather than being inherited silently: (a) the
   token store of a Rust shell (the framework's no-keychain rule covers its Python packages, the
   Apple apps use the Keychain by operator decision; the review recommends the 0600 protected
   file so there is one store on three OSes); (b) the Qt 5.15 end of life: a move to
   PyQt6/PySide6 is the cheaper hedge and is not urgent.

## Consequences

- The polish work lands in Qt and is portable by construction (1056 carries a portability
  column; macOS-only items are excluded).
- The web assistant and the desktop share design (tokens, the orb's state machine and
  geometry, the copy) but not code. Divergence is a review item, not a build failure.
- The signing path of ADR 0006 is the shipping path for the desktop; nothing in it is
  throwaway for this cycle.
- Reopening this decision requires the gate in point 3 and the spike's measurements, not a
  preference for the language.

## Alternatives considered

- **Tauri 2 shell around the web components now** (the lead's first position): rejected for
  this cycle on the evidence above; the day-one regressions in the web port are the strongest
  single datum, because they show what "re-earning the spec" costs even for a careful port.
- **A pure-Rust GUI (iced, egui, Slint)**: rejected outright; it duplicates the UI work the web
  needs and makes the orb, themes and animation more expensive than CSS/SVG or QPainter.
- **PyQt6/PySide6 migration now**: deferred; it changes nothing the operator asked for.

## References

- `untracked/apple-web-wave/adversary.md` §3 (host assessment) and
  `untracked/apple-web-wave/w2-apple-to-desktop.md` §5 (the inventory) — session scratch,
  not tracked; their substance is summarised above.
- [Tauri 2 macOS signing](https://v2.tauri.app/distribute/sign/macos/)

# 1061 — iPhone and Apple Watch: the gateway's voice library in Voice settings

> Package: abstractassistant (iPhone `phone/iphone`, Apple Watch `watch/apple`)
> Type: task
> Created: 2026-10-27
> Status: Completed
> Completed: 2026-10-27
> Priority: P1
> Labels: iphone, watch, voice, gateway-0.16.0
> Parent: framework root item 1055 — [Release wave 2026-10-27: voice library, personal voices, replayable ledger, memory graph, shared UI primitives](../../../../docs/backlog/planned/1055_release_wave_2026_10_27_voice_library_replay_memory.md) (track "Shared UI: voice picker, create a voice", row "iPhone/watch branch")
> Sibling: [1060](1060_desktop_voice_library.md) (the desktop side, same rules)

## Current code reality (before)

Voice settings on the iPhone and the watch listed the gateway catalog's voices flat: only records with
`params {provider, model, voice}`, so cloned voices (spoken by `voice_id` on their engine) were missing,
with no owner, no language and no way to create, rename or delete a voice. AbstractGateway 0.16.0 adds
the voice library (`POST /voice/design`, multipart `POST /voice/clones`, `PATCH`/`DELETE
/voice/clones/{id}`; refusals 403/422/501 as `{"detail": ...}`) and personal voices per account;
contract in abstractgateway `docs/api.md` "Voice library" and `routes/voice_library.py`.

## Scope and expected outcome

- Shared client (`watch/apple/Packages/AbstractGatewayClient`): catalog entries grouped **Your voices /
  Engine voices / Shared voices** (a clone by its `kind` before `voice_kind`; `tags.builtin` or
  `params.meta.scope == "library"` is shared), each with its language, languages and description;
  clones spoken by `voice_id` on their engine; the language filter (an unrestricted voice speaks every
  language, the chosen voice stays listed); `designVoice`, `cloneVoice`, `renameVoice`, `deleteVoice`;
  a refusal surfaces as the gateway's sentence.
- iPhone: the grouped list with each voice's language, **Voices that speak…**, the selected voice's
  description; **Create a voice** from a description or from a recording (microphone, 5-20 s, or a
  WAV/FLAC/OGG/MP3/M4A/WEBM file; language **Detect** by default; optional transcript and name) with
  progress while the gateway works; swipe to rename/delete one's own voices, shared voices read-only;
  the new voice selected when it speaks on the assistant's engine, otherwise said plainly.
- Watch: the same groups and language filter, and "Create voices on the iPhone or the desktop."

## Completion report — 2026-10-27

Delivered on branch `feat/voice-library-ios` (cut from `feat/voice-library`; not pushed):

- `186ab99` — AbstractGatewayClient voice library (grouping, languages, filter, the four calls, the
  sample gateway's own/engine/shared voices) and AssistantKit `VoiceCreation` (the two forms, the
  request each sends, `VoiceCreationOutcome`: selected, elsewhere, unlisted); tests.
- `d4241da` — iPhone `VoiceSettingsScreen` / `CreateVoiceScreen` and watch `VoiceSettingsView`; UI tests.
- `f359505` — changelogs (Unreleased), READMEs, architecture docs.
- `70bcc1b` — test: a built-in voice listed from AbstractVoice's personal layer (`meta.scope:
  personal`, `tags.builtin: true`) is shared. The only built-in record in the earlier test also had
  `scope: library`, so dropping the `tags.builtin` rule survived (mutation C2 below).
- `0f23e12` — `llms-full.txt`: the f359505 doc hunks only. A full `scripts/update_llms_full.py` run
  from the committed sources would also revert sign-in wording that `llms-full.txt` has carried since
  0fc6c51, which no committed source holds. Regenerate in full once those doc sources are committed.
- `b80e6ef` — the recording ticker in its own method (fixes the `ImplicitStrongCapture` warning the
  new screen added; the rebuild after it reports no warning).

A leftover uncommitted change from the interrupted worker removed `store.preferences.voice = choice`
from `CreateVoiceScreen.create()`. That was the UI mutation check for "the new voice is selected" (run
red below), not a change to keep, and it was reverted.

## Validation

| Command (from `phone/iphone/`) | Result |
| --- | --- |
| `swift test --package-path ../../watch/apple/Packages/AbstractGatewayClient --scratch-path build/ClientTests --jobs 1` | 174 tests passed (baseline before the branch: 164) |
| `swift test --package-path Packages/AssistantKit --scratch-path build/SwiftTests --jobs 1` | 205 tests passed (baseline: 198) |
| `xcodegen generate --spec project.yml`, then `xcodebuild -scheme AbstractAssistantPhone -destination 'generic/platform=iOS Simulator' … build` (carries the watch app) | exit 0 |
| `xcodebuild -scheme AbstractAssistantWatch -destination 'generic/platform=watchOS Simulator' … build` | exit 0 |
| `python3 scripts/build.py --ui-test <temporary iPhone 17 Pro, iOS 26.5>` with `--only-testing` the voice library test and the four other Voice settings/voice tests | 5/5 passed |
| `xcodebuild test -scheme AbstractAssistantWatchUITests -destination 'platform=watchOS Simulator,id=<temporary Series 11, watchOS 26.5>' -only-testing:AbstractAssistantWatchUITests/VoiceSettingsUITests` | 2 passed, 1 skipped (`testSpinnerWhileTheSampleIsMade` needs `GW_URL`) |

Mutation checks (each applied alone, the test run, the source restored). Every one fails its test:

- Client (`VoiceLibrary.swift`, `GatewayClient.swift`; suites `VoiceLibrary*`): `voice_kind` before
  `kind`; no `tags.builtin` rule (red only after `70bcc1b`); no library scope; no unrestricted
  language; filter drops the chosen voice; `provider` not sent; clone without the engine's first
  model; no description; language not normalised; rename as PUT; no voice-id path guard; 20 s timeout;
  empty name/language sent to design.
- AssistantKit (`VoiceCreation.swift`): language always sent; non-cloning engine sent; always selected;
  the gateway default's engine ignored; no 5 s minimum; no 20 s maximum; no 25 MB cap; no format check;
  unlisted reported as elsewhere; description not trimmed.
- iPhone UI (`testVoiceLibraryGroupsFilterManageAndCreate`): the new voice not selected ("the new voice
  is the assistant's voice"); swipe actions on shared voices ("a shared voice offers Delete"); no
  progress text ("no progress while the voice is made").
- Watch UI (`testVoicesComeInGroupsWithTheirLanguage`): no "Create voices on the iPhone or the desktop"
  line; no language filter; no group headers.

Not verified here: a real gateway (every UI test runs on the sample gateway); a microphone recording
or a file import sent end to end (the UI test checks the recording form's Detect default and that
nothing can be sent without a recording; the request it builds is covered by package tests); the
"made on another engine" message on screen (covered by `VoiceCreationOutcomeTests`); a physical
iPhone or watch.

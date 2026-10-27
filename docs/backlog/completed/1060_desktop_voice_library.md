# 1060 — Desktop: the gateway's voice library (create a voice, grouped voices)

> Package: abstractassistant (desktop)
> Type: task
> Created: 2026-10-27
> Status: Completed
> Completed: 2026-10-27
> Priority: P1
> Labels: desktop, voice, gateway-0.16.0
> Parent: framework root item 1055 — [Release wave 2026-10-27: voice library, personal voices, replayable ledger, memory graph, shared UI primitives](../../../../docs/backlog/planned/1055_release_wave_2026_10_27_voice_library_replay_memory.md) (track "Shared UI: voice picker, create a voice", row "Assistant desktop branch")

## Current code reality (before)

The speech route's Voice list in Settings showed the gateway catalog's voices flat, without saying whose
they were or which language they speak; the desktop could not create a voice. AbstractGateway 0.16.0
adds the voice library (`GET/POST /voice/clones`, `PATCH`/`DELETE /voice/clones/{id}`, `POST /voice/design`,
`GET /voice/languages`, `?language=` on `/voice/voices`) and personal voices per account (0942).

## Scope and expected outcome

- Gateway client: `voice_languages`, `voice_clones(language=)`, `voice_design`, `voice_clone_create`
  (multipart, `provider`), `voice_clone_update`, `voice_clone_delete`, `language` on `voice_voices`.
- Voice list grouped **Your voices / Engine voices / Shared voices** with each voice's language.
- **Create a voice** dialog (from a description, from a recording file) off the Qt thread; the gateway's
  refusal (403 shared store, 501 engine missing) shown as its sentence; the new voice selected.

## Completion report — 2026-10-27

Delivered on branch `feat/voice-library` (not pushed):

- `f4e9042` — the voice library client calls, the Create a voice dialog, grouped voice choices, docs.
- `6333af4` — review fixes after an adversarial review (2026-10-27):
  - B1: a clone is recognised by its record's `kind` before `voice_kind` (the gateway's catalog merge,
    `_gateway_catalog_voice_items` in abstractgateway routes/gateway.py, sends clones as
    `voice_kind: "voice"`); the test runs on the exact record those gateway functions emit. The third
    group is **Shared voices** and the suffix "(shared)" (built-in and administrator-shared voices).
  - B2: a voice created on another engine switches the route to that engine (its first model, the voice
    selected and saved) when the Provider list offers it, else a message names the engine; the selected
    provider rides into the dialog and a cloning engine (qwen3-tts, omnivoice, f5_tts, chroma, audiodit)
    is sent with the recording (controller and service take `provider`).
  - B3: a recording's language defaults to **Detect from the recording** (no `language` sent); a
    description keeps one.
  - B4: Cancel drops a late result (no accept after reject); the dialog is released (`deleteLater`).

## Validation

Each review fix has a test that was run red against `f4e9042` before the fix (9 of 13 tests in
`tests/basic/test_voice_library.py` failed: grouping on the gateway's record, Shared voices label,
detect language, cloning engine in dialog and in controller/service, late result after Cancel, route
switch to the created voice's engine, the unlisted-engine message, dialog release) and green after.

| Command | Result |
| --- | --- |
| `.venv/bin/python -m pytest -q -p no:cacheprovider tests/basic/test_voice_library.py` | 13 passed |
| `.venv/bin/python -m pytest -q -p no:cacheprovider tests/basic` | 1355 passed, 4 skipped |
| `.venv/bin/python scripts/update_llms_full.py` | regenerated; its diff holds only this change's hunks |

Re-run 2026-10-27 on branch `feat/voice-library-ios` (it carries 6333af4), with the repository's `.venv`
interpreter and `PYTHONPATH=<worktree>:<abstractframework>/abstractcore`: that `.venv` holds abstractcore 2.13.38
while `pyproject.toml` requires `>=2.16.0` (`abstractcore.utils.identity`), so three dialog tests fail on
`ModuleNotFoundError` against the installed package and pass against abstractcore 2.30.0 from source.

| Command | Result |
| --- | --- |
| `python -m pytest -q -p no:cacheprovider tests/basic/test_voice_library.py` | 13 passed |
| `python -m pytest -q -p no:cacheprovider tests/basic` | 1348 passed, 6 skipped, 5 failed: `test_router_route.py` (3) and `test_managed_workflow_tools.py` (2), the same 5 failing on 0fc6c51 (before the voice library), from the mixed environment, not this change |

The iPhone and Apple Watch side is item [1061](1061_iphone_and_watch_voice_library.md).

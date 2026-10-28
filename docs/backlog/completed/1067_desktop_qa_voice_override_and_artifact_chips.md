# 1067: Desktop QA 2026-10-28: the chosen voice is used, answers show no bookkeeping chips

**Status**: completed in 0.16.3 (branch `fix/desktop-qa-1`; released by `release.yml` workflow_dispatch from main).
**Cross-package**: AbstractRuntime 0862 (`abstractruntime/docs/backlog/planned/0862_replay_view_message_artifacts_exclude_bookkeeping.md`:
the view lists the run's offloaded bookkeeping as message artifacts); AbstractVoice `docs/api.md` (the plugin's
`voice` field: "base voice/profile id or cloned voice id").
**Scope**: the desktop app only (`web/`, `phone/` and `watch/` are other tracks).

## (a) Read aloud ignored the voice chosen in Settings

**Symptom.** Settings → Voice output: local override `qwen3-tts` / `Qwen/Qwen3-TTS-12Hz-0.6B-Base` / the clone
"hal9000-qwen2". Replies were read by Supertonic (the gateway default). AbstractCode web, with a clone, worked.

**Cause.** `AssistantController._sync_gateway_voice_defaults` always set `current_tts_voice_mode = "profile"`,
so the clone id Settings saves as `options.voice` travelled as the request's `profile`. The gateway passes a
profile to the engine as a preset; Qwen3-TTS refuses a Base (cloning) checkpoint as a preset before any audio,
and the voice manager's pre-audio "unpinned retry" then re-ran the stream with no pins: the gateway default voice,
silently. AbstractCode web sends a clone as `voice` (ui-kit `voice_settings.tsx`), which is why it worked.

**Fix.** `options.voice` travels as `voice` (the gateway resolves it as a stored clone or an engine profile),
an explicit `options.profile` as `profile`. When the unpinned retry does substitute the default voice, the
palette says so (`GatewayVoiceManager.on_speech_notice` -> warning banner) instead of only `warnings.warn`.

**Evidence** (scratch gateway, AbstractGateway 0.17.0 + AbstractVoice 0.19.2, the operator's override copied,
real Qwen3-TTS weights): with the released code the stream request carried `profile=<clone>` and answered
`error: Qwen3-TTS model type 'base' is a cloning checkpoint…`, then an unpinned request (gateway default);
with the fix the request carried `voice=<clone>` and the audio events report `provider=qwen3-tts`,
`model=Qwen/Qwen3-TTS-12Hz-0.6B-Base`, `voice=<clone>`, done metrics `engine=clone`, first audio 1.8 s.
Tests: `test_settings_clone_voice_travels_as_voice_not_profile`, `test_settings_explicit_profile_still_travels_as_profile`,
`test_unpinned_retry_tells_the_user_the_chosen_voice_was_not_used` (fail on the released code).

## (b) Two raw-id chips under an automation answer, "artifact not found"

**What they were.** Not attachments: the runtime's size offloads of the run's own bookkeeping. `7c8efef…` is the
agent's system prompt (text, 4.3 KB, tag `node_trace_offload`, owned by a child run, referenced under
`output.scratchpad.node_traces…_provider_request.payload.messages[0].content`); `f738932…` is the step list
(JSON, 145 KB, `run_output_offload`, path `output.scratchpad.steps`). Both exist in the gateway's artifact store.
The replay view's final message lists every `$artifact` under the run output in `artifact_ids`, so the palette made
them chips labelled with their ids. The first one could not open: the gateway serves an artifact through the run
that owns it (`_assert_artifact_visible_to_run`), and the chip asked through the root run.

**Fix.** `replay_view._media_meta` attaches only what a person can use: a ref the view does not list (no path, no
owning run) or one under the run's bookkeeping (`scratchpad`, `node_traces`, `trace`, `_`-prefixed fields) is left
out, and each kept ref carries its owning `run_id` (the download route then asks the right run). Chip labels never
show an id: file name, else "Image" / "Audio" / "Document" / "Attachment" with the size when known.
The runtime side (the view should not list bookkeeping as message artifacts; one ref missing from
`view.artifacts`) is AbstractRuntime 0862.

**Evidence.** The real run's ledgers folded with `abstractruntime.replay.replay` and projected by the fixed
`ViewProjector`: no chip (released code: two, `7c8efef…`, `f738932…`). Tests: `tests/basic/test_replay_view_artifact_chips.py`.

## (f) "Already connected to … as admin; kept that sign-in."

The hand-over notice repeated the connection status shown at the top right. A kept sign-in now raises no notice;
a replaced sign-in still says who is signed in and who was signed out.

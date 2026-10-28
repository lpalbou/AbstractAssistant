# 1076: Desktop Settings: no section claims empty height; choosing a voice plays a sample; message stamps in the kit's words

**Status**: in progress, PAUSED 2026-10-28 by the lead (operator reprioritization) · branch `feat/settings-tools-watch`
(draft PR "WIP (paused): Settings vertical space, voice select-to-play, watch run feedback"). Code and tests done for
all three parts; NOT yet done: adversarial review, CI, merge. No version bump (the lead sequences the release).
**Found by**: operator QA 2026-10-28 (Settings screenshot): "a huge loss of vertical space after 'Voice output (TTS)'
which pushes everything down; fix for all tabs"; voice select-to-play like the kit's picker; lead: footer stamp parity
with AbstractUIC panel-chat `formatMessageStamp`.

## 1. Vertical space (all tabs)

Cause: `ui/settings/route_editor.py` `RouteOverrideEditor`: the route list (left) is fixed to the height of its ten
routes (~370 px); the form column (right, a QVBoxLayout) had no trailing stretch. On a route whose form is shorter than
the list (Voice output, Voice input, every media route) Qt gave the surplus to the column's labels: title 53 px for
16 px of text, help 53 px for 13 px, state, feedback (measured offscreen). Fix: `right.addStretch(1)`.
Every other tab was measured the same way (each widget of every vertical column against its height-for-width): no
other section claimed empty height. Test: `tests/basic/test_settings_pages.py::test_no_settings_section_claims_empty_height`
(every tab, every route; RED on main: "models/output.voice: QLabel 'Voice output (TTS)': 53px for 16px").
Evidence: `untracked/release-closing/design/settings/settings-<tab>-before-{light,dark}.png` (+ `-full-` page grabs).

## 2. Voice select-to-play

`VoiceSample` in route_editor.py (kit `chooseSample`/`toggleSample`): `voice_combo.activated` (a person's choice only)
plays `VOICE_SAMPLE_TEXT` through `voice_manager.speak` after the 200 ms debounce, once the choice is saved (the
controller pushes it to the voice manager, so the sample is the chosen voice); play/stop toggle beside the list;
a newer choice stops the older sample (`stop_speaking`) and drops its late end; never over a reply being spoken;
stops on route change or when the page hides. `GatewayVoiceManager.speak(..., on_failure=, on_notice=)` routes that
speak's failure/notice to the caller instead of the chat window's banner.
Tests: `tests/basic/test_settings_voice_sample.py` (7), `tests/basic/test_voice_failure_visibility.py` (+2);
mutation-checked (activated hook, abort, reply guard, stale-run guard: each RED).

## 3. Message stamp

`app._format_message_timestamp(raw, now=None)` = kit `formatMessageStamp`. Tests: `tests/basic/test_message_timestamp.py`
(7; the old function fails 5).

## Next steps

1. Screenshots `-after-` (run `untracked/release-closing/design/settings/shoot.py <worktree> after`).
2. Adversarial review (fresh opus reviewer, read-only, given the diff); fix confirmed findings.
3. Mark ready, `gh pr checks --watch`, merge on all-pass, pull main, move this item to completed with the PR link.

# 0850 — Transcript refresh cost, and the follow-ups left by the clickable-links wave

**Status**: planned · **Priority**: normal · **Created**: 2026-09-18
**Package**: abstractassistant · **Wave**: 0845–0850 (2026-09-17 prompt-cache / gateway-stall investigation)

## Why

The 2026-09-17 wave shipped clickable file/URL links in answers, a file chip under the
answer, a safe click policy, correct per-tool identity, and a managed-workflow revision
gate. Two adversarial passes cleared the security-relevant findings, and three items were
consciously left for later rather than rushed in at the end of the wave.

## 1. `refresh_history` rebuilds every message card on every run event

`refresh_history` deletes and rebuilds **all** `MessageCard`s, and it is called on every
SSE/run event — so during a streaming reply the whole transcript is rebuilt repeatedly.
That was already true before the wave; the wave added per-assistant-card work to it:
`mentioned_local_files` (a `scandir` of the parent when a spaced path must be
disambiguated, plus `exists` per candidate under safe roots), `os.path.getsize` for the chip
caption, and, for a mentioned image, a `QImageReader` header read (the decode itself is now
refused above 40 MPix, on the GUI thread).

Detection is cheap on its own (≈0.11 ms for a benign message, ≈2 ms across 100 messages);
the cost is the rebuild-everything pattern meeting per-card filesystem work.

**In scope**: update cards in place (or diff by message key) instead of rebuilding the
transcript; move chip resolution (stat/size/thumbnail) off the GUI thread; cache the
per-message link/chip analysis keyed by `(message_key, content hash)` so a rebuild is not a
re-analysis. **Acceptance**: streaming a long reply into a 100-message session does no
per-event filesystem work for messages whose content did not change, and the event handler
stays under a frame budget.

## 2. Spoken replies mangle file paths

`core/speech_text.py::speech_plain_text` strips underscores from paths, so a real answer is
read aloud as "macbookprocamera/capture2026…". Now that paths are first-class in answers
(link + chip), this is the surface a voice user gets instead.

**In scope**: read a path as its filename plus a short location ("clip dot m p 4, in
Pictures"), or say "the file" and let the chip carry the detail; never read raw markup.
**Acceptance**: the reported answer, spoken, names the file in a way a listener can act on.

## 3. Link-detection edges left open

- `unfence_lone_targets` turns a fenced block holding nothing but one local path into inline
  code so it can link (models answer "where is it?" that way — observed in the operator's
  own session). Existence is not required for an unspaced fenced path, so a documentation
  example path also unfences into a (dead) link. Decide: require existence for the fenced
  form too, or keep it and accept dead links in docs-style content.
- Tool-call identity falls back to `(run, step, index)` for ledgers written before
  `runtime_call_id` existed; on a re-attach replay of such a run the adapter's guard (which
  keys on the unique id only) can list a tool result twice. All 20,919 calls on disk today
  carry `runtime_call_id`, so this is unreachable now — revisit only if old ledgers must
  replay cleanly.

## 4. Known coupling to note, not to fix

The revision gate means an app build older than a workflow revision defers to the stored
workflow instead of downgrading it — which is the point — but it also means such a build
never gets the newer router definition. Packaged builds must be rebuilt to pick up workflow
changes; the revision number is what makes that safe rather than a publish war.

## Receipts

- `abstractassistant/core/link_targets.py`, `utils/markdown_renderer.py`, `app.py`
  (2026-09-17, uncommitted at time of writing).
- Tests: `tests/basic/test_message_links.py`, `test_tool_call_identity.py`,
  `test_managed_workflow_revision.py`, `test_suite_cannot_reach_a_real_gateway.py`.
- Adversarial passes: 70-case detection corpus (70/70), click-policy attack round
  (one blocker found and fixed: a `%00` in a `file://` href aborted the app).

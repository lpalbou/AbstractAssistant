# Proposed: Interrupted turns are invisible to the model (abstractruntime contract)

## Metadata
- Created: 2026-09-07
- Status: Proposed
- Completed: N/A
- Owning package: **abstractruntime** (this client cannot fix it; see "Why not client-side")

## ADR status
- Governing ADRs: [ADR 0001](../../adr/0001_gateway_native_assistant_v2.md)
- ADR impact: None to the gateway boundary. This is the durable-session replay contract
  (`durable-sessions` v1), not the assistant's own surface.

## The incident

Session `sess_7a24b7fc12be402899ece560b34b25ee`:

1. 23:36 the operator asks (in French) for an hourly recurring measurement task. The run works
   through 7 cycles and 6 `execute_command` calls, then parks on a tool approval that never
   reached the client, and is cancelled at 23:54 with **no written answer**.
2. 00:33 the operator asks "i am unsure if you managed to carry out my request, please confirm."
3. The assistant answers: *"I don't have the earlier request in this chat, so I can't confirm
   whether it was completed or retry it."*

The operator could SEE the earlier request on screen. The assistant could not. Worse, the run had
in fact **succeeded**: `~/bin/mesure-systeme.sh`, a loaded LaunchAgent
`com.albou.mesure-systeme`, and `~/mesure.tsv` with rows an hour apart (23:38:08, 00:37:51). The
true answer was "yes, it is done and already collecting".

## Mechanism

`abstractruntime/src/abstractruntime/session_history.py`, `session_chat_messages()` — two
independent filters, both of which the interrupted turn trips:

```python
158:  if status != "completed":     # cancelled / failed run -> turn skipped whole
164:  if not prompt or not answer:  # answerless turn        -> turn skipped whole
```

Called by `abstractgateway/.../hosts/bundle_host.py::_seed_session_history`, which seeds a new
run's context from prior **completed** root runs.

The module's own docstring flags this as open, not settled:

> Only COMPLETED root runs contribute, and only when both a user prompt and an assistant answer
> could be extracted (a failed run never spoke — its half-turn is invisible to replay; **revisit
> if reviewers rule otherwise**).

and at the filter itself: *"contract question (a), conservative"*.

## Evidence

- **Ground truth.** Ledger of the second run's agent subrun `b1f9fb4c`, first `llm_call` effect:
  `messages` = **1 entry** (the current prompt only). `"récurrente"` / `"espace disque"` appear
  **0 times**. A healthy 10-turn session in the same store gives **9** messages at the same point,
  with an explicit `#TRUNCATION` note — so the replay path itself works.
- **Controlled live experiment** (scratch session `sess_probe_1788734416`, three real runs):
  turn A completed with codeword `ZARQUON7734`, turn B **cancelled** with codeword `BANANA9911`,
  turn C asked to list every codeword. It answered `ZARQUON7734` only; seeded `context.messages`
  = 2 (turn A alone); `BANANA9911` appeared 0 times in the prompt.
- **Filters bind independently** (in-memory, against the live module): `completed+answer` -> 2
  messages; `cancelled+no answer` -> 0; `completed+no answer` -> 0; `cancelled+partial answer`
  -> 0. **Relaxing only one fixes nothing.**
- **Natural replication**: the two other cancelled-first sessions in the store
  (`sess_e5c34d87…`, `sess_3e76e804…`) both show turn 2 receiving 1 message.
- **Blast radius**: of 200 recent root runs, **26 (13%)** are non-completed, spread over
  **25 of 104 sessions**. Every one is a turn the user can read and the model cannot.

## Proposed fix (abstractruntime)

Preserve the deliberate strict-alternation invariant (line 91, "dangling user messages are
provider-hostile") by synthesizing the missing half rather than emitting a bare user message:

```python
if not answer:
    answer = f"[This turn was interrupted (status: {status}) and produced no answer.]"
```

and let non-`completed` statuses through to that branch. Validated against the real incident turn:
**0 -> 2 messages**, French prompt restored.

Their contract test `test_session_chat_messages_skips_incomplete_internal_and_child_runs`
encodes today's behaviour and would need updating in the same change — which is precisely why
this is filed rather than patched.

## Why not client-side

The client sends **no** conversation history at all, for any run: `gateway_worker.py:1131` and
`cli.py:110` call `build_run_input_data` with no `messages=` and no `use_context=`, and
`run_input.py:144` then forces `messages_list = []`. History is server-owned by deliberate
decision (`run_input.py:124-128`). Passing the local cache's copy instead would work — the cache
does hold the French prompt — but it makes the thin client an authority on transcript truth and
reverses that decision. Not recommended.

## Not proven

- Whether `status != "completed"` matters on its own in production: every real case found is
  cancelled **and** answerless, so the two always co-occur. The separation is white-box only.
- `failed` runs were exercised in memory but not against the live gateway; they hit the same
  status filter.

## Related

- The client-side half of this incident IS fixed here: a pending approval on an agent SUBRUN was
  suppressed on reattach (`ui/gateway_worker.py::_suppress_resolved_waits_for_attach`), which is
  why the run parked for 16 minutes in the first place. See the 2026-09-07 entries in
  `CLAUDE.md`.
- A run parked on the user now keeps a persistent notice and a tray badge, so silence like this
  is visible even when a dialog never arrives.

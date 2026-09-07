# Proposed: Token usage is zeroed upstream (abstractcore), and router calls are never counted

## Metadata
- Created: 2026-09-07
- Status: Proposed
- Completed: N/A
- Owning packages: **abstractcore** (defect A) and **abstractruntime** (defect C)

## ADR status
- Governing ADRs: [ADR 0001](../../adr/0001_gateway_native_assistant_v2.md)
- ADR impact: None. Reporting only; no boundary or contract between client and gateway changes.

## Complaint

"the metadata shown for AI answers is often wrong" — a footer reading
`input : 0 tk | output : 0 tk | tools : 0 | files : 0 | 9.4s` on an answer that plainly cost
tokens.

## Defect A — usage normalization reads one dialect only (abstractcore)

`abstractcore/abstractcore/providers/openai_compatible_provider.py:372-373`, in
`_build_usage_dict` (`:362-391`):

```python
"input_tokens":  usage.get("prompt_tokens", 0),
"output_tokens": usage.get("completion_tokens", 0),
"total_tokens":  usage.get("total_tokens", 0),
```

It builds a fresh dict reading **only** Chat-Completions names. A server that answers in the
Responses dialect (`input_tokens` / `output_tokens`) therefore has both halves zeroed, while
`total_tokens` — the one key both dialects share — survives. That is the self-contradictory
`{"input_tokens": 0, "output_tokens": 0, "total_tokens": 4157}` seen in the run store.

**Proven live**, one HTTP call to the airelay proxy at `127.0.0.1:8317/v1/chat/completions`:

```
envelope keys : ['choices', 'created', 'id', 'model', 'object', 'usage']     <- Chat Completions
usage keys    : ['attribution', 'input_tokens', 'input_tokens_details',
                 'output_tokens', 'output_tokens_details', 'total_tokens']    <- Responses
usage         : {"input_tokens": 18, "output_tokens": 5, "total_tokens": 23}
prompt_tokens / completion_tokens present: False / False
```

Nothing downstream repairs it — the runtime copies verbatim
(`abstractruntime/.../integrations/abstractcore/llm_client.py:5808`).

### Measured blast radius

80 completed root runs / 43 sessions / **625 completed `llm_call` ledger records** / 6 providers:

| provider | records | in/out correct | **in=0, out=0, total>0** | raw_response holds truth |
|---|---|---|---|---|
| mlx | 260 | 258 | 0 | n/a |
| **endpoint:airelay** | **203** | **0** | **201 (100%)** | **201/201** |
| lmstudio | 60 | 59 | 0 | 59 |
| huggingface | 49 | 44 | 0 | 37 |
| endpoint:m4-max | 33 | 33 | 0 | 33 |
| `route_call` (structured) | 20 | — | — | usage is `null` (defect C) |

**38 of 80 root runs (47.5%) display zeros. All 38 are airelay; all 42 others are exact.**
Magnitudes hidden: `2e7680f2` shows 0/0, truth **108,146 / 4,866**; `ee66d859` shows 0/0, truth
**591,265 / 7,186**.

**The discriminator is the server's key shape, not the provider class.** `endpoint:m4-max` goes
through the same `openai_compatible_provider` and is 100% correct, because its server speaks
Chat-Completions. Not a regression: the block is unchanged since `a94ec2d` (2026-07-10). Streaming
is ruled out as a cause — `stream_options: {"include_usage": true}` is set (`:1093-1094`,
`:1618-1619`) and streamed runs do receive usage.

### Proposed fix

Widen `_build_usage_dict`'s **inputs** to accept `input_tokens` / `output_tokens` as fallbacks,
keeping all five output keys. The 5-key output is an asserted contract
(`abstractcore/tests/providers/test_streamed_usage_accounting.py:98`;
`abstractcore/server/app.py:9910-9916` is intolerant on read), so **widen inputs, never narrow
outputs**. Simulated over all 625 records: **201 repairs, 0 regressions**.

Related, same package: `abstractcore/server/app.py:2769-2775` makes abstractcore emit the very
Responses shape it cannot consume — a proxy relaying that output reproduces this bug exactly.

## Defect C — the router's tokens are never recorded (abstractruntime)

**22 of 22 `route_call` records carry `usage: null`** and no `raw_response`, on every provider:
the structured-output path hardcodes it (`abstractruntime/.../llm_client.py:5768-5777`). Every
run therefore undercounts by its routing call. Small, but systematic and provider-independent.

## Not affected

- **Billing**: `abstractruntime/.../storage/sqlite.py:1144-1148` reads only `total_tokens`, which
  survives. Only the input/output split goes dark.
- **Duration**: median error **3 ms** across 86 runs; 70 within 200 ms.
- **Files**: derived from `tool_call_details` and *omitted* rather than faked when details are
  absent — honest as designed.
- The 5 huggingface records with no usage carry `finish_reason: "error"` — genuinely nothing to
  report.

## Done in this client instead (2026-09-07)

- The footer no longer prints `input : 0 tk | output : 0 tk` when the split is unavailable; it
  shows `total : 4,157 tk`, the number we actually have. Zero is a claim, and a false one.
- Stored stats are re-derived on seeding and replaced only when the fresh figures are richer, so
  legacy rows folded from the root run alone (no tokens, `tools : 0`) heal instead of staying
  wrong forever.

**Deliberately NOT done**: preferring `raw_response.usage` in this client when the normalized dict
is internally inconsistent. It scores 625/625 on today's corpus and its detector is perfectly
precise (201/201 airelay), but it is contingent — 295 records carry no `raw_response` at all, so
it would fail silently for any future provider that omits it and speaks Responses. A stopgap, not
a fix.

## Not proven

- Only one Responses-shaped server exists in this store; behaviour against other Responses-style
  proxies is inferred from key names, not measured.
- 3 of 96 cached messages on `session_memory_*` (attachment-upload) runs show small token counts
  the current bundle does not contain. Unattributed.
- The current-client airelay evidence rests on run `ab52d4b7` (workflow `0.0.3`); no new run was
  started for the audit.

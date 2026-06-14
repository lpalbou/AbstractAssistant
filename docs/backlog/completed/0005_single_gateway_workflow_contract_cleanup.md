# Completed: Single gateway workflow contract cleanup

## Metadata
- Created: 2026-06-14
- Status: Completed
- Completed: 2026-06-14

## ADR status
- Governing ADRs: [ADR 0001](../../adr/0001_gateway_native_assistant_v2.md)
- ADR impact: Enforced and tightened the accepted assistant boundary.

## Context

The v2 shell had improved visually, but it still carried hybrid runtime behavior and dead code from
earlier iterations:

- catalog workflow launch;
- hidden workflow selection state;
- direct sandbox chat;
- client-side direct media workers;
- compatibility logic around non-canonical assistant workflows.

That contradicted the intended gateway-first boundary and made the tray product harder to trust.

## Completed work

- Collapsed the runtime contract to one canonical workflow path through the gateway tenant catalog.
- Made `abstractassistant-orchestrator` the managed assistant workflow that the client reconciles
  and runs.
- Removed active direct-chat and direct-media execution from the v2 tray path and CLI path.
- Removed hidden mode/workflow selection state from the primary v2 shell.
- Tightened tests around catalog-only workflow launch metadata.
- Rewrote ADR 0001 and related docs to ban private/direct fallback authority.

## Validation

- `python -m py_compile abstractassistantv2/app.py abstractassistantv2/controller.py abstractassistantv2/gateway.py abstractassistantv2/preferences.py tests/basic/test_assistant_v2.py`
- `python -m pytest tests/basic/test_assistant_v2.py tests/basic/test_gateway_run_input.py tests/basic/test_gateway_events.py tests/basic/test_gateway_client_methods.py tests/basic/test_cli_gateway_mode.py -q`

## Follow-up still tracked elsewhere

- Production macOS UX polish remains in [0004](../planned/0004_production_ux_and_catalog_default_hardening.md).
- Broader rollout and legacy-path de-emphasis remain in [0002](../planned/0002_gateway_native_assistant_v2_rollout.md).

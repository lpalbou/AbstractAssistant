# ADR 0001: Canonical Gateway Workflow Assistant

Status: Accepted.

## Context

AbstractAssistant drifted into a hybrid runtime shape while the framework moved to a gateway-first
control plane. The desktop shell had started to mix:

- published gateway workflows;
- private bundle discovery;
- direct gateway sandbox chat;
- client-side direct media execution paths;
- hidden routing heuristics in the tray shell.

That split authority across the desktop client and the gateway. It also created visible product
problems: users could not reliably tell what was answering, why tools were or were not available,
or whether the assistant was following the gateway defaults they had configured.

## Decision

AbstractAssistant v2 has exactly one runtime execution path:

- every tray turn and CLI turn runs through one published assistant workflow in the gateway tenant
  catalog;
- the canonical workflow is the managed `abstractassistant-orchestrator` bundle implementing the
  `abstractassistant.agent.v1` interface;
- the desktop client may reconcile, publish, and promote that workflow when it is absent or stale,
  but it must still execute only through the catalog workflow, not through alternate runtime paths;
- gateway capability-default routes remain the source of truth for provider, model, voice, image,
  video, sound, and music defaults;
- the workflow consumes those gateway defaults and performs routing inside the gateway/runtime
  boundary;
- the desktop client does not negotiate session prompt-cache hints or other model-specific runtime
  accelerators on the workflow's behalf;
- the desktop client owns only local UX state, local mic capture, local playback, artifact
  download/open, and per-device tool gating preferences.

The assistant must not:

- fall back to private bundle execution when the catalog workflow is missing;
- fall back to direct sandbox chat when the workflow path is unavailable;
- bypass the workflow with client-side direct image, video, music, or sound execution;
- silently compensate for missing gateway control-plane surfaces by inventing alternate local
  routing behavior.

If the gateway cannot expose the required assistant workflow or the required capability surfaces,
the client fails closed with an explicit user-visible error.

## Consequences

### Positive

- The assistant has one understandable mental model.
- Gateway is the single authority for durable execution, tools, defaults, and artifacts.
- Tool availability and multimodal behavior stop depending on hidden client-side route changes.
- The tray UI can stay small because it no longer needs to surface execution-path choice.

### Negative

- The assistant now depends on the gateway exposing the workflow authoring/catalog surfaces needed
  to bootstrap the canonical workflow.
- Broken or incomplete gateway deployments fail closed instead of degrading into a best-effort
  local alternative.
- Media generation requests pay the workflow orchestration hop even when a direct route might have
  been simpler to wire client-side.

### Neutral

- The desktop host is Qt-based.

## Enforcement

- `abstractassistantv2/` is the only valid extension point for new desktop-shell work.
- `abstractassistantv2/app.py`, `abstractassistantv2/controller.py`, `abstractassistantv2/gateway.py`,
  `abstractassistant/cli.py`, and `abstractassistant/ui/gateway_worker.py` must not introduce
  alternate runtime execution paths.
- The desktop client must not inject workflow-specific prompt-cache runtime hints before starting a
  run.
- `GatewayWorker` must require catalog metadata (`bundle_id`, `bundle_version`, `registry_scope`)
  and reject non-catalog workflow launches.
- The tray shell must not expose workflow-mode or execution-path selectors as part of the primary
  user path.
- Settings may edit gateway capability-default routes, but they must not create a second local
  provider/model routing policy.
- Any future proposal to reintroduce direct client execution or fallback workflow discovery must
  update this ADR first.

## Validation

- `python -m pytest tests/basic tests/integration -q`
- Targeted validation that the tray shell and CLI start runs only with tenant-catalog workflow
  metadata.
- Targeted validation that obsolete direct/sandbox/private assistant paths are absent from the v2
  execution flow.
- Live gateway smoke:
  - tool-bearing prompt uses the assistant workflow and tools;
  - media-bearing prompt runs through the assistant workflow and returns artifacts;
  - missing workflow/catalog surfaces fail with an explicit blocked state.

## Backlog Links

- [../backlog/planned/0002_gateway_native_assistant_v2_rollout.md](../backlog/planned/0002_gateway_native_assistant_v2_rollout.md)
- [../backlog/planned/0004_production_ux_and_catalog_default_hardening.md](../backlog/planned/0004_production_ux_and_catalog_default_hardening.md)
- [../backlog/completed/0005_single_gateway_workflow_contract_cleanup.md](../backlog/completed/0005_single_gateway_workflow_contract_cleanup.md)

## Related

- [../architecture.md](../architecture.md)
- [../../../docs/adr/0032-package-dependency-boundaries-and-gateway-first-apps.md](../../../docs/adr/0032-package-dependency-boundaries-and-gateway-first-apps.md)
- [../../../docs/adr/0035-capability-routing-defaults.md](../../../docs/adr/0035-capability-routing-defaults.md)

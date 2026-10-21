# 1050 — Any runnable workflow for automations

> Package: abstractassistant
> Type: task
> Created: 2026-10-19
> Status: Completed
> Completed: 2026-10-19
> Priority: P1
> Labels: iphone, automation, usability

## Current code reality

NewAutomationScreen requests only bundles declaring abstractassistant.agent.v1, so runnable
non-Assistant workflows never reach its picker. Required custom inputs only trigger an error
pointing to the console. The creation action inherits ordinary Form-row styling.

## Scope and expected outcome

Use the existing Gateway bundle catalog without an Assistant interface filter, retaining
Gateway run eligibility and excluding archived/deprecated entries. Load selected workflow
input descriptors and allow configuring custom required/default inputs on the phone. Preserve
exact bundle version/entrypoint and typed inputs in automation targets. Keep Assistant gateway
default behavior available. Give Create/Retry a mint primary-action treatment. No Gateway,
Framework or Watch changes. No real automation creation for validation.

## Validation and ADR state

Transport tests for unfiltered discovery and eligibility, typed custom input validation and
version-pinned creation payload. Native creation flow for a non-Assistant workflow, visual
inspection and normal developer install alongside1049. Keep retry/context guards. Existing
thin-client/schema-authority architecture applies; no new ADR required. No commit/push.

## Completion report — 2026-10-19

NewAutomationScreen now requests the Gateway bundle catalog without an Assistant-interface
filter. WorkflowChoice excludes archived/deprecated/explicitly non-runnable entries, while
Gateway visibility remains authoritative. Explicit workflow selection fetches its versioned
input schema and exposes typed custom inputs, defaults, required values and enum choices.
Structured/artifact values accept JSON. Workflows without a prompt show their actual inputs
instead of ignored task instructions. Creation preserves exact bundle version/entrypoint and
JSON value types. Schema responses are scoped to selection/account and input values join the
retry fingerprint. Create/Retry and Run now use mint primary-action styling.

Package260/260 and final native3/3 pass; the earlier native22/22 includes initial custom
workflow coverage as well. Tests cover unfiltered discovery, Assistant-filter retention,
required/custom/nullable/artifact inputs, typed POST targets, non-Assistant UI creation,
existing Assistant creation and history budgets. Final native screenshots inspected; evidence:
../evidence/1050/README.md. README, architecture, native changelog and llms-full updated.
Normal development-signed0.6.22(33) signature-verified, installed and launched on the iPhone.

Original planned/1050_any_runnable_automation_workflow.md moved here with the same ID/intent.
The existing schema-authoritative thin-client architecture applies; no new ADR or follow-up
needed. Full schema validation remains on the Gateway; physical user validation is pending.
All automated creation checks used demo, with no real scheduled automation created or run.
No Framework/Watch edits, Git commit/push or Store upload.

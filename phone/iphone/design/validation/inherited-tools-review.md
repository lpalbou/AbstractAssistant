# Inherited Assistant tools — 0.6.5 (13)

## Reproduced discrepancy

The Tools UI displayed gateway discovery and approval defaults, but inherited Assistant
sends omitted the enabled tool list. The desktop client always materializes that list.

In the shipped `abstractassistant-orchestrator@0.0.0.flow`, a connected Tools pin has
no default. Omission becomes an empty child allowlist and zero tool declarations in
the Agent's LLM effect. The shipped basic-agent differs: it supplies its own default
tools. The regression therefore depends on the selected workflow, rather than every
gateway run being tool-free. The remote account's selected flow was not inspected.

## Correction

Every Assistant start overload uses the same path: resolve the account workflow,
fetch current discovery, and supply enabled names in both `input_data.tools` and
`_runtime.allowed_tools`. Inherited approval policy stays absent; this does not grant
blanket Auto approval. Inheritance means catalog-enabled tools, matching desktop
selection, rather than a workflow author's overridable Tools-pin defaults.

Explicit Off remains excluded, including an empty deny-all selection. Disabled or
removed tools are filtered from explicit allowlists and named approval policies.
Discovery failure, including an HTTP-200 catalog error, cannot start an apparently
tool-free run. Attachments travel with the selection. Existing gateway endpoints
are sufficient; no production gateway change or release is required by this fix.

## Evidence

- 96 Swift package tests pass (68 phone and 28 inherited client tests). Tests cover
  all three start overloads, inherited names without invented approval overrides,
  fresh host restrictions, explicit deny-all, attachments and failed discovery.
- Five gateway tests pass through real ASGI `/runs/start`, shipped workflow routing,
  compilation and Agent subruns. The LLM transport alone is stubbed. Assertions
  inspect actual parameter schemas, child allowlists and a real approval wait.
  They reproduce omission producing zero schemas in the orchestrator, resolved
  inventory producing `read_file`/`list_files` schemas, empty selection disabling
  tools, and basic-agent retaining its own defaults.
- Gateway test commit: `49e76c36`,
  `tests/test_iphone_assistant_tool_declarations.py`.
- Three native Tools UI checks pass with zero failures, skips or runtime warnings:
  `build/UITests-1792299236102856000.xcresult`. They cover Settings entry,
  category/search/disabled states and per-conversation Save.
- Logs: `/tmp/phone-inherited-tools-tests.log`,
  `/tmp/gateway-phone-tool-declarations-tests.log`,
  `/tmp/phone-inherited-tools-native.log`.

The gateway test uses its `.venv` with the workspace agent/runtime/core sources on
`PYTHONPATH`; installed lower-layer copies were stale. External provider serialization
and a live remote model are outside this regression's evidence.

## Independent review

- Execution Mode: parent implementation; user-requested Astra 6 medium reasoning.
- Planned Reviewer Set / Actual Reviewer Set: `/root/tools_astra` (`gpt-6-astra`, medium).
- Subagents Used: one for this correction.
- Fallback Reason / Contract Degradation: none.
- Observed Evidence: desktop/phone/runtime source, shipped bundles, transport tests
  and real workflow execution tests.
- Inference Or Unverified Claims: the remote selected workflow and external model
  request have not been inspected.
- Reviewer Verdicts: Approved for transport/runtime scope; parent separately reviewed
  the integration tests written by Astra.
- Open Questions Or Missing Evidence: live remote model behavior and external
  provider serialization have not been exercised by this validation.
- Residual Risk: custom workflows can impose their own non-overridable tool restrictions.
- Final Verdict: Approved for inspected transport/runtime and native UI behavior;
  physical delivery remains a separate installation result.

## Physical delivery

Strict code-signature verification passed. CoreDevice installed 0.6.5 (13),
independently reported that exact installed version, and successfully launched it.
Binary SHA-256: `8779b8b431c224233e1b5d7af5834954348d608022c20844908f2282a5f68013`.
The first device build yielded to a Watch build; the successful retry ran after
Xcode became available. No app or user data was removed. Build log:
`/tmp/phone-inherited-tools-device.log`.

# 1050 — Runnable automation workflows and primary actions

Package260/260 passes:179 AssistantKit and81 GatewayClient. New transport coverage confirms
unfiltered GET /bundles discovery, exact entrypoint/version preservation, exclusion of
archived/deprecated/non-runnable records, typed required/default input handling, zero/false,
enums, structured/artifact/nullable values and a version-pinned creation POST payload.
Chat’s explicit Assistant-interface discovery still retains executable_for.

Native final3/3 passes, with no failed/skipped tests or runtime warnings. The non-Assistant
CSV workflow exposes Source URL, integer Row limit and Include header controls, replaces
unused task instructions with its actual inputs, and creates successfully in demo. Existing
Assistant title/task creation and custom/inherited growing-history budgets also pass.
The earlier22-test orb/voice/native pass additionally included the initial workflow creation.
All creation requests use MockGatewayClient; no real scheduled routine was created or run.

non-assistant-inputs.png and mint-create.png are final native screenshots, visually inspected.
Simple required/type checks happen locally; the Gateway remains authoritative for advanced
JSON-schema constraints. Structured values can be configured as JSON. Gateway default still
selects the Assistant interface default; explicit selections use the runnable catalog.

Normal development build0.6.22(33) was signature-verified, installed and launched on the
physical iPhone for user validation. No Git commit/push, Store upload or Framework/Watch changes.

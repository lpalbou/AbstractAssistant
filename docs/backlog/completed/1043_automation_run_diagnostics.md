# 1043 — Automation run explanations and live results

> Package: abstractassistant
> Type: task
> Created: 2026-10-19
> Status: Completed
> Completed: 2026-10-19
> Priority: P1
> Labels: iphone, reliability

## Current code reality

AutomationDetailScreen renders status-only cards, drops occurrence.failure, duplicates the latest row, and requires a manual pull after Run now. The existing Gateway occurrence contract already returns failure.message/reason_code/attempts and run IDs.

## Scope and expected outcome

Decode failure and attempt metadata; provide dated, tappable run cards and a run details sheet with explanation, task, trigger and existing ledger/activity. Refresh only while this screen is visible. Investigate the existing failed remote occurrences read-only using the saved device sign-in. No new automation execution or framework/server changes.

## Validation

Regression tests for actual failure JSON, empty answers and partial metadata; native UI checks for multiple runs, details, timestamps and refresh failures. Preserve evidence without email contents or credentials.

## ADR state

Existing thin-client architecture and ADR0002/0003 delivery boundaries apply; no new durable architecture decision.

## Completion report — 2026-10-19

Delivered LastOccurrence failure/attempt/task decoding, recorded-error explanations, dated
multi-run cards and a details sheet with times, attempts, task/trigger, support ID and expandable
existing activity. The active screen refreshes every5 seconds without starting a new task.
Latest results are not repeated, blank answers get an explicit explanation and active runs
block another Run now. Provider401 remains distinct from phone authentication expiry.

Read-only physical investigation identified two actual AIRelays401 failures after3 attempts;
no email was sent and no framework/server configuration was changed. That historical provider error alone does not establish that the saved key is wrong; later
fresh generation checks succeeded. The UI change does not claim to repair remote routing.
Package250, contracts14, targeted native4 and physical read-only1 all pass; screenshots inspected.
Public troubleshooting guide and iPhone changelog updated. Evidence: ../evidence/1043/README.md.
No new ADR: existing thin-client and human-gated delivery boundaries apply. Original planned
path moved to completed with the same filename. No unrelated follow-up added.

## Post-completion hardening — 2026-10-19

Full hosted feature checks passed in the80/81 run; the unrelated orb timing assertion is
tracked by1045. Retry runs are now grouped and refreshed by occurrence index even when the
attempt run ID changes. If a row has left the20-run history page, terminal root state still
updates its detail snapshot. The modal uses explicit Refresh details; automatic polling belongs
to the automation’s main page. New identity regression makes package total251.

## Additional read-only provider verification

While the126.1 candidate runs, inspect the saved AIRelays profile's public credential-presence
flag and its Console model-discovery test. This reads model inventory with the server-side key;
it does not revise a profile, launch the automation or send mail. Discovery success alone is
not proof that chat/completions accepts the credential, since some services expose a public
model list. Inspect only routing IDs/provider/model fields of email automation targets, never
prompts or secret configuration. Product-source candidate remains pinned to d2aec7b.

## Bounded generation-route comparison

The saved profile is enabled, api_key_set=true and model discovery succeeds. The email
routine's latest occurrence is still failed4, pinned to orchestrator0.0.0/d5d4e5a1; available
Assistant entries are0.0.15. Compare one synthetic text request per version, with tools=[]
and _runtime.allowed_tools=[] and a fresh no-history session. Do not run the email task or
change any definition. Archive only these diagnostic sessions once terminal. A successful
model listing alone must not be represented as proof of valid chat authentication.

## Current-state investigation outcome

Stored AIRelays profile and model-discovery check succeed. Fresh tool-free runs on both the
routine's0.0.0 agent and the available0.0.15 agent returnedOK, then their diagnostic sessions
were archived. Provider401 is confirmed for the two historical occurrences but not reproduced
in these fresh runs. The original email automation itself was not run; its definition, pin,
schedule, tool choices and provider configuration are unchanged. Do not claim its end-to-end
email task passed or recommend credential replacement from the historical failures alone.
Additional test-only probes are not part of the immutable126.1 app candidate on d2aec7b.

## User-directed continuation — recorded routing comparison

The user confirms Console discovery succeeds and requests investigation of both a reported404
and the historical AIRelays401. Compare the saved automation target and failed occurrence
ledgers against fresh successful runs using sanitized provider/model/endpoint metadata only.
Normal chat admission and Runtime occurrence dispatch are distinct paths; do not assume they
carry identical routing or credentials. No Framework source changes. No further Git commits or
pushes until the user validates the app; install a normal development build on the physical
iPhone for that validation. The existing App Store upload remains at its human gate.

A second bounded verification uses a new manual-only diagnostic automation with the original
target's provider/model pins, an OK prompt, tools=[] and _runtime.allowed_tools=[], one
attempt, no history, and console-only notifications. It cannot read or send email. Start one
occurrence, record status/error, then archive that diagnostic controller. The user's original
automation remains unchanged. All probes stay test-only and uncommitted.

## Final current-state evidence — 2026-10-19

The VPS About endpoint reports Framework0.11.14, Gateway0.15.11, Runtime0.10.6 and
Core2.26.3. Recorded routing inspection traversed20 root/child runs, with only whitelisted
provider/model/endpoint/status/error metadata exported. The two failed occurrences and all
their retained retry roots fail at the initial model step with401; no404 was present in
this bounded inspected history. The error path lacks successful provider-response metadata,
so the actual historical outgoing Authorization state cannot be reconstructed from it.
Do not claim a bad current key or a proven historical cache defect.

Two synthetic manual-only automations on the ORIGINAL target0.0.0/d5d4e5a1 completed:
757c85a8-e769-5b38-969e-9ff6b4b4b242 returnedOK with no tools;
9f959f13-f299-5f44-ae4e-cf155e1792b3 returnedOK after one completed list_email_accounts
tool batch. Only account metadata was read, no message bodies or external sends. Console-only
notifications, one attempt, no history; archive requested for the first diagnostic and verified
for the second. The original automation remains active at revision3, last occurrence4 failed
at11:38UTC, next scheduled2026-10-20T05:56:44.933235UTC. Its task was not re-executed
and no provider profile, default or original automation definition was modified.

Refined phone explanations distinguish a provider404 from401 without guessing that a Gateway
route404 is a model failure; earlier failures explicitly describe a recorded run. Package252
passed; native current-routing diagnostics3 passed. Normal development-signed0.6.22(30)
was verified, installed and launched on the physical iPhone, separate from the Store identity.
The same combined CI candidate126.1 previously passed81/81 and remains at the human upload
gate. All continuation source/docs/evidence changes remain uncommitted and unpushed pending
user validation. Framework source unchanged. Evidence: ../evidence/1043/README.md.

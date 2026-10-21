# 1043 — Automation diagnostics evidence

Read-only physical iPhone test `testInspectFailedAutomationsReadOnly` passed on 2026-10-19.
The saved Keychain sign-in stayed on the device. No automation command, email send, workflow
upload, server configuration change or generation was performed. Only bounded failure metadata
was exported; no message subjects/bodies, credentials or provider request payloads.

Two occurrence rows and their root runs agree: indices3 and4 each failed after3 attempts with
`OpenAI-compatible server API error (401): Missing or invalid AIRelays bearer token.`
This is provider authentication, not the iPhone Gateway session. A UI change cannot repair the
remote provider credential; the administrator must correct it. Framework/server files were not
modified. The fixture and unit regression use the actual wire shape and error sentence.

Validation: package250/250, release contracts14/14, targeted native UI4/4 and physical
read-only1/1. Screenshots history.png, failed-run.png and updates.png were inspected.
The physical iPhone reports `beta_update_app_available=true` for `itms-beta://` without
opening it or installing anything. The final device rebuild used clean isolated iPhone
DerivedData after an older standalone Swift module shadowed the current package framework.
No Watch build/cache/source was changed.

A first native UI assertion expected separate accessibility children for labeled metadata;
the controls combine labels and values. Stable metadata identifiers corrected that assertion;
the final four native tests have zero failures/skips. Both actual failure metadata and the
explanatory UI now agree. The gateway provider credential remains an administrator action.

## Current provider and workflow checks

At13:41–13:47 UTC the gateway-owned AIRelays connection was enabled with a stored key;
its model-discovery test succeeded. The email automation is pinned to orchestrator0.0.0,
flowd5d4e5a1, with latest occurrence4 still failed. Available app workflows are0.0.15.

Two bounded synthetic "OK" requests then completed successfully, one on0.0.0 and one on
0.0.15 using the same agent entrypoint, explicit empty tools and runtime allowlists, no
history and separate fresh sessions. Both returnedOK and neither produced401. Both diagnostic
sessions were archived only after reaching terminal state. No email task was executed and
no automation definition/provider configuration was changed. Each device verification passed.

This narrows the finding: the two recorded occurrence failures were provider401 responses;
they are not reproduced by fresh tool-free runs under current gateway configuration. It does
not prove the original automation controller or email tools now succeed, and does not justify
blind credential replacement or automatic workflow migration. The historical0.0.0 pin is
preserved. Evidence: provider-connection.json and workflow-route-check.json with run IDs.

## Current VPS routing versus historical failures

remote-versions.json records the live public About response. recorded-routing.json contains
only sanitized routing/status/error metadata from20 inspected runs; no credentials, prompts
or email contents. No404 was present in this bounded history; retained failed attempts show401
at the first model call. The old requests' outgoing bearer state is not recoverable from these
records, so the exact historical cause remains unproven.

controller-route-check.json: a manual-only clone of the original target returnedOK, with no
tools and console-only notification; archive command accepted. controller-tool-check.json:
a second clone completed one real list_email_accounts tool batch and returnedOK, and its
archived status was verified. It read only account metadata, no email bodies, and could not
send. Original automation still active revision3, latestfailed4 at11:38UTC; definition untouched.
Current authentication and automation dispatch work; do not recommend replacing a valid key
or claim the original mailbox task passed. phone-validation-install.json records the normal
developer app installed/opened for user validation. Package252 passes. No new Git commit/push.

If a NEW original occurrence fails, retain its ID/time and compare the INITIAL model step
against these successful diagnostics. On a VPS using the documented user systemd service,
`journalctl --user -u abstractgateway.service --utc --since '2026-10-19 05:50:00' --until '2026-10-19 11:45:00'`
can recover the historical process context locally. Inspect provider connection/default changes
and401/404 entries without exporting credentials. Verify the execution account's text default
uses the saved `endpoint:airelays` connection, not an unrelated generic provider connection.
A Gateway restart can discard stale in-memory provider clients after a connection change;
`systemctl --user restart abstractgateway.service` applies only if that is the actual service.
No restart is warranted from the old failed cards alone while all current route checks pass.

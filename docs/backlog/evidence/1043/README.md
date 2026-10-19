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

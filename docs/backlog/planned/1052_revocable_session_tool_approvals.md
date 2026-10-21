# 1052 — Revocable session tool approvals

> Package: abstractassistant
> Type: bug
> Created: 2026-10-20
> Status: Planned
> Completed: N/A
> Priority: P1
> Labels: iphone, tools, approval

## Current code reality

Watch keeps client-owned sessionTrust separate from Ask/Auto tool choices and exposes an
orange shield to revoke it. iPhone approveAll instead replaces enabled modes with Auto,
persists those choices plus a .grant name list, and has no revoke shortcut. Original modes
cannot be recovered from old records: that list includes both original Auto and Approve.

## Scope and expected outcome

Keep new temporary approvals separate from tool choices. An orange shield appears only for
this account/responder/session's grants; one tap makes Approve tools ask again from the next
unanswered call, including during a run. Auto/Off choices remain unchanged. Preserve gateway
approval requirements on future runs. Clear/recheck grants on edits and asynchronous context
changes. Old ambiguous records get an explicit one-time review without guessing which Auto
settings were deliberate. No Gateway/Framework/Watch edits, Git commit/push or Store upload.

## Validation and ADR state

Package tests cover mixed modes, running-run revocation, persistence/scoping, inventory-await
revocation races, failed approval and legacy review. Native regression checks the optional
orange shield, direct revoke and Tools visibility; inspect screenshots and install a normal
development build. Existing thin-client exact-key approval contract applies; no new ADR.

## Validation update — 2026-10-20

All 266 package tests passed, including mixed Auto/Approve/Off settings, revocation during
an active run, an inventory-await revocation race, persistence/reopen and legacy review.
The native shield/revoke regression passed twice; screenshots of the toolbar and Tools
card were inspected. Normal build36 installed and launched; build37 delivery is pending.
Account setup additionally configured the iPhone as laurent and the physical Watch with the
admin token on the requested local gateway. The iPhone authenticated from-device; Watch
saved gateway and token were verified without exporting the credential to reports. The
installed Watch ignores the local --user hint; server token identity is admin. Temporary
credential payloads were cleared. Evidence:../evidence/1052/validation.json.
The independent voice-following regression remains tracked in1051.

## Delivery boundary — 2026-10-20

The user's requested redeploy is build0.6.22(36), installed and launched normally with the
shield feature; the phone's authenticated local-gateway account is laurent. Watch preferences
retain the requested gateway and admin token, verified privately; temporary payloads were
cleared on both devices and Mac. Later build37 (frame coalescing plus minor Ask again styling
and stale-sheet disabling) remains uninstalled because the Watch priority guard interrupted
its build. Keep this item Planned until that final source state is validated/delivered.
No Git commit/push or Store upload.

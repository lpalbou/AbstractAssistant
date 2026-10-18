# Direct tool overrides and visible Tools — 0.6.7 (15)

## Behavior and scope

The main conversation header includes an always-visible Tools icon beside the responder
selector. It remains reachable during agent work. Every available Off/Auto/Approve control
is interactive, including when defaults are inherited. Choosing a mode creates an override
without first finding or changing a defaults switch.

The editor offers **This conversation** and **iPhone defaults**. Explicit conversation
choices take precedence over this phone's defaults for the connected gateway, account and
responder; otherwise gateway defaults apply. New conversations inherit the saved phone
defaults. Empty explicit selections remain deny-all. Each scope keeps its own unsaved draft;
Save commits both edited scopes and Close discards them. Defaults switches reset inheritance.

Preferences can be edited during work and apply to the next message. They do not resend
or mutate an active request. Availability is still checked at send time; unavailable tools
cannot be enabled by an app or conversation override. No gateway update or new endpoint is
required.

## Evidence

- **134 Swift tests pass** (94 AssistantKit and 40 gateway client). Four new tests exercise
  precedence, reset and deny-all behavior, persistence across store recreation, isolation by
  gateway/account/responder, forwarding the effective selection in the next actual client
  request, and editing during work without resending the active request.
- **Five native UI tests pass**, zero runtime warnings:
  `build/UITests-1792302753769330000.xcresult`. They cover direct edits without unlocking,
  inheritance in a new chat, conversation precedence, retained drafts across scope changes,
  saving, reachability during work, gateway-disabled tools, category/search controls and
  the Settings entry point.
- **Two final focused native reruns pass**, zero runtime warnings:
  `build/UITests-1792302924150661000.xcresult`. These verify the final compact search help
  and switching between inherited values and retained overrides. The Settings row uses
  the same tested preference-editing availability guard.
- Directly inspected native renders: [header](../screenshots/tools-header.png),
  [scope editor](../screenshots/tools-scope-editor.png),
  [iPhone override](../screenshots/tools-iphone-defaults.png), and
  [conversation override](../screenshots/tools-conversation-override.png).

## UX review

Execution: implementation plus native interaction tests and direct artifact inspection by
one reviewer; no independent persona swarm was requested for this change. The main action
is recognizable and reachable without opening a menu. The editor names both scopes and
explains that changes apply to the next message. Inheritance no longer disables available
controls. Searching keeps Close and Save reachable. The visual pass shortened search help
to keep the result and its mode control visible above the keyboard.

**Approved for the inspected layouts and interaction flows.** Larger Dynamic Type sizes,
hardware keyboard navigation and other display sizes were not visually inspected. Native
cases use reproducible demo data; they do not claim a new production provider run.

## Device delivery

The guarded build used one low-priority iPhone job and isolated DerivedData. Strict
code-signature verification passed. Installed and launched on the connected iPhone;
app inventory confirms **0.6.7 (15)**. Executable SHA-256:
`7878277ee61a64972d19a2aaf14cb498d27d637a7ff38af1faeb22c648012927`.

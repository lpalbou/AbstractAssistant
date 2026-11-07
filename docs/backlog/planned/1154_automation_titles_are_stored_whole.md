# 1154 — Automation titles are stored whole; the 120-character default title is a display form, never what is saved

> Package: AbstractAssistant (web `web/src/lib/automations.ts:82-95`; Apple `Models.swift:633,867`), with the same rule for every client that creates automations
> Type: defect (root ADR 0054: stored text is never truncated)
> Status: planned
> Created: 2026-11-08 (found by the adversarial review of the Observer Board redesign; 2 of 8 live automations carry a cut title)
> Priority: P1
> Labels: automations, truncation, web, apple

## Summary

When a person creates an automation without naming it, the web app stores the task's first line cut at 120 characters
with "…" as the automation's title (`automations.ts:85`: `line.slice(0, 119) + "…"`; `:94-95` keeps the cut name in
step with the task); the Apple apps do the same (`Models.swift:633, 867`). The gateway then stores that cut text as the
automation's name, Observer and the consoles show it cut, and nothing can recover the whole first line. Root ADR 0054
(operator 2026-11-08): "never truncate summaries or titles, especially not in what is stored; store the verbatim and let
the consumer apps decide what they show or not."

## Scope

- The default title saved to the gateway is the task's whole first line (or the whole task when it has one line);
  the 120-character form, if a screen needs it, is derived at render time with the kit's "…" reveal (ADR 0053 §2).
- Renaming logic (`:90-95`) follows the whole line, not a 120-character prefix.
- Apple apps: the same change in `Models.swift` (the Watch/iPhone agent's lane this week; this item is the shared
  contract, root 1151 the shared-component follow-up).
- Existing cut titles: a one-time repair where the task still holds the first line (name == first 119 chars + "…"),
  or left as they are with the task shown whole; decide with the operator.
- Tests: creating an automation from a 300-character task stores a 300-character title; the web list folds it with a
  reveal; a mutation restoring the slice turns the test red.

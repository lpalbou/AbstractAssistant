# Conversation controls: decision and adversarial review

Verified 2026-10-18 against the checked-out gateway/runtime sources and built iPhone preview
0.6.0 (8). Saved app baseline: 762b4a9. Gateway implementation: 3769d62e.

## Execution and reviewers

- Execution mode: parent implementation with two requested adversarial agents.
- Planned and actual set: everyday UX (`iphone_adversary`) and technical behavior
  (`iphone_behavior_adversary`). No extra agents; no agora participation.
- Each reviewer authored an isolated part during implementation. The other reviewer and
  parent reviewed those parts independently; self-inspection counts only as visual QA.
- No fallback in reviewer count or scope. Watch development remained independent.

## Decision question and current reality

How can a conversation's Off/Auto/Approve choices be enforced consistently for Assistant
runs and entity turns, without a second approval execution system?

Assistant runs already accept runtime allowlists and named approval policy. Legacy hosted
entity chat executes its own granted tools without a durable approval continuation. Durable
entity visits already provide run stamps, single-writer home leases and persisted waits.
Automation history's runtime default is 50,000 tokens; omission inherits it.

## Alternatives and comparison

| Option | Ownership | Migration cost | User effect | Operations | Reversibility / gaps |
| --- | --- | --- | --- | --- | --- |
| Phone-only settings | Client | Small | Useful for Assistant, false enforcement for entities | Small | Reversible UI; rejected because entity approval has no consumer |
| Extend hosted chat with callbacks/jobs | Gateway chat host | Medium | Can add approval with low initial UI disruption | Another continuation/execution lifecycle | Requires its own restart and pending-job design |
| Extend durable visits | Runtime wait plus gateway entity executor | Medium | Same Off/Auto/Approve interaction for both responders | Existing leases/stamps/wait recovery | Chosen; new routes require gateway update |

The chosen boundary keeps authorization and execution on the server. The phone sends only
an exact wait key and boolean decision. An approval executes through the stamped entity's
existing handler, rechecks its home grant and records execution intent before side effects.
Interrupted uncertain outcomes refuse blind replay. Unknown tool names in explicit policies
are denied; explicit empty lists remain deny-all.

Names written to durable state use one versioned `entity_session_tools` namespace with
principal owner and per-name modes. Legacy visits without it keep their behavior. Older
server builds must not resume managed visits without these gates; close them before a
server downgrade. The app capability check blocks unsupported explicit settings.

## Findings incorporated

- Global Stop visibility replaced by reading-message ownership.
- Streaming partial metrics are not cached as final; unknown metrics are not repeatedly fetched.
- Existing visit endpoints enforce the same managed-session owner boundary; trusted janitor
  ticks remain internal. Bare occupied-status metadata remains available to visible entities.
- Quiet reconnect, terminal/missing-visit eviction, safe history switching and lost-response
  recovery prevent stale reading, stuck visits and automatic duplicate sends.
- Defaults stay visible; toggling inheritance shows actual defaults without destroying custom
  drafts. Known default-Off tools retain Off when customization begins.
- Actual gateway defaults populate the history placeholder; blank remains inheritance.

## Verdict and remaining evidence

Recommend with reservations for developer preview. The source, transport, durable execution,
UI and rendered-screen evidence are recorded in ../../docs/validation.md. Deployment requires
the gateway update; the simulator's demo does not establish live provider quality or physical
microphone sensitivity. The existing automation Form runtime warning remains documented.

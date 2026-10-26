# Proposed: Shared Swift between the two Apple apps: one gateway client module, an honest credential file

> Created: 2026-10-26
> Type: architecture
> Priority: P2
> Labels: apple, watch, iphone, sign-in, security

## Metadata
- Created: 2026-10-26 (rewritten the same day after an adversarial review and the one-project merge)
- Status: Proposed
- Completed: N/A
- Owning packages: abstractassistant (iPhone app, Watch app, their packages)
- Origin: the operator's fusion decision ([ADR 0004](../../adr/0004_notes_inside_the_assistant_abstractnote_stays_a_service.md)); the operator's rule: every step makes the code cleaner, simpler, more robust, more secure and more efficient, never more complex

## ADR status
- Governing ADRs: [ADR 0005](../../adr/0005_one_apple_project.md), [ADR 0004](../../adr/0004_notes_inside_the_assistant_abstractnote_stays_a_service.md)
- ADR impact: May revise ADR 0005 (the static-framework workaround for the duplicate module name is part of its decision; this item removes the need for it)

## Summary
Finish what ADR 0005 started: the iPhone app and the Watch app build from one gateway client
module instead of two packages that export the same module name (worked around today by
compiling the watch's package as a static framework), and the shared credential store in
`AssistantPush` becomes an honest Class C file instead of a file encrypted with a key kept
beside it. Measured by lines deleted in this repository, not by a new abstraction.

## Why
- `phone/iphone/project.yml:197-210` compiles `watch/apple/Packages/AbstractGatewayClient` as a
  static framework because the iPhone's `AssistantKit` package exports a module with the same
  name; SwiftPM refuses two packages with one target name in one graph. One module name is the
  real fix, and the workaround is deleted.
- The two clients still carry two transports: between the watch's and the iPhone's packages,
  `GatewayClient.swift`, `Models.swift` and the mock differ by hundreds of lines each; only
  `Auth.swift` is byte-identical (`md5` equal on 2026-10-26). A fix to sign-in or to an error
  message lands twice or once.
- `AssistantPush/Sources/AssistantPush/SealedFile.swift` seals the sign-in with ChaChaPoly under
  a key kept in `sealing.key` in the same folder, with the same protection: whoever reads one
  file reads both, so the encryption adds code and no protection. No file is excluded from
  backup (`isExcludedFromBackup` appears nowhere), and app-group containers are backed up. The
  kept sign-ins (`KeptSignIns`, `gateway.kept`) still hold credentials in UserDefaults, which
  the same package says it never does.

## Scope
1. **Credential file, honest.** Delete `sealing.key` and the ChaChaPoly step; write the sign-in
   as plain JSON with Data Protection `completeUntilFirstUserAuthentication` (the class the
   extensions can read after first unlock), exclude it from backup, delete it at sign-out, as
   AbstractNote's `CredentialFile.swift` does. Move the kept sign-ins into the same file (or stop
   keeping credentials and keep only the account name). Stop calling it "sealed" in docs and
   code. About three files.
2. **One module name.** Rename one of the two `AbstractGatewayClient` modules, make the watch's
   package an ordinary local-path dependency of the project, delete the static-framework target.
   Local-path packages are how every package is consumed already (`project.yml:25-29`).
3. **One shared package plus an additive phone module, in one dedicated pass.** The target:
   `AbstractGatewayClient` (the watch's package, the original name) holds everything the watch,
   the iPhone and the Mac app share: the transport, the wire models, the sign-in, the mock. What
   only the phone needs stays in `AssistantKit`, which already sits on top of the client, and
   depends on the shared package. `PhoneGatewayClient` is the phone's diverged copy of the client
   (measured 2026-10-26: transport 686 differing lines, models 721, mock 861, events 101, session
   files 144; nine phone-only files, three watch-only; only `Auth.swift` identical) and is deleted
   at the end of the pass, not folded in file by file over months. Both apps are clients of the
   same gateway, so one transport and one set of wire types is the honest shape; the mock keeps
   one sample world with per-app launch data.

## Non-goals
- No consumer outside this repository: AbstractNote's watch is retired under ADR 0004, and its
  files are forks, not copies (its `SNAPSHOT.json` records the Listener as replaced and the
  sign-in page as parameterized). No package in `abstractuic`, no versioned tags.
- No shared screens or view models beyond what `AssistantPush` already renders; no protocol or
  abstraction added for its own sake.
- No migration from the Keychain: the bundle ids changed in ADR 0005, so the old items are
  unreachable; people sign in once.

## Current code reality
- `phone/iphone/project.yml`: one project (ADR 0005); packages `AssistantKit` and
  `AssistantPush` under `phone/iphone/Packages`, the watch's `AbstractGatewayClient` under
  `watch/apple/Packages`, compiled as a static framework (`:197-210`).
- `AssistantPush`: the sign-in file in the app group `group.ai.abstractframework.assistant`
  (`SealedFile.swift`), push registration, the iPhone-to-watch sign-in handoff, push rendering;
  used by both apps and both notification extensions.
- The complication is in the app group (`project.yml`) and can read the credential although it
  never calls the gateway: the file's scope is the group, not the target.
- Watch: `SavedSignIn` loads from the shared file (`watch/apple/Sources/App/Settings/SignInView.swift`),
  `KeptSignIns` still in UserDefaults (`:139-142`).

## Ruling (operator, 2026-10-26, clarified the same day)
The framework's no-keychain rule is about its Python packages, which must run on Linux, macOS and
Windows alike; the Apple apps may use the Keychain, "the best simple secure practice". The store
shipped is a plain file under the device's Data Protection (class "complete until first user
authentication", so the notification extensions can read it after the first unlock), owner-only,
excluded from backups, deleted at sign-out, no encryption of our own: one store for the watch, the
iPhone and the Mac app to come, testable with `swift test` on every platform. What a Keychain item
in a shared access group would add over it: "this device only" semantics and per-target scoping
(the complication can read the file although it never calls the gateway). Switch only if one of
those is wanted; the file is not a rule.

## Progress — 2026-10-26
Steps 1 and 2 shipped on main (commit 24f47c9): `ProtectedFile` replaces the sealed pair (plain
JSON under Data Protection, 0600, excluded from backups, the 0.15 pair moved at first read; package
tests cover the attributes and the move), the watch's kept sign-ins moved from UserDefaults into
`kept-signins.json` beside it, the iPhone's module is `PhoneGatewayClient` and the watch package
is a plain dependency of the one project (the static-framework target is gone; ADR 0005 amended).
Step 3 shipped the same day as one dedicated pass (an Opus worker on branch
`phone-client-convergence`, applied to main): `PhoneGatewayClient` is gone, `AbstractGatewayClient`
holds every route and wire model either app uses (164 package tests), `AssistantKit` depends on it
(198 tests), `MockGatewayClient(world: .watch | .phone)` is one actor with one sample world per
app, and the two packages went from 10,653 to 8,673 lines of Swift. Both apps and all three
extensions build, the watch's Release build (broken on main by two debug-only types used outside
a debug guard) builds again, and no test that passed before fails. The twenty judgment calls (which
copy's behaviour won where the two differed) are in `untracked/convergence-log-2026-10-26.md` and
summarised in both changelogs. Not unified, on purpose: the two media models (`MediaItem` /
`SessionFile` and `PhoneArtifact` / `WorkspaceEntry`) and the two tool-choice representations,
each app's persona, and the phone's single read try. This item can be closed once the operator has
used both apps on the converged client for a few days.

## Promotion criteria
- Ruled on 2026-10-26 (above); promote when a session is free to take it.
- A count of lines in the two packages before the work, kept in this item, so the outcome is
  measurable.

## Validation ideas
- `SignInUITests` and the iPhone's sign-in tests run unchanged.
- A test proves the credential file carries the backup-exclusion attribute and the protection
  class, and that sign-out removes it and the kept sign-ins.
- The project builds and archives with the watch package as a plain dependency (the release
  workflow of ADR 0005).

## Guidance for future agents
Reject any step that adds an abstraction without deleting a copy. If a shared file needs a
third copy to compile somewhere, that somewhere is the problem.

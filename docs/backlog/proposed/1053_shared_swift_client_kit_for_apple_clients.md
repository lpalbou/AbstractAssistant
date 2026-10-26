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
3. **Converge file by file, only when touched.** `Auth.swift` (identical) moves into one package
   and the other depends on it. Transport, models and mocks converge only when a fix must land
   in both; no "shared kit" is built ahead of such a fix.

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

## Ruling (operator, 2026-10-26)
No OS keychain, anywhere: AbstractFramework stays OS-agnostic and its clients must behave the same
on every installation. A credential is a plain file in the app's own container, protected by the
operating system's at-rest encryption where one exists (Data Protection class "complete until
first user authentication" on Apple devices, so the notification extensions can read it after the
first unlock), owner-only permissions, excluded from backups, deleted at sign-out. No encryption
of our own on top: a key kept beside the data protects nothing and adds code. The cost accepted
with it: no "this device only" semantics beyond what backup exclusion gives, and the file is
readable by every target in the app group (the complication included).

## Expected outcomes
- One `AbstractGatewayClient` module, no static-framework target, fewer lines of Swift in this
  repository (measured here only).
- One credential file, plain, Class C, excluded from backup, holding the current and the kept
  sign-ins; no credential in UserDefaults.

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

# 1040 — iPhone restored image previews

> Package: abstractassistant
> Type: bug
> Created: 2026-10-18
> Status: Completed
> Completed: 2026-10-18
> Priority: P1
> Labels: iphone, images, lifecycle, regression

## Goal and current code reality

Generated images open full screen but can remain blank inline after app reload, displaying
“cancelled”. MessageArtifactView uses a row-scoped SwiftUI task. MessageMediaController.fetch
forwards that task’s cancellation to the actual download, while another consumer returns nil
when loading already contains the artifact. URLError.cancelled is shown as a failure. The
second consumer never retries when the first finishes. Opening the file does not decode its
inline thumbnail. Temporary previews are intentionally disposable; gateway artifacts remain
the source of truth and must be refetched after a cold start.

## Scope and acceptance

- [x] Cover overlapping/cancelled row requests against delayed transport.
- [x] Conversation owns shared in-flight downloads; row cancellation cannot strand previews.
- [x] Session/account reset cancels ownership and prevents late stale cache/presentation writes.
- [x] Opening an image restores its inline thumbnail; real failures offer an explicit retry.
- [x] Relaunch/reopen and preview-dismiss native journeys retain visible inline images.
- [x] Preserve bounded storage/audio behavior; inspect native renders and install normal iPhone.

## Boundaries and validation

Only iPhone code/tests/docs and this package backlog. No Watch, AbstractFramework/root or server
changes; no real media generation or user conversation mutations. ADR impact None: existing
gateway content route and disposable-cache architecture. Focused delayed-transport race tests,
reset/cache/error tests, native relaunch and navigation journeys, signed installation evidence.

## Completion report

Completed 2026-10-18. Original path `planned/1040_iphone_restored_image_previews.md`;
final path `completed/1040_iphone_restored_image_previews.md`.

MessageMediaController coalesces conversation-owned transfers; row cancellation cannot cancel
another consumer’s work or strand its thumbnail. It decodes images before releasing consumers,
refetches deleted temporary files, guards full-screen presentation against session changes,
suppresses lifecycle cancellation errors, and presents genuine-error retry controls. Ownership,
cache bounds, reset cleanup and audio request isolation remain intact. README/version,
architecture and validation docs updated. Scope stays entirely within the iPhone/package backlog.

**Seven native tests passed**, no runtime warnings, including delayed HTTP overlap/cancellation,
same-artifact session reset, failure/retry/purged-file recovery, existing storage/audio/reference
checks and a two-cold-launch preview/tab-navigation journey. Parent inspected both restored
inline-image screenshots. Normal **0.6.21 (29)** signed app with no test plugins installed on the
iPhone. Automatic launch denied because the phone is locked (SBMainWorkspace Locked); reopening
Assistant after unlocking uses the installed build. See [evidence](../evidence/1040/README.md) for
reproduction, iteration notes, results and installation records. Changes uncommitted; no new
commit was requested this turn.

Residual limits: tests use controlled HTTP and restored demo history; real user media were not
regenerated or mutated. Physical verification covers installation; launch requires an unlocked
phone. Existing disposable-cache limits remain; gateway files remain durable. No remaining code
blocker, additional follow-up or priority impact identified. ADR impact None: existing
authenticated gateway content routes and disposable-preview architecture.

## Documentation and delivery — 2026-10-19

User requested commit/push with coredoc. Public iPhone guidance describes shared image downloads,
retry and cold-restoration behavior; toolbar/file/share instructions match the three-island UI.
Native release history covers 0.6.19–0.6.21, linked from the root README, docs index and llms.txt.
Architecture retains its Mermaid diagram and supported behavior; historical endpoint/router
repair narratives and fixture-only instructions were removed from public guidance. Root
CHANGELOG links the iPhone release record. The LLM aggregate includes native release history and
was regenerated with the checked-in generator in the same pass. Documentation links (excluding
code examples), core-file/diagram presence, whitespace and aggregate freshness checks pass.

Native code remains exactly the version validated by the seven tests recorded above; no new
native build was needed for this documentation/checkpoint pass. Implementation-completion
uncommitted status above is historical; this pass commits and pushes the completed iPhone fix,
public docs and evidence. No Watch files, server changes or package publication.

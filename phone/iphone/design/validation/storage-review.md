# iPhone storage investigation — 0.6.4 (12)

## Physical measurements before cleanup

CoreDevice recursively listed the installed Assistant's complete accessible data
container while 0.6.3 (11) was installed. No user file contents were read.

| Area | Regular files | Logical bytes |
|---|---:|---:|
| Documents | 0 | 0 |
| tmp, including recordings/imports/previews | 0 | 0 |
| iOS SplashBoard snapshots | 4 | 16,646,240 |
| System rendering/loader caches | 5 | 270,096 |
| Preferences | 1 | 1,051 |
| Saved application state | 1 | 42 |
| **Total** | **11** | **16,917,429** |

Only one developer app was listed: `ai.abstractframework.assistant.iphone`.
This rules out visible duplicate Assistant development apps, but does not measure
OS-owned installation staging. The app bundle is separate from its data container.

The observed app data does not support retained-audio or attachment accumulation
as the cause of the earlier installation failure. POSIX 28 alone did not establish
which storage volume was exhausted. The earlier assertion that the iPhone was full
was unsupported. Successful 0.6.3 installation required no app or user-data deletion.

Raw measurements are local: `/tmp/iphone-assistant-storage-before.json`,
`/tmp/iphone-assistant-storage-confirmation.json`,
`/tmp/iphone-developer-apps-storage.json`. CoreDevice hardware details expose total
capacity but did not provide phone-wide free space through the inspected surface.
The subsequent on-phone filesystem audit measured **511,355,080,704 capacity bytes**
and **8,888,320,000 free bytes** (8.89 GB decimal). This is current free space;
it does not reconstruct conditions during the earlier failed installation.

## Corrected accumulation paths

- Attachment previews previously remained until conversation reset or controller
  destruction. Dismissal and replacement now remove the local operation directory;
  repeated previews retain at most one local copy.
- Capture/import/preview copies now have separate operation directories under
  `tmp/AbstractAssistant/{voice,imports,previews}`. Cancellation, completion and
  failed writes discard their own operation directory.
- Startup removes interrupted-operation leftovers from this namespace and strict
  UUID-named legacy temporary copies. Original files, Documents, credentials and
  gateway artifacts are outside cleanup scope.
- Creation/disposal reject root/category symlinks; startup removes dangling owned
  root links without following them into other files.

Spoken WAV replies are played from Data in memory. The transport uses an ephemeral
URLSession and does not persist a network disk cache. No local model is downloaded.
Those are source findings, consistent with the empty temporary directory observed.

## Validation and delivery

93 package tests pass (65 phone plus 28 inherited client tests), including owned
cleanup, preservation of originals, symlink boundaries and dangling-root recovery.
All 18 native controller tests pass, without failures, skips or runtime warnings:
`build/UITests-1792298849111576000.xcresult`. They cover repeated preview
replacement/dismissal, upload-copy disposal, recording cancellation and transcription
disposal. The guard allowed only an existing idle Watch UI-test process and monitored
Watch activity and memory pressure throughout; no Watch compilation was interrupted.

The signed 0.6.4 (12) build passed strict signature verification and was successfully
installed and launched. CoreDevice independently reported that installed version.
Binary SHA-256: `002cdb919863b927fbfabb3d8d3dd727ed8b6d35912f19bf95b877d9baeba1be`.
No app or original user files were removed. Build log:
`/tmp/phone-storage-device-build.log`; copied physical audit:
`/tmp/iphone-volume-storage-audit.json`.

The optional DEBUG launch argument `--storage-audit` writes only volume capacity/free
byte counts to `tmp/AbstractAssistant/storage-audit.json`. It does not include file
names, file contents, account data or credentials. It exists to measure the physical
phone's current filesystem, not infer historical disk state from an install error.

## Independent review

- Execution Mode: parent implementation and one independent adversarial reviewer.
- Planned Reviewer Set / Actual Reviewer Set: `/root/tool_contract_adversary`, covering
  correctness, ownership and user/operational claims.
- Subagents Used: one existing reviewer.
- Fallback Reason / Contract Degradation: none.
- Observed Evidence: raw device metadata, on-phone free-space audit, source diff,
  package tests, native tests and verified installed version.
- Inference Or Unverified Claims: no observed app-file pollution; earlier POSIX 28's
  affected volume and historical free space remain unknown.
- Reviewer Verdicts: combined source/package/native implementation Approved.
- Open Questions Or Missing Evidence: the historical install-error cause remains unknown.
- Residual Risk: iOS-owned staging and other apps are outside inspected app storage.
- Final Verdict: Approved for the inspected cleanup and installation scope.

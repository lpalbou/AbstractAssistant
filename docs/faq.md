# FAQ

See also:

- [getting-started.md](getting-started.md)
- [architecture.md](architecture.md)
- [troubleshooting.md](troubleshooting.md)

## What is AbstractAssistant?

It is a desktop assistant for AbstractGateway. It runs as a tray app with a compact top-right
palette and a matching CLI. The assistant is thin by design: the gateway owns workflows, defaults,
and durable execution.

## Does it run locally?

The desktop shell runs locally. Whether requests work offline depends on the gateway deployment and
its providers. A gateway backed by local providers can stay local; a gateway backed by cloud
providers still needs network access.

## Where do provider and model defaults live?

On the gateway side.

The assistant Settings window edits gateway capability-default routes. The desktop app only keeps
local UX preferences and session convenience state.

## Does the assistant still remember a local provider/model default?

No. Gateway defaults are authoritative. The assistant remembers local preferences, but the default
multimodal routing policy belongs to the gateway.

## Which workflow does the assistant use?

AbstractAssistant uses the published gateway workflow bundle `abstractassistant-orchestrator`. The
tray app and the CLI both run through that published catalog workflow.

## Can I choose a different workflow?

Not in the normal desktop path.

The assistant expects exactly one published assistant workflow from the gateway catalog. If that
workflow is missing or ambiguous, the app blocks and tells you to fix the gateway side.

## Why are some requests unavailable?

Image, video, sound, music, voice, and tool behavior depend on configured gateway routes and a
published assistant workflow. If those gateway surfaces are missing, the assistant asks you to fix
them in Settings or on the gateway instead of silently guessing.

## How does voice work?

The desktop app captures microphone audio locally and plays audio locally. STT and TTS execution go
through the gateway.

If the gateway does not advertise voice routes, the assistant disables the mic or auto-speak
controls.

## Where are downloads stored?

Downloaded artifacts are cached under `~/.abstractassistant/`.

## Why do I keep seeing tool approval prompts?

Because tool execution remains gateway-driven and explicit. When a workflow emits a tool-approval
wait, the assistant surfaces it and resumes the run only after your decision.

## Which auth model does the desktop app use?

The tray app supports both gateway bearer tokens and hosted gateway sessions. In Settings you
can either save a shared bearer token or exchange a gateway user token for an opaque gateway
session plus CSRF token. The CLI remains bearer-token oriented.

## Can I use it outside macOS?

macOS is the primary tray target. Linux and Windows may work, especially for the CLI, but they are
not yet validated to the same standard as the macOS tray path.

## How do I report a security issue?

Use the process in [../SECURITY.md](../SECURITY.md).

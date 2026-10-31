# 1057 — Gateway Apps access, 2026-10-31

The operator requested access to the existing web Assistant from the Gateway tray
and console. The web app existed, but neither catalog included it. The desktop
Assistant already owned the id `assistant`.

Gateway now registers `assistant-web` as **Assistant (web)**, with package
`@abstractframework/assistant`, port 3008, cookie prefix `abstractassistant` and the
existing managed Node app lifecycle. The tray opens it through the same one-time
handover as the console. The desktop entry is unchanged.

On the local Gateway, built and packed private preview 0.0.1, installed it under
the Gateway data directory, and enabled its managed server. A Vite preview had
occupied port 3008 without the mount identity header; replaced that preview with
the built server. Reloaded the Gateway through its graceful restart API after
checking zero active runs and zero in-flight ticks. The tray helper is ready.

Validation:

- Assistant frontend: 57 tests pass; TypeScript/Vite build and relative-URL check pass.
- Gateway catalog, routes, app manager, proxy and tray: 229 tests pass.
- Gateway first-run cards, process leftovers, pending upgrades and terminal
  interfaces: 103 tests pass, including the web/desktop distinction regression.
- Headless Chrome against the live Gateway: the console's **Open** button opens
  `/apps/assistant-web/` signed in; the tray's handover API opens the same path.
  Both mounted assets return 200, the app account request returns 200, app cookies
  stay under `/apps/assistant-web/`, and an existing conversation renders both
  request and response. No browser JavaScript errors.
- Managed app reports running, mounted, enabled, and source `gateway`.

No model request, approval decision or microphone recording was needed. This
does not complete phase 1's full conversation/voice proofs or publish the npm
package. The package remains private; registry installation is still pending.

# Troubleshooting

See also:

- [getting-started.md](getting-started.md)
- [faq.md](faq.md)
- [architecture.md](architecture.md)

## The tray starts, but I cannot run anything

Most often the gateway cannot expose the published `abstractassistant-orchestrator` workflow.

Check:

```bash
export ABSTRACTGATEWAY_FLOWS_DIR="$PWD/abstractgateway/flows/bundles"
abstractgateway serve --host 127.0.0.1 --port 8080
```

Then relaunch the assistant.

## The assistant says no workflow is available

The assistant reads the published `abstractassistant-orchestrator` workflow from the gateway
workflow catalog. If the app cannot resolve that workflow, verify:

- the gateway is reachable
- the gateway has loaded bundles
- your auth token is accepted by the gateway

## A request says a route is not configured

Open **Settings** and configure the matching gateway route. The assistant uses gateway capability
defaults for image, video, voice, sound, and music requests inside the published assistant
workflow.

## The mic button is disabled

The gateway is not advertising a working speech-input route, or local microphone capture is not
available.

On macOS, check:

1. System Settings
2. Privacy & Security
3. Microphone
4. Allow access for your Python or app-bundle launch target

## Auto-speak is disabled

Gateway voice output is not configured, or the desktop cannot play audio with an available local
player.

## The global hotkey does not work

The summon hotkey is optional and depends on platform support plus permissions. The tray icon still
works even if the hotkey path is unavailable.

Try:

- reopening Settings and saving the hotkey again
- granting accessibility/input-monitoring permissions if your platform requires them
- using the tray icon if the runtime does not allow global hooks

## I only see one provider or no expected models

Catalogs come from the gateway, not from the local desktop app.

Verify:

- `ABSTRACTGATEWAY_AUTH_TOKEN` matches the running gateway
- the gateway can reach the configured provider
- the provider is configured on the gateway side, not only on your desktop

## Artifact opening fails

The assistant downloads gateway artifacts locally before opening them. Check:

- the run still exists on the gateway
- the artifact id is valid for that run
- your local downloads directory under `~/.abstractassistant/` is writable

## The tray app cannot connect to the gateway

Check the configured URL and sign-in mode in **Settings** first.

For bearer-token setups, verify:

```bash
echo "$ABSTRACTGATEWAY_URL"
echo "$ABSTRACTGATEWAY_AUTH_TOKEN"
```

For hosted gateway-session setups, verify:

- the gateway user exists and its token is still valid
- the saved gateway session has not expired or been revoked
- re-running **Connect** in Settings succeeds

You can also override bearer-token connection settings on the command line:

```bash
assistant --gateway-url http://127.0.0.1:8080 --gateway-token "$ABSTRACTGATEWAY_AUTH_TOKEN"
```

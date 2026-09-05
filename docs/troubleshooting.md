# Troubleshooting

See also:

- [getting-started.md](getting-started.md)
- [settings.md](settings.md)
- [voice.md](voice.md)
- [faq.md](faq.md)

## The header orb is red or the title says "Reconnecting…"

The gateway is unreachable. Check the URL and sign-in in Settings → Connection (the status card
names the failure), then:

```bash
echo "$ABSTRACTGATEWAY_URL"
curl -s -H "Authorization: Bearer $ABSTRACTGATEWAY_AUTH_TOKEN" "$ABSTRACTGATEWAY_URL/api/gateway/me"
```

A run that was in progress keeps its busy state while the follower retries and continues when the
gateway is back.

## The palette says no workflow is available

The assistant needs the published `abstractassistant-orchestrator` workflow in the gateway's
tenant catalog. Verify the gateway is reachable, that it loaded its bundles
(`ABSTRACTGATEWAY_FLOWS_DIR`), and that your token is accepted. Then reopen Settings → Connection
and press Connect.

## A message shows "Not sent — …"

The gateway refused to start the run and the palette restored your message. The banner carries
the gateway's reason. The common cause is a workspace grant outside the gateway's policy:
open Settings → Workspace, compare your root and allowed folders with the policy card, and adjust
or reset them. See [settings.md](settings.md#workspace).

## An approval sheet never appears but the run is waiting

The sheet is modeless and may be behind other windows, or you deferred it with Esc. Show the
palette again (the question is re-asked), or click **Review** on the waiting step in the activity
card. The run log (list icon on the activity card) shows the pending wait.

## A tool is "Disabled on gateway"

The gateway has turned that tool off; the assistant cannot enable it. Ask the gateway operator.

## The microphone button is disabled

The gateway is not advertising a speech-input route, or local capture is unavailable. Install the
`voice` extra (`pip install "abstractassistant[voice]"`) and allow microphone access in macOS:
System Settings → Privacy & Security → Microphone → your Python or the app bundle. The button's
tooltip names the missing side.

## The voice conversation stops with "Microphone unavailable"

The recognizer could not open the input device. Check the macOS microphone permission above, that
an input device is selected in Sound settings, and that no other app holds the microphone
exclusively. Start the conversation again with ⌘⇧V.

## Replies are spoken but I hear nothing

Playback follows the Mac's default output. The notice shown when speech starts names the device
and the system volume; a headset or a muted or very low output is the usual cause. Open Sound
settings from Settings → Voice.

## A spoken reply fails with a banner

The banner names the cause (a rejected engine pin, a gateway timeout, unplayable audio). If you
pinned a voice engine in Settings → Models & reasoning, reset the voice route to the gateway
default and try again. In a conversation the loop resumes listening after a failed reply.

## Settings shows "Could not read the gateway workspace policy"

The gateway did not answer the workspace policy routes (older gateway or a permission problem).
Local workspace settings still save and are sent; the gateway applies its own policy at run start.

## The Models page shows no providers or models

Catalogs come from the gateway. Verify the token matches the running gateway, that the provider
is configured on the gateway side, and press Reload in the route editor.

## The global hotkey does not work

The summon hotkey depends on macOS Accessibility permission for the launching process. Grant it
in System Settings → Privacy & Security → Accessibility, save the shortcut again in Settings →
Window & shortcuts, or use the menu-bar icon.

## Artifact opening fails

The assistant downloads gateway artifacts before opening them. Check that the run still exists on
the gateway and that `~/.abstractassistant/downloads/` is writable.

## The bundled app looks unchanged after a source change

Source-run testing and `/Applications/AbstractAssistant.app` are separate targets. Rebuild with
`build-macos-app`, quit the older menu-bar process, and relaunch the app bundle.

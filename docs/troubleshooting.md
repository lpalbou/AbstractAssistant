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

Sending is blocked when the workflow chosen in Settings → Models → Workflow cannot run:

- **Gateway default → unavailable**: the gateway sets no default for `abstractassistant.agent.v1`
  and the built-in `abstractassistant-orchestrator` is not in your tenant catalog. Verify the
  gateway is reachable and your sign-in is accepted, then reopen Settings → Connection and press
  Connect so the app can publish its orchestrator; or ask the gateway operator to set a default.
- **The chosen workflow is not in the gateway catalog any more**: pick another one in
  Settings → Models → Workflow, or go back to Gateway default.

See [settings.md](settings.md#models--reasoning).

## Opening the Assistant from the gateway console does not sign it in

The banner names the cause:

- **expired or already used**: the sign-in works once, within two minutes. Click **Open** again.
- **only works on the gateway's own machine**: the hand-over is redeemed on the gateway's loopback
  address; on another Mac, connect in Settings → Connection.
- **needs a newer AbstractGateway**: the gateway does not offer the hand-over; connect in
  Settings → Connection.
- **the sign-in file was refused**: the path given to `--gateway-handover-file` was not a
  hand-over file written by the gateway. The file is left untouched.

If nothing happens at all, the Assistant was probably already running: quit it from the menu-bar
icon and click **Open** again. See [api.md](api.md#global-flags).

## `assistant run` says the gateway needs you to sign in

The gateway answered 401. Open the Assistant once from the gateway console, connect in
Settings → Connection (the CLI reuses that sign-in), or pass `--gateway-token`. See
[api.md](api.md#assistant-run---prompt-text).

## Replies do not stream

Check Settings → Models → **Stream replies**. **On — not supported by this gateway** means the
gateway does not advertise live replies, so nothing is requested and the chat shows one note. A
step that cannot stream (structured output, a remote model server, a provider that cannot stream
or report usage while streaming) is named in the status line and its answer appears when it is
finished. See [settings.md](settings.md#live-replies).

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

Playback uses the device chosen in Settings → Voice → Output device, or the Mac's default output
when that is `System default` or the chosen device is not connected. The notice shown when speech
starts names the device and the system volume; a headset or a muted or very low output is the
usual cause. Use **Test** next to Output device to check the device.

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
Appearance, or use the menu-bar icon.

## Artifact opening fails

The assistant downloads gateway artifacts before opening them. Check that the run still exists on
the gateway and that `~/.abstractassistant/downloads/` is writable.

## The bundled app looks unchanged after a source change

Source-run testing and `/Applications/AbstractAssistant.app` are separate targets. Rebuild with
`build-macos-app`, quit the older menu-bar process, and relaunch the app bundle.

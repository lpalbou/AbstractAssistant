# Runs, failures and app updates

## Understand an automation run

Open **Automations**, select a routine, then tap a run card. The latest run appears first;
the screen retains the latest 20 occurrences. Each card shows its state, local start time,
attempt count when recorded, and either its answer or an explanation.

**Automation run** shows the outcome, next step, start/finish times, attempts, recorded error,
task/trigger and expandable activity. **Support details** exposes the run ID and failure code
for an administrator. **Refresh details** retries a failed detail fetch without starting a task.
Missing activity or an unavailable explanation is stated explicitly; it is not evidence that the
run succeeded.

While the automation’s main page is open and the app is active, it checks the gateway every five seconds.
**Run now** first sends a request; the gateway then admits and executes the occurrence. Its state
and result update without pull-to-refresh. Run now is unavailable while an occurrence is active.
A **Needs you** result directs you to **Inbox** to answer a question or approve tools.
The run modal refreshes on opening and with **Refresh details**. The scheduled task continues on the gateway when the app closes.

A failed run and an unavailable connection are different problems:

- **The model provider rejected the gateway’s sign-in:** the phone reached the gateway, but
  the provider rejected its credential. Ask the gateway administrator to check that endpoint’s
  API credential. Changing phone tool permissions or signing in again on the phone does not
  repair the provider credential.
- **A service did not respond:** check gateway/provider connectivity, then review the recorded
  error before starting another run.
- **Provider request limit:** check quota or wait before trying again.
- **Please sign in again:** the gateway rejected this phone’s sign-in. Reconnect this iPhone.

Read the error before retrying a task that can make changes. Earlier tools might have completed
before a later step failed. Refreshing details only reads existing records.

## Find the installed version

Open the **Settings** wheel. **App → Version** shows the installed marketing version and build,
for example `0.6.22 (120.1)`. CI build numbers differ from local developer builds. The gateway and
desktop Python package have separate versions.

Open **Version & updates** for the installation channel, update controls and release history.
The channel uses Apple-verified app transaction information where available. If it cannot be
verified, the screen says so and offers the TestFlight and App Store instructions.

## Update a TestFlight copy

Choose **Check for updates in TestFlight**, select **AbstractAssistant**, and tap **Update** if a
newer build is available to your tester account. The button opens TestFlight; the iPhone app does
not query private App Store Connect credentials or claim that an uploaded build is available to you.

For automatic beta updates, open **TestFlight → AbstractAssistant → App Information → Automatic
Updates**. Enable it there. Apple owns this setting and installation; AbstractAssistant cannot read
or change the switch. See [Apple’s TestFlight instructions](https://testflight.apple.com/).

A new source commit is not an installed update. Our pipeline tests and archives the combined
phone/Watch candidate, then requires human approval before upload. Apple processing and tester
availability follow. See [testing and distribution](distribution.md).

## Update an App Store or development copy

For an App Store installation, **Check for updates in App Store** opens the app’s Apple-verified
listing when its app ID is available. Manage automatic updates under **iPhone Settings → Apps →
App Store → App Updates**. See [Apple’s update guide](https://support.apple.com/en-us/102629).

A development copy uses the [build guide](../BUILD.md) or an existing TestFlight invitation.
The app cannot install a replacement binary itself. **Release notes → iPhone version history**
opens the [native changelog](../CHANGELOG.md); it documents changes and is not an update-availability
service.

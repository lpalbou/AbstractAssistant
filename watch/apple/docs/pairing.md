# Pairing a physical Apple Watch for development (watchOS 27)

What it took to get the app onto a Series 11 on watchOS 27.0.1 from Xcode 27.1 on macOS 27.0.1,
on 2026-10-17, after three hours of a watch that "did not exist". The whole procedure is five
minutes once the order is right. Everything here was read in the Mac's unified log
(`/usr/bin/log stream --predicate 'process == "remotepairingd" OR process == "CoreDeviceService"'`;
the `log` word alone is a zsh builtin and prints nothing).

## How the Mac reaches a watch

A watch is never on the cable. Xcode reaches it two ways, and watchOS 26+ changed which one works:

1. **Through the iPhone (`companion_proxy`)** — the historical path. The Mac talks to the paired
   iPhone over USB and the phone relays to the watch. On watchOS 26+ `remotepairingd` logs
   `Device supports user-driven network pairing flows. Skipping companion proxy bootstrap pairing`
   and this path only *discovers* the watch; it no longer creates the developer pairing.
2. **Nearby pairing over Bluetooth/Wi-Fi** — the Mac beacons, the watch lists the Mac under its
   own Developer Mode setting, and the person confirms a PIN on both. This is the only path that
   creates the pairing on watchOS 27, and it is the one Apple's Device Hub drives.

## The procedure

1. **iPhone**: unlocked, Developer Mode on (Settings → Privacy & Security → Developer Mode),
   trusted for this Mac. Plug the cable in *while the phone is unlocked*; a locked phone at
   plug-in fails `companion_proxy` with `kAMDPasswordProtectedError` and the watch stays invisible
   until you unplug and replug.
2. **Mac, Xcode → Window → Devices and Simulators (Device Hub)**: the iPhone appears. The watch
   may appear greyed under it or not at all; either is fine.
3. **Device Hub → `+` → Pair Nearby Device**: the Mac starts beaconing. Leave this sheet open.
4. **Watch → Settings → Privacy & Security → Developer Mode**: this row does not exist until
   the Mac is beaconing; it appears after a few seconds of step 3. Turn the toggle on (a restart
   prompt follows on first enable). Below the toggle, under *Devices*, the Mac is listed while it
   beacons.
5. **Watch → tap the Mac → Pair**: a six-digit PIN shows on the watch; type it into the Mac's
   sheet. The watch becomes a CoreDevice ("Connected", with its own identifier).
6. **Verify from a shell**: `xcrun devicectl list devices` lists the watch with a CoreDevice
   identifier (`6CA9…` style, not the `00008310-…` UDID). Save it to
   `untracked/watch/.secrets/watch-device-id.txt`; `scripts/deploy-watch.sh` reads it.

Tailscale on the phone, Mac or watch has nothing to do with any of this; it was switched off during
the investigation and switched back on afterwards without effect.

## Signing

The app signs automatically with the team from `project.yml` (`DEVELOPMENT_TEAM`), and the CLI
build needs `-allowProvisioningUpdates` so `xcodebuild` can register the watch and mint the
profile. The team id is the one Xcode used for its own signed build (Report navigator → the
`CodeSign` step shows it); a wrong id fails with `No Account for Team …`.

## Install and launch without Xcode's debugger

Xcode's Run can sit on "Fetching debug symbols" for a long time on a new watch. The app does not
need the debugger: `scripts/deploy-watch.sh` builds signed, installs with
`xcrun devicectl device install app` and launches with `xcrun devicectl device process launch`,
passing the gateway URL and token as launch arguments so nothing is typed on the wrist:

```sh
scripts/deploy-watch.sh --env ../../../untracked/watch/.secrets/public-gateway.env   # GW_URL + GW_TOKEN
scripts/deploy-watch.sh --no-build --screen settings --shoot settings                # relaunch + screenshot
scripts/deploy-watch.sh --no-build --forget                                          # clear the saved pairing
```

Screenshots of the real watch: `xcrun devicectl device capture screenshot --device <id> --destination x.png`.

## What did not matter

Updating watchOS, macOS and Xcode (all done during the investigation) changed nothing; the
missing step was always the Mac-side beacon (step 3) that makes the Developer Mode row appear on
the watch. The three `defaults write com.apple.remotepairing …` keys tried along the way were
removed afterwards; they were not what made it work.

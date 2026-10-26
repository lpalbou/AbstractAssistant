#!/bin/zsh
# deploy-phone.sh [--device ID] [--gateway URL --token TOKEN [--user ID] | --env FILE | --forget]
#                 [--no-build] [--screen NAME] [--console] [--shoot FILE.png [--wait S]]
# Signed Debug build for the connected physical iPhone (scripts/build.py --device; --no-build: the
# last one), install over CoreDevice, launch with the sign-in from the arguments (or FILE: GW_URL +
# GW_TOKEN [+ GW_USER]) verified and sealed on the iPhone, handed to the watch and registered for
# push, exactly as the account-token sign-in does. No sign-in arguments keep the one on the iPhone;
# --forget clears it. Debug builds only: Release ignores these launch arguments.
# --console stays attached and prints the app's `phone-trace` lines (sign-in, watch handoff, push);
# --shoot captures a screenshot after S seconds (default 10; black while the screen is off).
# The iPhone: --device, PHONE_DEVICE, or ../../../untracked/watch/.secrets/phone-device-id.txt
# (xcrun devicectl list devices). Mirror of ../../watch/apple/scripts/deploy-watch.sh.
set -e; setopt null_glob
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SECRETS="$ROOT/../../../untracked/watch/.secrets"
DEVICE="${PHONE_DEVICE:-}"
if [ -z "$DEVICE" ] && [ -r "$SECRETS/phone-device-id.txt" ]; then DEVICE="$(head -1 "$SECRETS/phone-device-id.txt")"; fi   # no file: --device decides later, not a silent exit
TEAM="${DEVELOPMENT_TEAM:-$(sed -n 's/^ *DEVELOPMENT_TEAM: *//p' "$ROOT/project.yml" | head -1)}"
ENVF=""; GW=""; TOKEN=""; GUSER=""; SCREEN=""; SHOOT=""; WAIT=10; BUILD=1; CONSOLE=0; FORGET=0; ARGS=()
while [ $# -gt 0 ]; do case "$1" in
  --device) DEVICE="$2"; shift 2;;  --gateway) GW="$2"; shift 2;;  --token) TOKEN="$2"; shift 2;;
  --user) GUSER="$2"; shift 2;;  --env) ENVF="$2"; shift 2;;  --screen) SCREEN="$2"; shift 2;;
  --shoot) SHOOT="$2"; shift 2;;  --wait) WAIT="$2"; shift 2;;  --forget) FORGET=1; shift;;
  --no-build) BUILD=0; shift;;  --console) CONSOLE=1; shift;;
  *) echo "unknown argument $1"; exit 2;; esac; done
[ -n "$DEVICE" ] || { echo "no iPhone: --device <CoreDevice id> or PHONE_DEVICE (xcrun devicectl list devices)"; exit 1; }
if [ -n "$ENVF" ]; then source "$ENVF"; GW="${GW:-$GW_URL}"; TOKEN="${TOKEN:-$GW_TOKEN}"; GUSER="${GUSER:-$GW_USER}"; fi
if [ $FORGET = 1 ]; then
  [ -z "$GW$TOKEN$GUSER" ] || { echo "--forget takes no sign-in"; exit 2; }
  ARGS+=(--forget-gateway)
elif [ -n "$GW$TOKEN" ]; then
  [ -n "$GW" ] && [ -n "$TOKEN" ] || { echo "--gateway and --token go together"; exit 2; }
  ARGS+=(--gateway "$GW" --token "$TOKEN"); [ -n "$GUSER" ] && ARGS+=(--user "$GUSER")
fi
[ -n "$SCREEN" ] && ARGS+=(--screen "$SCREEN")
cd "$ROOT"
if [ $BUILD = 1 ]; then
  # The guarded build: one job, yields to other Xcode builds (exit 75), signs with automatic provisioning.
  python3 scripts/build.py --device "$DEVICE" --team "$TEAM" | tail -3
  [ ${pipestatus[1]} = 0 ] || { echo "build did not finish"; exit 1; }
fi
APP="build/DeviceDerivedData/Build/Products/Debug-iphoneos/AbstractAssistantPhone.app"
[ -d "$APP" ] || { echo "no Debug build at $APP (run without --no-build)"; exit 1; }
# devicectl reports its errors on stdout: show them when a step fails.
OUT=$(xcrun devicectl device install app --device "$DEVICE" "$APP" --timeout 180 2>&1) || { echo "$OUT"; exit 1; }
LAUNCH=(xcrun devicectl device process launch --device "$DEVICE" --terminate-existing)
if [ $CONSOLE = 1 ] && [ -z "$SHOOT" ]; then
  # No --timeout here: devicectl's timeout also ends a console attach.
  echo "launched${GW:+ against $GW}; console attached (Ctrl-C detaches)"
  exec "${LAUNCH[@]}" --console ai.abstractframework.assistant "${ARGS[@]}"
fi
OUT=$("${LAUNCH[@]}" --timeout 60 ai.abstractframework.assistant "${ARGS[@]}" 2>&1) || { echo "$OUT"; exit 1; }
echo "launched${GW:+ against $GW}${SCREEN:+ at $SCREEN}"
if [ -n "$SHOOT" ]; then
  sleep "$WAIT"; mkdir -p "$(dirname "$SHOOT")"
  xcrun devicectl device capture screenshot --device "$DEVICE" --destination "$SHOOT" --timeout 45 >/dev/null
  echo "$SHOOT"
fi

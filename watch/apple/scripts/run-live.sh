#!/bin/zsh
# run-live.sh [screen] — launch the installed simulator app in LIVE mode against the gateway in
# ../../../../untracked/watch/.secrets/watch.env (GW_URL, GW_WATCH_TOKEN) and take a screenshot.
set -e; setopt null_glob
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SIM="${SIM:-Apple Watch Series 11 (46mm)}"
ENVF="${GW_ENV:-$ROOT/../../../untracked/watch/.secrets/watch.env}"
[ -f "$ENVF" ] || { echo "missing $ENVF (GW_URL, GW_WATCH_TOKEN)"; exit 1; }
source "$ENVF"
SCREEN="${1:-home}"
APP=$ROOT/build/DerivedData/Build/Products/Debug-watchsimulator/AbstractAssistantWatch.app
xcrun simctl boot "$SIM" 2>/dev/null || true
xcrun simctl bootstatus "$SIM" >/dev/null
xcrun simctl install "$SIM" "$APP" >/dev/null
xcrun simctl terminate "$SIM" ai.abstractframework.assistant.watchkitapp >/dev/null 2>&1 || true
xcrun simctl launch "$SIM" ai.abstractframework.assistant.watchkitapp --live --gateway "$GW_URL" --token "$GW_WATCH_TOKEN" --screen "$SCREEN" ${EXTRA:+${=EXTRA}} >/dev/null
sleep "${WAIT:-8}"
mkdir -p "$ROOT/screenshots/live"
xcrun simctl io "$SIM" screenshot "$ROOT/screenshots/live/$SCREEN.png" >/dev/null 2>&1
echo "screenshots/live/$SCREEN.png"

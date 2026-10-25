#!/bin/zsh
# deploy-watch.sh [--env FILE] [--screen NAME] [--forget] [--no-build] [--shoot NAME [--wait S]]
# Signed Debug build for the paired physical watch (--no-build: the last one), install over CoreDevice, launch with the pairing
# from FILE (GW_URL + GW_TOKEN, or GW_WATCH_TOKEN) saved on the watch. No --env keeps the pairing
# already on the watch; --forget clears it (the app falls back to the Pair screen's values).
# Needs: the watch paired for development (docs/pairing.md) and its CoreDevice id in
# ../../../untracked/watch/.secrets/watch-device-id.txt or WATCH_DEVICE (xcrun devicectl list devices).
# The watch app is the AbstractAssistant iPhone app's companion (one project:
# ../../phone/iphone/project.yml); this installs the watch app by itself, straight onto the watch.
set -e; setopt null_glob
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT_DIR="$ROOT/../../phone/iphone"
SECRETS="$ROOT/../../../untracked/watch/.secrets"
DEVICE="${WATCH_DEVICE:-$(head -1 "$SECRETS/watch-device-id.txt" 2>/dev/null)}"
[ -n "$DEVICE" ] || { echo "no watch: set WATCH_DEVICE=<CoreDevice id> (xcrun devicectl list devices)"; exit 1; }
ENVF=""; SCREEN=""; SHOOT=""; WAIT=10; BUILD=1; ARGS=()
while [ $# -gt 0 ]; do case "$1" in
  --env) ENVF="$2"; shift 2;;  --screen) SCREEN="$2"; shift 2;;  --shoot) SHOOT="$2"; shift 2;;
  --wait) WAIT="$2"; shift 2;;  --forget) ARGS+=(--forget-gateway); shift;;  --no-build) BUILD=0; shift;;
  *) echo "unknown argument $1"; exit 2;; esac; done
if [ -n "$ENVF" ]; then
  source "$ENVF"; TOKEN="${GW_TOKEN:-$GW_WATCH_TOKEN}"
  [ -n "$GW_URL" ] && [ -n "$TOKEN" ] || { echo "$ENVF must set GW_URL and GW_TOKEN"; exit 1; }
  ARGS+=(--gateway "$GW_URL" --token "$TOKEN")
fi
[ -n "$SCREEN" ] && ARGS+=(--screen "$SCREEN")
cd "$ROOT"
if [ $BUILD = 1 ]; then
  [ "$PROJECT_DIR/project.yml" -nt "$PROJECT_DIR/AbstractAssistant.xcodeproj/project.pbxproj" ] && xcodegen generate --spec "$PROJECT_DIR/project.yml"
  xcodebuild -project "$PROJECT_DIR/AbstractAssistant.xcodeproj" -scheme AbstractAssistantWatch -destination 'generic/platform=watchOS' \
    -configuration Debug -derivedDataPath build/DerivedData -allowProvisioningUpdates -quiet build
fi
# Always install (--no-build installs the last build: a retry after the watch was out of reach).
xcrun devicectl device install app --device "$DEVICE" build/DerivedData/Build/Products/Debug-watchos/AbstractAssistantWatch.app --timeout 180 >/dev/null
xcrun devicectl device process launch --device "$DEVICE" --terminate-existing --timeout 60 ai.abstractframework.assistant.watchkitapp "${ARGS[@]}" >/dev/null
echo "launched${GW_URL:+ against $GW_URL}${SCREEN:+ at $SCREEN}"
if [ -n "$SHOOT" ]; then
  sleep "$WAIT"; mkdir -p design/screenshots/device
  xcrun devicectl device capture screenshot --device "$DEVICE" --destination "design/screenshots/device/$SHOOT.png" --timeout 45 >/dev/null
  echo "design/screenshots/device/$SHOOT.png"
fi

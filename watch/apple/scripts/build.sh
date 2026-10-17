#!/usr/bin/env bash
# Generate, test, build for the watch simulator, install, and screenshot every screen.
# Usage: scripts/build.sh [--no-screens]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SIM="${SIM:-Apple Watch Series 11 (46mm)}"
# The simulator by id: Xcode 27's name lookup fails when several runtimes are installed.
SIM_ID="$(xcrun simctl list devices available | grep -F "$SIM (" | head -1 | grep -oE '[0-9A-F]{8}-[0-9A-F-]{27}')"
[ -n "$SIM_ID" ] || { echo "no simulator named $SIM (xcrun simctl list devices)"; exit 1; }
BUNDLE=ai.abstractframework.assistant.watch
SCREENS=(home approval email draft askuser ask ask-entity picker listening thinking answer sessions session automations automation settings orbstyle signin read waits)
t() { date +%s; }

T0=$(t)
cd "$ROOT"
xcodegen generate --spec project.yml
(cd Packages/AbstractGatewayClient && swift test)
T1=$(t)
xcodebuild -project AbstractAssistantWatch.xcodeproj -scheme AbstractAssistantWatch \
  -destination "platform=watchOS Simulator,id=$SIM_ID" \
  -configuration Debug -derivedDataPath build/DerivedData build CODE_SIGNING_ALLOWED=NO -quiet
T2=$(t)
echo "swift test: $((T1-T0)) s (incl. generate) · xcodebuild: $((T2-T1)) s"
[[ "${1:-}" == "--no-screens" ]] && exit 0

APP=build/DerivedData/Build/Products/Debug-watchsimulator/AbstractAssistantWatch.app
xcrun simctl boot "$SIM_ID" 2>/dev/null || true
xcrun simctl bootstatus "$SIM_ID" >/dev/null
xcrun simctl install "$SIM_ID" "$APP"
mkdir -p screenshots
for s in "${SCREENS[@]}"; do
  xcrun simctl terminate "$SIM_ID" "$BUNDLE" 2>/dev/null || true
  # Exit code matters: a failed launch still yields a (watch-face) screenshot.
  xcrun simctl launch "$SIM_ID" "$BUNDLE" --mock --no-notification-prompt --screen "$s" >/dev/null
  sleep 4
  xcrun simctl io "$SIM_ID" screenshot "screenshots/$s.png" >/dev/null 2>&1
  echo "screenshot: screenshots/$s.png"
done
xcrun simctl terminate "$SIM_ID" "$BUNDLE" 2>/dev/null || true
xcrun simctl shutdown "$SIM_ID"
echo "total: $(( $(t) - T0 )) s"

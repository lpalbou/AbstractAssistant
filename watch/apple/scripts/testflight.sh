#!/bin/zsh
# testflight.sh [--no-upload] — archive AbstractAssistant (the iPhone app with the watch app inside,
# one project: ../../phone/iphone/project.yml) signed, and, without --no-upload, upload it for
# internal TestFlight testing (maintainers). The Store workflow is .github/workflows/iphone.yml.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT_DIR="$ROOT/../../phone/iphone"
cd "$ROOT"
xcodegen generate --spec "$PROJECT_DIR/project.yml" >/dev/null
ARCHIVE=build/AbstractAssistant.xcarchive
python3 -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ('$ARCHIVE', 'build/upload')]"
xcodebuild -project "$PROJECT_DIR/AbstractAssistant.xcodeproj" -scheme AbstractAssistantPhone -configuration Release \
  -destination 'generic/platform=iOS' -archivePath "$ARCHIVE" -derivedDataPath build/DerivedData -allowProvisioningUpdates -quiet archive
WATCH_PLIST="$ARCHIVE/Products/Applications/AbstractAssistantPhone.app/Watch/AbstractAssistantWatch.app/Info.plist"
echo "archived: $(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$WATCH_PLIST") ($(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$WATCH_PLIST"))"
[ "${1:-}" = "--no-upload" ] && exit 0
cat > build/ExportOptions-upload.plist <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>method</key><string>app-store-connect</string>
  <key>destination</key><string>upload</string>
  <key>teamID</key><string>K3R4D6HP2A</string>
  <key>signingStyle</key><string>automatic</string>
  <key>uploadSymbols</key><true/>
  <key>testFlightInternalTestingOnly</key><true/>
</dict></plist>
PLIST
xcodebuild -exportArchive -archivePath "$ARCHIVE" -exportOptionsPlist build/ExportOptions-upload.plist \
  -exportPath build/upload -allowProvisioningUpdates

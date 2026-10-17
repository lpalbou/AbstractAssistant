#!/bin/zsh
# testflight.sh [--no-upload] — archive the App Store carrier (the empty iOS container holding the
# watch app) and upload it to App Store Connect for INTERNAL TestFlight testing.
# Needs: the app record for ai.abstractframework.assistant in App Store Connect (create it once:
# Xcode Organizer → Distribute App, or appstoreconnect.apple.com → Apps → +), and Xcode signed in
# to team K3R4D6HP2A. Bump CURRENT_PROJECT_VERSION in project.yml before every new upload.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
xcodegen generate --spec project.yml >/dev/null
ARCHIVE=build/AbstractAssistant.xcarchive
python3 -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ('$ARCHIVE', 'build/upload')]"
xcodebuild -project AbstractAssistantWatch.xcodeproj -scheme AbstractAssistant -configuration Release \
  -destination 'generic/platform=iOS' -archivePath "$ARCHIVE" -derivedDataPath build/DerivedData -allowProvisioningUpdates -quiet archive
echo "archived: $(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$ARCHIVE/Products/Applications/AbstractAssistant.app/Watch/AbstractAssistantWatch.app/Info.plist") ($(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$ARCHIVE/Products/Applications/AbstractAssistant.app/Watch/AbstractAssistantWatch.app/Info.plist"))"
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

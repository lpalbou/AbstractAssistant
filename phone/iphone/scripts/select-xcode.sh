#!/bin/bash
set -euo pipefail
major="${XCODE_MAJOR:-27}"
[[ "$major" =~ ^[0-9]+$ ]] || exit 1
app=$(ls -d /Applications/Xcode_"${major}".*.app 2>/dev/null | grep -Evi 'beta|rc' | sort -V | tail -1 || true)
if [ -z "$app" ]; then
  echo "::error::No released Xcode ${major}.x is installed on this runner."
  exit 1
fi
sudo xcode-select -s "$app/Contents/Developer"
xcodebuild -version

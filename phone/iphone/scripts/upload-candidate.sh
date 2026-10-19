#!/bin/bash
# Only the protected GitHub environment supplies credentials to this script.
set -euo pipefail
: "${RUNNER_TEMP:?}" "${GITHUB_SHA:?}" "${TEAM_ID:?}" "${ASC_KEY_ID:?}" "${ASC_ISSUER_ID:?}" "${ASC_KEY_P8:?}"
[[ "$ASC_KEY_ID" =~ ^[A-Z0-9]{10}$ ]] || { echo '::error::Invalid ASC_KEY_ID'; exit 1; }
[[ "$ASC_ISSUER_ID" =~ ^[0-9a-fA-F-]{36}$ ]] || { echo '::error::Invalid ASC_ISSUER_ID'; exit 1; }
base=$(cd "$(dirname "$0")" && pwd)
work=$(mktemp -d "$RUNNER_TEMP/iphone-upload.XXXXXX")
trap 'rm -rf "$work"' EXIT
chmod 700 "$work"
python3 "$base/release.py" verify --folder "$1" --destination "$work/unpacked" --sha "$GITHUB_SHA"
umask 077
key="$work/AuthKey_${ASC_KEY_ID}.p8"
printf '%s\n' "$ASC_KEY_P8" > "$key"
unset ASC_KEY_P8
openssl pkey -in "$key" -noout >/dev/null
python3 "$base/release.py" export-options "$work/ExportOptions.plist" --team "$TEAM_ID"
xcodebuild -exportArchive \
  -archivePath "$work/unpacked/AbstractAssistantPhone.xcarchive" \
  -exportOptionsPlist "$work/ExportOptions.plist" -exportPath "$work/export" \
  -allowProvisioningUpdates -authenticationKeyPath "$key" \
  -authenticationKeyID "$ASC_KEY_ID" -authenticationKeyIssuerID "$ASC_ISSUER_ID"

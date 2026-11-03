#!/bin/bash
# Select the newest RELEASED Xcode of the wanted major on this runner.
# Betas and release candidates are refused even when a plain-named symlink
# points at them (the hosted image ships /Applications/Xcode_27.2.app ->
# Xcode_27.2_Release_Candidate.app; App Store Connect rejects archives built
# with it), so each candidate is judged by its real path, not its link name.
set -euo pipefail
major="${XCODE_MAJOR:-27}"
[[ "$major" =~ ^[0-9]+$ ]] || exit 1
apps="${XCODE_APPS_DIR:-/Applications}"
best=""
best_version=""
for link in "$apps"/Xcode_"$major".*.app "$apps"/Xcode_"$major".app; do
  [ -e "$link" ] || continue
  real=$(cd "$link" 2>/dev/null && pwd -P) || continue
  name=$(basename "$real")
  # Only a bare numeric version of the wanted major is a release: Xcode_27.1.app, Xcode_27.app.
  [[ "$name" =~ ^Xcode_(${major}(\.[0-9]+)*)\.app$ ]] || continue
  version="${BASH_REMATCH[1]}"
  if [ -z "$best" ] || [ "$(printf '%s\n%s\n' "$best_version" "$version" | sort -V | tail -1)" = "$version" ]; then
    best="$real"; best_version="$version"
  fi
done
if [ -z "$best" ]; then
  echo "::error::No released Xcode ${major}.x is installed under $apps (betas and release candidates are refused)."
  exit 1
fi
echo "selected=$best"
[ -n "${XCODE_SELECT_DRY_RUN:-}" ] && exit 0
sudo xcode-select -s "$best/Contents/Developer"
xcodebuild -version

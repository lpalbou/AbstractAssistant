#!/bin/zsh
# test-watch.sh light|full [Test …]
#   light  the tests of the shared pages (orb page, navigation, an automation, tools): ~5 min,
#          after each change. Extra test classes may be added: test-watch.sh light ShareUITests
#   full   every test but the live ones, on 3 simulator clones in parallel (~10 min), once
#          before a commit or a deploy.
# Package tests (`swift test` in Packages/AbstractGatewayClient) run in both: a few seconds.
set -e
cd "$(dirname "$0")/.."
MODE=${1:-light}; shift || true
SIM=${WATCH_SIM:-7CB8FFBB-6A57-45E8-98D2-2CE7502252F8}
LOG=${TMPDIR:-/tmp}/watch-tests-$MODE.log
(cd Packages/AbstractGatewayClient && swift test 2>&1 | tail -1)
ARGS=(-project AbstractAssistantWatch.xcodeproj -scheme AbstractAssistantWatchUITests
      -destination "platform=watchOS Simulator,id=$SIM" -derivedDataPath build/DerivedData CODE_SIGNING_ALLOWED=NO)
T=AbstractAssistantWatchUITests
if [[ $MODE == light ]]; then
  for c in CornerButtonUITests BrowserNavigationUITests AutomationConversationUITests NewConversationToolsUITests \
           SendNowUITests StopVoiceUITests "$@"; do ARGS+=(-only-testing:$T/$c); done
else
  for c in LiveActivityUITests LiveEditUITests LiveHistoryUITests LiveHomeUITests LiveMediaUITests AskStatusUITests; do
    ARGS+=(-skip-testing:$T/$c)
  done
  ARGS+=(-parallel-testing-enabled YES -parallel-testing-worker-count 3)
fi
xcodebuild test "${ARGS[@]}" > "$LOG" 2>&1 || true
grep -E "Test Case .*failed|error: -\[" "$LOG" | cut -c1-220 | sort -u
echo "$(grep -c 'Test Case .*passed' "$LOG") passed, $(grep -c 'Test Case .*failed' "$LOG") failed — $LOG"

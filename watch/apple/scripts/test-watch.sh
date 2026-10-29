#!/bin/zsh
# test-watch.sh light|full [Test …]
#   light  the tests of the shared pages (orb page, navigation, an automation, tools): ~5 min,
#          after each change. Extra test classes may be added: test-watch.sh light ShareUITests
#   full   every test but the live ones, on 3 simulator clones in parallel (~10 min), once
#          before a commit or a deploy.
# Package tests (`swift test` in Packages/AbstractGatewayClient) run in both: a few seconds.
# One project for the iPhone and the watch app: ../../phone/iphone/project.yml (AbstractAssistant.xcodeproj).
set -e
cd "$(dirname "$0")/.."
[ ../../phone/iphone/project.yml -nt ../../phone/iphone/AbstractAssistant.xcodeproj/project.pbxproj ] && xcodegen generate --spec ../../phone/iphone/project.yml >/dev/null
MODE=${1:-light}; shift || true
SIM=${WATCH_SIM:-7CB8FFBB-6A57-45E8-98D2-2CE7502252F8}
LOG=${TMPDIR:-/tmp}/watch-tests-$MODE.log
# The voice tests listen: the app's microphone permission (per bundle id) must not stop them.
xcrun simctl privacy "$SIM" grant microphone ai.abstractframework.assistant.watchkitapp >/dev/null 2>&1 || true
(cd Packages/AbstractGatewayClient && swift test 2>&1 | tail -1)
(cd ../../phone/iphone/Packages/AssistantPush && swift test 2>&1 | tail -1)
ARGS=(-project ../../phone/iphone/AbstractAssistant.xcodeproj -scheme AbstractAssistantWatchUITests
      -destination "platform=watchOS Simulator,id=$SIM" -derivedDataPath build/DerivedData CODE_SIGNING_ALLOWED=NO)
T=AbstractAssistantWatchUITests
if [[ $MODE == light ]]; then
  for c in CornerButtonUITests BrowserNavigationUITests AutomationConversationUITests RunFeedbackUITests NewConversationToolsUITests \
           SendNowUITests StopVoiceUITests "$@"; do ARGS+=(-only-testing:$T/$c); done
else
  for c in LiveActivityUITests LiveEditUITests LiveHistoryUITests LiveHomeUITests LiveMediaUITests AskStatusUITests; do
    ARGS+=(-skip-testing:$T/$c)
  done
  ARGS+=(-parallel-testing-enabled YES -parallel-testing-worker-count 3)
fi
xcodebuild test "${ARGS[@]}" > "$LOG" 2>&1 || true
# (a parallel run says "Test case … passed on 'Clone 2 …'"; a serial one "Test Case '-[…]' passed")
# (xcodebuild's own notes can break a line in two: count the outcomes, not the lines)
grep -iE "test case .*\) failed|error: -\[|^.*\.swift:[0-9]+: error" "$LOG" | cut -c1-220 | sort -u
echo "$(grep -oiE "test case '[^']+' passed" "$LOG" | sort -u | wc -l | tr -d ' ') passed, $(grep -oiE "test case '[^']+' failed" "$LOG" | sort -u | wc -l | tr -d ' ') failed — $(grep -oE 'TEST (SUCCEEDED|FAILED)' "$LOG" | tail -1) — $LOG"

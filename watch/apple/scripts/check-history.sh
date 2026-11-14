#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/assistant-history-check.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
swiftc "$ROOT/Sources/App/Shared/AutomationRunHistory.swift" "$ROOT/Checks/AutomationRunHistoryCheck.swift" -o "$WORK/history-check"
"$WORK/history-check"

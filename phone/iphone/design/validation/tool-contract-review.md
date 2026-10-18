# Conversation tool compatibility — 0.6.3 (11)

## Scope and correction

Assistant tool discovery and run submission use the established desktop contract:
`GET /discovery/tools`, account workflow preferences, and `POST /runs/start`.
The phone no longer calls or requires `/tool-policy/capabilities`.
Explicit choices preserve enabled names in `tools` and `_runtime.allowed_tools`,
and approval lists in `_runtime.tool_policy`. Empty enabled lists deny all tools;
omission inherits defaults. Attachments remain in the same request.

Entity session-local approvals add behavior absent from the older entity APIs.
Gateway commit `fd57f04e` exposes it through existing visit open/close routes.
The entity inventory's optional `visit_routes` flag selects these routes. Its
absence selects the earlier managed aliases, preserving compatibility with gateways
that implemented session approvals before the consolidation. A missing inventory
never causes explicit policies to be submitted through an ungated legacy visit.

## Observed evidence

- 65 gateway checks passed: managed approvals, canonical routes, compatibility
  aliases, null versus empty modes, owner checks, rejoin, legacy visit lifecycle,
  grant precedence and pending approval cancellation. Cancellation cannot call
  the tool handler and still fires queued admission.
- 32 existing runtime policy/scope checks passed: per-run Auto and Approve,
  explicit deny-all, ancestor ceilings and approval rechecks. No runtime feature
  or package-version change was required.
- 89 Swift package checks passed: 61 phone checks and 28 inherited client checks.
  The older-gateway regression returns 404 for every route outside established
  discovery/preferences/run-start paths and asserts the exact request sequence.
  Transport cases cover both entity route variants, inheritance, deny-all and
  rejected entity discovery.
- Three native tools UI checks passed with no failures, skips or runtime warnings:
  Settings entry, category/search/disabled states and per-conversation Save.
  Result: `build/UITests-1792293809304255000.xcresult`. The parent inspected
  exported filtered-Save and expanded-category screenshots from the actual run.
  Native UI uses demo data; the older-server transport regression is separate.

Gateway checks used the workspace `abstractagent/src` on `PYTHONPATH`; the installed
copy lacks the existing `reset_react_turn` export and cannot run the visit suite.
All providers were scripted; these checks do not contact a remote gateway or LLM.

Logs: `/tmp/gateway-tool-contract-local-tests.log`,
`/tmp/runtime-established-tool-contract-tests.log`,
`/tmp/phone-tool-contract-tests.log`, `/tmp/phone-tool-contract-native.log`.

## Independent review

- Execution Mode: implementation by parent; one independent adversarial reviewer.
- Planned Reviewer Set: one reviewer covering correctness, architecture and users/operations.
- Actual Reviewer Set: `/root/tool_contract_adversary`.
- Subagents Used: one, reused for framework and phone reviews.
- Fallback Reason: none.
- Contract Degradation: none; the user explicitly requested one adversarial subagent.
- Observed Evidence: real source diffs and test logs listed above.
- Inference Or Unverified Claims: live remote gateway behavior and physical delivery
  are not established by source/package tests.
- Reviewer Verdicts: framework Approved; phone Approved at source/package-test level.
- Open Questions Or Missing Evidence: live remote gateway and physical delivery
  have not been exercised for this version.
- Residual Risk: gateways without entity session approvals retain legacy chat and
  cannot enforce visitor-specific entity approval choices.
- Final Verdict: Approved for the inspected implementation and native UI scope;
  device delivery remains a separate installation result.

## Device delivery

The guarded signed-device build exited with status 75 after another Xcode build
started; only this iPhone build was stopped to preserve Watch priority. No 0.6.3
installation was attempted from that interrupted build. A CoreDevice installed-app
query confirmed 0.6.1 (9) is still installed. The earlier 0.6.2 installation had
failed because the iPhone had no free storage; no app or user data was removed.
Log: `/tmp/phone-tool-contract-device.log`.

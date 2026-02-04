import pytest

from abstractassistant.core.tool_policy import ToolApprovalPolicy


@pytest.mark.basic
def test_tool_policy_requires_approval_for_unknown_tool() -> None:
    policy = ToolApprovalPolicy()
    assert policy.requires_approval([{"name": "some_new_tool", "arguments": {}}]) is True


@pytest.mark.basic
def test_tool_policy_auto_approves_safe_tools_only() -> None:
    policy = ToolApprovalPolicy()
    assert policy.requires_approval([{"name": "read_file", "arguments": {"file_path": "x.txt"}}]) is False
    assert policy.requires_approval([{"name": "execute_command", "arguments": {"command": "echo hi"}}]) is True


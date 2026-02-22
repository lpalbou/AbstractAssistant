"""Unit tests for gateway history bundle seeding."""

from abstractassistant.gateway.history_seed import seed_messages_from_history_bundle


def test_seed_from_session_turns() -> None:
    bundle = {
        "session": {
            "turns": [
                {"run_id": "r1", "prompt": "hello", "answer": "hi there", "answer_meta": {"kind": "chat"}},
            ]
        }
    }
    msgs = seed_messages_from_history_bundle(bundle, include_tool_calls_for_run_id="r1")
    assert [m.get("role") for m in msgs][:2] == ["user", "assistant"]
    assert msgs[0].get("content") == "hello"
    assert msgs[1].get("content") == "hi there"
    assert isinstance(msgs[1].get("metadata"), dict)


def test_seed_tool_cards_truncation() -> None:
    long_output = "x" * 9001
    bundle = {
        "session": {
            "turns": [
                {"run_id": "r2", "prompt": "do tool", "answer": "done"},
            ]
        },
        "ledgers": {
            "r2": {
                "items": [
                    {
                        "record": {
                            "status": "completed",
                            "ended_at": "2026-02-21T00:00:00Z",
                            "effect": {
                                "type": "tool_calls",
                                "payload": {
                                    "tool_calls": [
                                        {"name": "write_file", "call_id": "c1", "arguments": {"path": "/tmp/x"}}
                                    ]
                                },
                            },
                            "result": {"results": [{"call_id": "c1", "success": True, "output": long_output}]},
                        }
                    }
                ]
            }
        },
    }
    msgs = seed_messages_from_history_bundle(bundle, include_tool_calls_for_run_id="r2")
    tool_msgs = [m for m in msgs if m.get("role") == "tool"]
    assert tool_msgs, "expected tool messages from ledger"
    assert "#TRUNCATION" in str(tool_msgs[0].get("content") or "")
    assert tool_msgs[0].get("metadata", {}).get("name") == "write_file"


def test_seed_root_prompt_fallback() -> None:
    bundle = {"input_data": {"prompt": "root prompt"}}
    msgs = seed_messages_from_history_bundle(bundle)
    assert msgs and msgs[0].get("role") == "user"
    assert msgs[0].get("content") == "root prompt"

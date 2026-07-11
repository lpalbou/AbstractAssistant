"""Unit tests for gateway history bundle seeding."""

from abstractassistant.gateway.history_seed import (
    recover_missing_assistant_from_history_bundle,
    seed_messages_from_history_bundle,
)


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


def _llm_record(*, run_id: str, input_tokens: int, output_tokens: int, ts: str) -> dict:
    return {
        "record": {
            "run_id": run_id,
            "status": "completed",
            "started_at": ts,
            "ended_at": ts,
            "effect": {"type": "llm_call", "payload": {}},
            "result": {
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                }
            },
        }
    }


def _tool_record(*, run_id: str, name: str, arguments: dict, ts: str) -> dict:
    return {
        "record": {
            "run_id": run_id,
            "status": "completed",
            "started_at": ts,
            "ended_at": ts,
            "effect": {
                "type": "tool_calls",
                "payload": {"tool_calls": [{"name": name, "call_id": "c1", "arguments": arguments}]},
            },
            "result": {"results": [{"call_id": "c1", "success": True, "output": "ok"}]},
        }
    }


def test_seed_attaches_run_tree_stats_to_assistant_message() -> None:
    """Answers seeded from a bundle carry ledger-derived stats aggregated across
    the whole run tree (root + sub-runs), since agent workflows execute their
    llm_call/tool_calls effects in sub-runs."""
    bundle = {
        "root_run_id": "root-1",
        "session": {
            "turns": [
                {"run_id": "root-1", "prompt": "do work", "answer": "done"},
            ]
        },
        "ledgers": {
            "root-1": {
                "items": [
                    _llm_record(run_id="root-1", input_tokens=100, output_tokens=20, ts="2026-07-09T10:00:00Z"),
                ]
            },
            "sub-1": {
                "items": [
                    _llm_record(run_id="sub-1", input_tokens=900, output_tokens=80, ts="2026-07-09T10:00:05Z"),
                    _tool_record(
                        run_id="sub-1",
                        name="write_file",
                        arguments={"file_path": "out.md", "content": "x"},
                        ts="2026-07-09T10:00:10Z",
                    ),
                ]
            },
        },
    }

    msgs = seed_messages_from_history_bundle(bundle, include_tool_calls_for_run_id="root-1")
    assistant = [m for m in msgs if m.get("role") == "assistant"][0]
    stats = assistant["metadata"]["_assistant_stats"]

    assert stats["llm_calls"] == 2
    assert stats["tool_calls"] == 1
    assert stats["usage"] == {"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100}
    assert stats["tool_call_details"][0]["name"] == "write_file"
    assert stats["duration_ms"] == 10000


def test_seed_keeps_existing_repl_stats_for_other_turns() -> None:
    """Only the target run's answer gets bundle stats; other session turns keep
    their own metadata untouched."""
    bundle = {
        "root_run_id": "root-2",
        "session": {
            "turns": [
                {"run_id": "old-run", "prompt": "before", "answer": "old answer", "stats": {"llm_calls": 7}},
                {"run_id": "root-2", "prompt": "now", "answer": "new answer"},
            ]
        },
        "ledgers": {
            "root-2": {
                "items": [
                    _llm_record(run_id="root-2", input_tokens=10, output_tokens=5, ts="2026-07-09T11:00:00Z"),
                ]
            }
        },
    }

    msgs = seed_messages_from_history_bundle(bundle, include_tool_calls_for_run_id="root-2")
    old = [m for m in msgs if m.get("role") == "assistant" and m.get("run_id") == "old-run"][0]
    new = [m for m in msgs if m.get("role") == "assistant" and m.get("run_id") == "root-2"][0]

    assert "_assistant_stats" not in (old.get("metadata") or {})
    assert (old.get("metadata") or {}).get("_repl", {}).get("stats", {}).get("llm_calls") == 7
    assert new["metadata"]["_assistant_stats"]["usage"]["input_tokens"] == 10


def test_seed_recovers_missing_assistant_from_subworkflow_artifact() -> None:
    bundle = {
        "root_run_id": "root-1",
        "input_data": {"prompt": "find Genentech roles"},
        "ledgers": {
            "root-1": {
                "items": [
                    {
                        "record": {
                            "status": "completed",
                            "node_id": "end_chat",
                            "effect": None,
                            "ended_at": "2026-06-20T16:00:00Z",
                            "result": {
                                "output": {
                                    "response": "",
                                    "meta": {"sub_run_id": "child-1", "tool_calls": 3, "tool_results": 3},
                                }
                            },
                        }
                    }
                ]
            },
            "child-1": {
                "items": [
                    {
                        "record": {
                            "status": "completed",
                            "node_id": "done",
                            "effect": None,
                            "ended_at": "2026-06-20T15:59:59Z",
                            "result": {"output": {"$artifact": "art-1"}},
                        }
                    }
                ]
            },
        },
    }

    def _loader(run_id: str, artifact_id: str):
        assert run_id == "child-1"
        assert artifact_id == "art-1"
        return b'{"answer":"Recovered assistant answer","report":"ok"}', "application/json"

    recovered = recover_missing_assistant_from_history_bundle(
        bundle,
        run_id="root-1",
        artifact_loader=_loader,
    )
    assert isinstance(recovered, dict)
    assert recovered["content"] == "Recovered assistant answer"
    assert recovered["run_id"] == "root-1"
    assert recovered["metadata"]["sub_run_id"] == "child-1"

    msgs = seed_messages_from_history_bundle(
        bundle,
        include_tool_calls_for_run_id="root-1",
        artifact_loader=_loader,
    )
    assert [m.get("role") for m in msgs] == ["user", "assistant"]
    assert msgs[-1]["content"] == "Recovered assistant answer"

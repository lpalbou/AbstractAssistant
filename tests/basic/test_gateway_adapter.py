"""
Basic tests for gateway ledger -> UI event adapter.
"""

from abstractassistant.gateway.adapter import GatewayEventAdapter


def test_adapter_emits_status_and_message() -> None:
    adapter = GatewayEventAdapter()
    rec = {"effect": {"type": "emit_event", "payload": {"name": "abstract.status", "payload": "Thinking"}}}
    events = adapter.handle_record(rec)
    assert events and events[0]["type"] == "status"


def test_adapter_emits_tool_request() -> None:
    adapter = GatewayEventAdapter()
    rec = {
        "result": {
            "wait": {
                "reason": "job",
                "wait_key": "tool:1",
                "details": {"tool_calls": [{"name": "read_file", "arguments": {"path": "README.md"}}]},
            }
        }
    }
    events = adapter.handle_record(rec)
    assert events and events[0]["type"] == "tool_request"


def test_adapter_emits_final_event_for_bare_artifact_output() -> None:
    adapter = GatewayEventAdapter()
    rec = {"result": {"output": {"$artifact": "answer_1", "content_type": "application/json"}}}

    events = adapter.handle_record(rec)

    assert events == [
        {
            "type": "assistant",
            "content": "",
            "meta": {
                "$artifact": "answer_1",
                "artifact": {"$artifact": "answer_1", "content_type": "application/json"},
                "artifact_id": "answer_1",
                "content_type": "application/json",
            },
            "final": True,
            "ts": "",
        }
    ]


def test_adapter_emits_cycle_for_reason_llm_call_started() -> None:
    """STARTED llm_call records on the agent's reason node become numbered cycle events
    (2026-07-10: live 'thinking, Nth pass' visibility), counted per run."""
    adapter = GatewayEventAdapter()
    rec = {
        "run_id": "r1",
        "node_id": "reason",
        "status": "started",
        "effect": {"type": "llm_call", "payload": {}},
    }
    assert {"type": "cycle", "iteration": 1} in adapter.handle_record(dict(rec))
    assert {"type": "cycle", "iteration": 2} in adapter.handle_record(dict(rec))
    # Independent counter per run id (subruns count on their own).
    assert {"type": "cycle", "iteration": 1} in adapter.handle_record(dict(rec, run_id="r2"))
    # Non-reason llm_call starts do not produce cycle events.
    assert not [
        e for e in adapter.handle_record(dict(rec, node_id="finalize")) if e.get("type") == "cycle"
    ]


def test_adapter_emits_tool_started_with_args_preview() -> None:
    """STARTED tool_calls records surface the launch (name + args preview) BEFORE
    execution; previously only tool results were visible."""
    adapter = GatewayEventAdapter()
    rec = {
        "run_id": "r1",
        "node_id": "act",
        "status": "started",
        "effect": {
            "type": "tool_calls",
            "payload": {"tool_calls": [{"name": "read_file", "arguments": {"file_path": "README.md"}}]},
        },
    }
    events = [e for e in adapter.handle_record(rec) if e.get("type") == "tool_started"]
    assert events
    tools = events[0]["tools"]
    assert tools[0]["name"] == "read_file"
    assert "README.md" in tools[0]["arguments_preview"]
    # Full args text for the activity view rides beside the bounded preview.
    assert "README.md" in tools[0]["arguments_text"]

    # Completed records must NOT re-announce the launch.
    done = dict(rec, status="completed")
    assert not [e for e in adapter.handle_record(done) if e.get("type") == "tool_started"]


def _approval_wait_record(wait_key: str, step_id: str, command: str = "ls") -> dict:
    return {
        "run_id": "r1",
        "node_id": "act",
        "step_id": step_id,
        "status": "waiting",
        "effect": {"type": "tool_calls", "payload": {}},
        "result": {
            "wait": {
                "reason": "user",
                "wait_key": wait_key,
                "details": {
                    "mode": "approval_required",
                    "tool_calls": [{"name": "execute_command", "arguments": {"command": command}}],
                },
            }
        },
    }


def _resume_record(wait_key: str) -> dict:
    return {
        "run_id": "r1",
        "node_id": "act",
        "step_id": "resume-step",
        "status": "completed",
        "effect": {"type": "resume", "payload": {"wait_key": wait_key, "wait_reason": "user"}},
        "result": {},
    }


def test_adapter_reprompts_repeated_wait_key_after_resume() -> None:
    """THE 2026-07-28 stall: the runtime reuses one stable wait_key
    (tool_calls:<run>:act) for EVERY approval batch from the same node.
    Key-only dedup swallowed the second approval and the run parked forever
    while the UI showed a running tool. After a resume record (the wait was
    answered), a new wait on the same key is a NEW question and must emit."""
    adapter = GatewayEventAdapter()
    key = "tool_calls:r1:act"

    first = adapter.handle_record(_approval_wait_record(key, "step-1", "find A"))
    assert [e for e in first if e.get("type") == "tool_request"]

    # Same occurrence replayed (stream retry) stays deduped.
    again = adapter.handle_record(_approval_wait_record(key, "step-1", "find A"))
    assert not [e for e in again if e.get("type") == "tool_request"]

    adapter.handle_record(_resume_record(key))

    second = adapter.handle_record(_approval_wait_record(key, "step-2", "find B"))
    assert [e for e in second if e.get("type") == "tool_request"], (
        "second approval on the same wait_key must re-prompt after the first was resumed"
    )


def test_adapter_synthetic_wait_dedups_against_real_occurrence() -> None:
    """Synthetic rehydration records carry no step_id; they must dedup
    against an already-emitted real occurrence (and vice versa) so the same
    pending question never opens two dialogs."""
    adapter = GatewayEventAdapter()
    key = "tool_calls:r1:act"

    assert [e for e in adapter.handle_record(_approval_wait_record(key, "step-1")) if e.get("type") == "tool_request"]
    synthetic = dict(_approval_wait_record(key, ""))
    synthetic.pop("step_id")
    assert not [e for e in adapter.handle_record(synthetic) if e.get("type") == "tool_request"]

    # Synthetic-first order: the later real record is the same question.
    adapter2 = GatewayEventAdapter()
    assert [e for e in adapter2.handle_record(dict(synthetic)) if e.get("type") == "tool_request"]
    assert not [e for e in adapter2.handle_record(_approval_wait_record(key, "step-1")) if e.get("type") == "tool_request"]


def test_adapter_seeded_occurrences_survive_resume_records() -> None:
    """Terminal-attach replays seed EVERY historical occurrence: replaying
    waiting -> resume -> waiting must stay silent (seeded marks are not
    cleared by resume records — only live marks are)."""
    adapter = GatewayEventAdapter()
    key = "tool_calls:r1:act"
    adapter.seed_handled_wait_occurrences([(key, "step-1"), (key, "step-2")])

    assert not adapter.handle_record(_approval_wait_record(key, "step-1"))
    adapter.handle_record(_resume_record(key))
    assert not adapter.handle_record(_approval_wait_record(key, "step-2"))


def test_adapter_seeding_all_but_pending_lets_pending_prompt() -> None:
    """Waiting-attach replay: historical occurrences seeded, the pending one
    excluded — replay suppresses the answered dialog and re-opens only the
    pending one."""
    adapter = GatewayEventAdapter()
    key = "tool_calls:r1:act"
    adapter.seed_handled_wait_occurrences([(key, "step-1")])

    assert not adapter.handle_record(_approval_wait_record(key, "step-1"))
    adapter.handle_record(_resume_record(key))
    pending = adapter.handle_record(_approval_wait_record(key, "step-2"))
    assert [e for e in pending if e.get("type") == "tool_request"]


def test_adapter_ask_user_wait_reprompts_after_resume() -> None:
    """The same occurrence contract applies to ask-user waits — the runtime
    reuses user:{run}:{node} keys for repeated questions from one node."""
    adapter = GatewayEventAdapter()
    key = "user:r1:ask"

    def _ask(step: str) -> dict:
        return {
            "run_id": "r1",
            "node_id": "ask",
            "step_id": step,
            "status": "waiting",
            "result": {"wait": {"reason": "user", "wait_key": key, "prompt": "Which one?"}},
        }

    assert [e for e in adapter.handle_record(_ask("s1")) if e.get("type") == "ask_user"]
    assert not [e for e in adapter.handle_record(_ask("s1")) if e.get("type") == "ask_user"]
    adapter.handle_record(_resume_record(key))
    assert [e for e in adapter.handle_record(_ask("s2")) if e.get("type") == "ask_user"]


def test_adapter_emits_cycle_result_with_model_output_not_prompt_echo() -> None:
    """COMPLETED reason llm_calls surface the model's ACTUAL cycle output
    (content + reasoning from the RESULT) — never the STARTED payload's
    messages, which echo the user's prompt (the 2026-07-17 dishonesty:
    'thinking' showing a repetition of the user's message)."""
    adapter = GatewayEventAdapter()
    started = {
        "run_id": "r1",
        "node_id": "reason",
        "status": "started",
        "effect": {
            "type": "llm_call",
            "payload": {"messages": [{"role": "user", "content": "the user prompt"}]},
        },
    }
    adapter.handle_record(started)

    completed = {
        "run_id": "r1",
        "node_id": "reason",
        "status": "completed",
        "ended_at": "2026-07-17T17:00:00+00:00",
        "effect": {"type": "llm_call", "payload": {}},
        "result": {
            "content": "I should check the README first.",
            "reasoning": "The user asked about setup; the README likely documents it.",
        },
    }
    events = [
        e for e in adapter.handle_record(completed) if e.get("type") == "cycle_result"
    ]
    assert events
    ev = events[0]
    assert ev["iteration"] == 1
    assert ev["content"] == "I should check the README first."
    assert "README likely documents" in ev["reasoning"]
    assert "the user prompt" not in ev["content"]

    # A completed reason call with an empty result emits nothing.
    silent = dict(completed, result={})
    assert not [
        e for e in adapter.handle_record(silent) if e.get("type") == "cycle_result"
    ]

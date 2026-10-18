"""2026-10-18: the Assistant workflow speaks. "Make a voice recording saying ..." routes to a
voice branch whose call is a BARE speech spec (modality voice, task tts), so the runtime gives
it the gateway's output.voice engine, the one that reads replies aloud. The sound branch asks
for a sound effect, never speech.

Driven through the real runtime compiler and Runtime with a fake LLM handler that answers the
router like a model would and records the media call it then receives.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

import pytest

from agent_fixture import agent_subflow  # tests/basic is on sys.path
from abstractassistant.assistant_workflow import _ROUTER_SCHEMA, _ROUTER_SYSTEM_PROMPT, managed_assistant_visualflow

rt = pytest.importorskip("abstractruntime")
compile_visualflow = pytest.importorskip("abstractruntime.visualflow_compiler").compile_visualflow
from abstractruntime.core.models import EffectType  # noqa: E402
from abstractruntime.core.runtime import EffectOutcome  # noqa: E402

AUDIO = {"$artifact": "a" * 32, "content_type": "audio/wav", "artifact_id": "a" * 32}


def _run(route: Dict[str, Any]) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    media_calls: List[Dict[str, Any]] = []

    def llm(run, effect, default_next_node: Optional[str]):
        payload = dict(effect.payload or {})
        if payload.get("response_schema"):
            return EffectOutcome.completed({"content": None, "data": dict(route)})
        media_calls.append(copy.deepcopy(payload))
        return EffectOutcome.completed({"content": None, "outputs": {"voice": [{"artifact_ref": AUDIO}]}, "artifact_ref": AUDIO, "audio_artifact": AUDIO})

    flow = managed_assistant_visualflow(agent_subflow())
    flow["id"] = "assistant_voice_probe"
    spec = compile_visualflow(flow)
    registry = rt.WorkflowRegistry()
    registry.register(spec)
    runtime = rt.Runtime(
        run_store=rt.InMemoryRunStore(),
        ledger_store=rt.InMemoryLedgerStore(),
        workflow_registry=registry,
        effect_handlers={EffectType.LLM_CALL: llm},
    )
    run_id = runtime.start(workflow=spec, vars={"prompt": "record a voice saying good morning", "provider": "t", "model": "t"})
    runtime.tick(workflow=spec, run_id=run_id, max_steps=60)
    return media_calls, runtime.get_state(run_id).output or {}


def test_the_router_may_choose_voice() -> None:
    assert "voice" in _ROUTER_SCHEMA["properties"]["mode"]["enum"]
    assert "voice" in _ROUTER_SYSTEM_PROMPT


def test_voice_speaks_the_routers_words_with_the_gateway_voice() -> None:
    calls, output = _run({"mode": "voice", "assistant_message": "Here it is.", "media_prompt": "Good morning, the coffee is ready."})
    assert len(calls) == 1
    call = calls[0]
    assert call["prompt"] == "Good morning, the coffee is ready."
    assert call["output"]["modality"] == "voice" and call["output"]["task"] == "tts"
    # Bare: no engine named, so the runtime merges the gateway's output.voice route.
    assert "provider" not in call["output"] and "model" not in call["output"]
    assert output.get("response") == "Here it is."


def test_sound_still_asks_for_a_sound_effect() -> None:
    calls, _ = _run({"mode": "sound", "assistant_message": "Here.", "media_prompt": "a door creaks", "seconds": None})
    assert calls and calls[0]["output"]["modality"] == "sound"

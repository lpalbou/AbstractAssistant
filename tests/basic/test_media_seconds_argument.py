"""R10.1 (2026-10-04): "a SFX laser gunshot of 3s" reaches the sound model as 3 seconds.

The router's structured answer carries a typed `seconds` argument (the model fills it; no code
reads durations out of the prompt). The workflow wires it into the sound node's output spec
(`duration_s`) and the music node's `duration_s` pin. Before, the schema had no length and the
SFX clip came back 30 s long.

Driven through the real runtime compiler and Runtime with a fake LLM handler that answers the
router like a model would and records the media call it then receives.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

import pytest

from abstractassistant.assistant_workflow import _ROUTER_SCHEMA, managed_assistant_visualflow

rt = pytest.importorskip("abstractruntime")
compile_visualflow = pytest.importorskip("abstractruntime.visualflow_compiler").compile_visualflow
from abstractruntime.core.models import EffectType  # noqa: E402
from abstractruntime.core.runtime import EffectOutcome  # noqa: E402


def _run(route: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Run the assistant flow once; the router answers `route`. Returns the media calls."""

    media_calls: List[Dict[str, Any]] = []

    def llm(run, effect, default_next_node: Optional[str]):
        payload = dict(effect.payload or {})
        if payload.get("response_schema"):
            return EffectOutcome.completed({"content": None, "data": dict(route)})
        media_calls.append(copy.deepcopy(payload))
        return EffectOutcome.completed({"content": None, "outputs": {}})

    flow = managed_assistant_visualflow()
    flow["id"] = "assistant_seconds_probe"
    spec = compile_visualflow(flow)
    registry = rt.WorkflowRegistry()
    registry.register(spec)
    runtime = rt.Runtime(
        run_store=rt.InMemoryRunStore(),
        ledger_store=rt.InMemoryLedgerStore(),
        workflow_registry=registry,
        effect_handlers={EffectType.LLM_CALL: llm},
    )
    run_id = runtime.start(workflow=spec, vars={"prompt": "generate a SFX laser gunshot of 3s", "provider": "t", "model": "t"})
    runtime.tick(workflow=spec, run_id=run_id, max_steps=60)
    return media_calls


def test_router_schema_declares_a_typed_seconds_argument() -> None:
    prop = _ROUTER_SCHEMA["properties"]["seconds"]
    assert prop["type"] == ["number", "null"]
    assert "seconds" in prop["description"]
    assert "seconds" not in _ROUTER_SCHEMA["required"]  # null/absent = engine default


def test_sound_route_seconds_reach_the_sound_output_spec() -> None:
    calls = _run({"mode": "sound", "assistant_message": "Generating.", "media_prompt": "laser gunshot", "seconds": 3})
    sound = [c for c in calls if (c.get("output") or {}).get("task") == "text_to_audio"]
    assert len(sound) == 1, calls
    assert sound[0]["output"]["duration_s"] == 3
    assert sound[0]["output"]["modality"] == "sound"
    assert sound[0]["prompt"] == "laser gunshot"


def test_sound_route_without_seconds_leaves_the_engine_default() -> None:
    calls = _run({"mode": "sound", "assistant_message": "Generating.", "media_prompt": "door slam", "seconds": None})
    sound = [c for c in calls if (c.get("output") or {}).get("task") == "text_to_audio"]
    assert len(sound) == 1, calls
    assert sound[0]["output"].get("duration_s") is None


def test_music_route_seconds_reach_the_music_output_spec() -> None:
    calls = _run({"mode": "music", "assistant_message": "Composing.", "media_prompt": "calm piano", "seconds": 45})
    music = [c for c in calls if (c.get("output") or {}).get("modality") == "music"]
    assert len(music) == 1, calls
    assert music[0]["output"]["duration_s"] == 45

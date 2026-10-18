"""Canonical router uses explicit text selection, then narrow runtime defaults."""
import copy
import json

import pytest

from agent_fixture import agent_subflow
from abstractassistant.assistant_workflow import managed_assistant_visualflow
from abstractruntime import Runtime, InMemoryRunStore, InMemoryLedgerStore, WorkflowRegistry
from abstractruntime.core.models import EffectType
from abstractruntime.core.runtime import EffectOutcome
from abstractruntime.visualflow_compiler import compile_visualflow


@pytest.mark.parametrize('selection,expected', [
    ({}, ('endpoint:default', 'default-model')),
    ({'provider': 'endpoint:selected', 'model': 'selected-model'}, ('endpoint:selected', 'selected-model')),
    ({'provider': None, 'model': None}, ('endpoint:default', 'default-model')),
])
def test_canonical_router_uses_explicit_selection_then_runtime(selection, expected):
    calls = []

    def llm(run, effect, next_node):
        calls.append(copy.deepcopy(effect.payload))
        if effect.payload.get('response_schema'):
            return EffectOutcome.completed({'data': {'mode': 'voice', 'media_prompt': 'Hello', 'assistant_message': 'Ready'}})
        return EffectOutcome.completed({'content': '', 'outputs': {}})

    graph = managed_assistant_visualflow(agent_subflow())
    graph["id"] = "canonical-router-test"
    spec = compile_visualflow(graph)
    registry = WorkflowRegistry()
    registry.register(spec)
    runtime = Runtime(run_store=InMemoryRunStore(), ledger_store=InMemoryLedgerStore(),
                      workflow_registry=registry, effect_handlers={EffectType.LLM_CALL: llm})
    run_id = runtime.start(workflow=spec, vars={'prompt': 'Speak hello', **selection,
        '_runtime': {'provider': 'endpoint:default', 'model': 'default-model', 'private_marker': 'DO-NOT-EXPOSE'}})
    runtime.tick(workflow=spec, run_id=run_id, max_steps=60)
    assert calls
    assert 'provider' in calls[0], calls[0]
    assert (calls[0]['provider'], calls[0]['model']) == expected
    assert 'DO-NOT-EXPOSE' not in json.dumps(calls)
    state = runtime.get_state(run_id)
    outputs = state.vars.get('_temp', {}).get('node_outputs', {})
    assert '_runtime' not in outputs['start']

"""Cache telemetry must stay separate from estimated provider usage."""

from abstractassistant.gateway.run_stats import observe_record, aggregate_run_stats
from abstractassistant.gateway.history_seed import _stats_are_richer
from abstractassistant.app import _assistant_footer_metrics


def _record(input_tokens, cached=None, new=None):
    result = {"usage": {"input_tokens": input_tokens, "output_tokens": 10}}
    if cached is not None:
        result["metadata"] = {"prompt_cache": {"cached_tokens": cached, "fed_tokens": new}}
    return {"status": "completed", "effect": {"type": "llm_call"}, "result": result}


def test_turn_cache_sums_across_subruns_and_weights_by_tokens():
    buckets = {}
    observe_record(buckets, run_id="root", rec=_record(1200, 0, 1000))
    observe_record(buckets, run_id="agent", rec=_record(11000, 9000, 1000))
    stats = aggregate_run_stats(buckets)
    assert stats["usage"]["input_tokens"] == 12200
    assert stats["prompt_cache"] == {"cached_tokens": 9000, "new_tokens": 2000, "measured_calls": 2}
    metrics = _assistant_footer_metrics({"metadata": {"_assistant_stats": stats}})
    cache = next(m for m in metrics if m["kind"] == "cache")
    assert cache["label"] == "82% reused"  # not the average of 0% and 90%
    tooltip = next(m for m in metrics if m["kind"] == "tokens_in")["tooltip"]
    assert "12,200" in tooltip and "9,000" in tooltip and "2,000" in tooltip
    assert "2 of 2" in tooltip and "Repeated context" in tooltip


def test_missing_cache_is_not_zero_and_partial_counts_are_labeled():
    buckets = {}
    observe_record(buckets, run_id="agent", rec=_record(1000, 700, 300))
    observe_record(buckets, run_id="agent", rec=_record(2000))
    stats = aggregate_run_stats(buckets)
    metrics = _assistant_footer_metrics({"metadata": {"_assistant_stats": stats}})
    cache = next(m for m in metrics if m["kind"] == "cache")
    assert cache["label"] == "Cache: partial"
    assert "1 of 2" in cache["tooltip"]
    # Invalid/incomplete telemetry is also unknown, not a cache miss.
    observe_record(buckets, run_id="agent", rec=_record(500, 10, None))
    assert aggregate_run_stats(buckets)["prompt_cache"]["measured_calls"] == 1


def test_no_cache_telemetry_is_explicit_and_old_history_can_be_enriched():
    buckets = {}
    observe_record(buckets, run_id="agent", rec=_record(1000))
    old = aggregate_run_stats(buckets)
    assert "prompt_cache" not in old
    metrics = _assistant_footer_metrics({"metadata": {"_assistant_stats": old}})
    assert "not reported" in metrics[0]["tooltip"]
    fresh = {**old, "prompt_cache": {"cached_tokens": 0, "new_tokens": 1000, "measured_calls": 1}}
    assert _stats_are_richer(fresh, old)
    assert not _stats_are_richer(old, fresh)
    metrics = _assistant_footer_metrics({"metadata": {"_assistant_stats": fresh}})
    assert next(m for m in metrics if m["kind"] == "cache")["label"] == "0% reused"

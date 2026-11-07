"""Why a run failed, in plain words.

The gateway reports a failed run's reason as text: the failed step's ``error``
in the run's replay view, or the run summary's ``error``. When an exception
caused it, that text is the runtime's serialisation of the exception chain,
``"<context>: <ExceptionType>: <message>"`` — for example
``"Effect failed after 3 attempts: SpeculationUnavailableError: The
openai-compatible provider has no native MTP adapter
(speculation.require_acceleration=True)"``. The gateway sends no separate
type or code field for these.

A failure is recognised by its exception TYPE only, read at the type's position
in that serialisation: the first ``": "``-separated part once the runtime's own
retry wrapper (``"Effect failed after N attempts"``, recognised by its fixed
words and a whole number) is set aside, and only when a message follows it. That
part must equal a known type name exactly. Nothing here reads the message's words
(no pattern over prose), and a known name elsewhere in the chain (a message that
quotes it, a wrapped cause) is not the type. An unknown type, or a reason with no
type, gets the short plain line; the raw reason always goes with it (the tooltip),
so nothing the gateway said is hidden.

The reason explained is the RUN's own (the palette's ``run_error`` from the worker:
the run summary's error), never an earlier step that may have recovered.
"""

from __future__ import annotations

from dataclasses import dataclass


GENERIC_FAILURE = "The run failed before it wrote a reply."

# Exception type → what it means for the person and what to do. Each entry is
# a type the gateway's runtime raises with a fixed meaning.
KNOWN_FAILURES = {
    # abstractcore.providers.speculation.SpeculationUnavailableError: the request
    # required MTP and the selected model or provider cannot do it. The requirement
    # comes from this app's MTP depth (a depth always requires the acceleration) OR
    # from the gateway's own default for the model (the console can store a strict
    # one), so "Gateway default" is not a fix: only Off is.
    "SpeculationUnavailableError": (
        "This model can't use the MTP speed-up (speculative decoding) this request asked for. "
        "In Settings → Models, set MTP depth to Off, or choose a model that supports it."
    ),
}


@dataclass(frozen=True)
class RunFailure:
    text: str  # what the conversation shows
    reason: str  # the gateway's own words, for the details tooltip
    error_type: str = ""  # the recognised exception type, "" when unknown


def _is_retry_wrapper(part: str) -> bool:
    """The runtime's own context, ``f"Effect failed after {n} attempts"``
    (abstractruntime core/runtime.py): fixed words around a whole number."""
    words = part.split(" ")
    return (
        len(words) == 5
        and words[:3] == ["Effect", "failed", "after"]
        and words[3].isdigit()
        and words[4] in {"attempt", "attempts"}
    )


def error_type_of(reason: str) -> str:
    """The known exception type at the type position of a serialised reason, or ""."""
    parts = str(reason or "").split(": ")
    while parts and _is_retry_wrapper(parts[0].strip()):
        parts = parts[1:]
    if len(parts) < 2:
        return ""  # no "<Type>: <message>" left: no type to read
    name = parts[0].strip()
    return name if name in KNOWN_FAILURES else ""


def explain_run_failure(reason: str) -> RunFailure:
    raw = " ".join(str(reason or "").split())
    kind = error_type_of(raw)
    if kind:
        return RunFailure(text=KNOWN_FAILURES[kind], reason=raw, error_type=kind)
    return RunFailure(text=GENERIC_FAILURE, reason=raw)


def failure_tooltip(failure: RunFailure) -> str:
    if not failure.reason:
        return failure.text
    return f"{failure.text}\n\nWhat the gateway reported: {failure.reason}"


__all__ = [
    "GENERIC_FAILURE",
    "KNOWN_FAILURES",
    "RunFailure",
    "error_type_of",
    "explain_run_failure",
    "failure_tooltip",
]

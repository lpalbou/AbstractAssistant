"""Why a run failed, in plain words.

The gateway reports a failed run's reason as text: the failed step's ``error``
in the run's replay view, or the run summary's ``error``. When an exception
caused it, that text is the runtime's serialisation of the exception chain,
``"<context>: <ExceptionType>: <message>"`` — for example
``"Effect failed after 3 attempts: SpeculationUnavailableError: The
openai-compatible provider has no native MTP adapter
(speculation.require_acceleration=True)"``. The gateway sends no separate
type or code field for these.

A failure is recognised by its exception TYPE only: one of the ``": "``
separated parts must be exactly a known type name. Nothing here reads the
message's words (no pattern over prose): an unknown type, or a reason with no
type in it, gets the short plain line, and the raw reason always goes with it
(the tooltip), so nothing the gateway said is hidden.
"""

from __future__ import annotations

from dataclasses import dataclass


GENERIC_FAILURE = "The run failed before it wrote a reply."

# Exception type → what it means for the person and what to do. Each entry is
# a type the gateway's runtime raises with a fixed meaning.
KNOWN_FAILURES = {
    # abstractcore.providers.speculation.SpeculationUnavailableError: the chat
    # request asked for MTP (Settings → Models, "MTP depth": a depth always
    # requires the acceleration) and the selected model or provider cannot do it.
    "SpeculationUnavailableError": (
        "This model can't use the MTP speed-up (speculative decoding) chosen in Settings. "
        "In Settings → Models, set MTP depth to Off or Gateway default, or choose a model that supports it."
    ),
}


@dataclass(frozen=True)
class RunFailure:
    text: str  # what the conversation shows
    reason: str  # the gateway's own words, for the details tooltip
    error_type: str = ""  # the recognised exception type, "" when unknown


def error_type_of(reason: str) -> str:
    """The known exception type named in a serialised reason, or ""."""
    for part in str(reason or "").split(": "):
        name = part.strip()
        if name in KNOWN_FAILURES:
            return name
    return ""


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

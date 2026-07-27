"""Pure planning helpers for future selective streaming conversion."""

from __future__ import annotations

from dataclasses import dataclass

from statconvert.streaming.capabilities import (
    FormatStreamingCapability,
    StreamingSupport,
    StreamingSuitability,
    get_streaming_capability,
)
from statconvert.streaming.errors import StreamingNotSupportedError


_FOUNDATION_FORMATS = {".csv", ".jsonl", ".ndjson"}


@dataclass(frozen=True)
class StreamingPlan:
    """Feasibility result without opening input or output files."""

    source: FormatStreamingCapability
    target: FormatStreamingCapability
    candidate: bool
    implemented: bool
    reasons: tuple[str, ...]

    def require_executable(self) -> None:
        """Reject execution until a later slice supplies backend implementations."""

        if self.implemented:
            return
        if ".json" in {self.source.extension, self.target.extension}:
            raise StreamingNotSupportedError(
                "Streaming conversion is not supported for JSON array files.",
                suggestion=(
                    "Use JSONL or NDJSON for streaming, or run without --stream."
                ),
            )
        raise StreamingNotSupportedError(
            "Streaming conversion is not supported for "
            f"{self.source.extension} -> {self.target.extension}.",
            suggestion=(
                "Streaming in 0.9.0 supports only CSV, JSONL, and NDJSON pairs. "
                "Run without --stream to use the normal in-memory conversion path."
            ),
        )


def build_streaming_plan(source: str, target: str) -> StreamingPlan:
    """Classify a pair for the CSV/line-delimited JSON foundation."""

    source_capability = get_streaming_capability(source)
    target_capability = get_streaming_capability(target)
    reasons: list[str] = []

    readable = source_capability.chunked_read in {
        StreamingSupport.POSSIBLE,
        StreamingSupport.SUPPORTED_NOW,
    }
    writable = target_capability.chunked_write in {
        StreamingSupport.POSSIBLE,
        StreamingSupport.SUPPORTED_NOW,
    }
    if not readable:
        reasons.append(
            f"{source_capability.extension} is not an approved initial chunked read."
        )
    if not writable:
        reasons.append(
            f"{target_capability.extension} is not an approved initial chunked write."
        )
    if source_capability.safe_initial_use is not StreamingSuitability.YES:
        reasons.append(
            f"{source_capability.extension} is not a safe initial streaming source."
        )
    if target_capability.safe_initial_use is not StreamingSuitability.YES:
        reasons.append(
            f"{target_capability.extension} is not a safe initial streaming target."
        )
    if source_capability.extension not in _FOUNDATION_FORMATS:
        reasons.append("The source is outside the 0.9.0b foundation scope.")
    if target_capability.extension not in _FOUNDATION_FORMATS:
        reasons.append("The target is outside the 0.9.0b foundation scope.")

    candidate = not reasons
    implemented = (
        candidate
        and source_capability.chunked_read is StreamingSupport.SUPPORTED_NOW
        and target_capability.chunked_write is StreamingSupport.SUPPORTED_NOW
    )
    if candidate and implemented:
        reasons.append("The pair has an internal 0.9.0b streaming execution path.")
    elif candidate:
        reasons.append("The pair is feasible but has no streaming execution path yet.")

    return StreamingPlan(
        source=source_capability,
        target=target_capability,
        candidate=candidate,
        implemented=implemented,
        reasons=tuple(reasons),
    )

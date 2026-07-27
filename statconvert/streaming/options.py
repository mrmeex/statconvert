"""Validated internal options for future chunked reads and writes."""

from dataclasses import dataclass


DEFAULT_STREAMING_CHUNK_SIZE = 100_000


def validate_chunk_size(value: int) -> int:
    """Return a positive row count or raise a stable validation error."""

    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("chunk_size must be a positive integer.")
    return value


@dataclass(frozen=True)
class ChunkedReadOptions:
    """Internal chunked-read controls; not a public CLI contract."""

    chunk_size: int

    def __post_init__(self) -> None:
        validate_chunk_size(self.chunk_size)


@dataclass(frozen=True)
class ChunkedWriteOptions:
    """Internal chunked-write controls; not a public CLI contract."""

    chunk_size: int

    def __post_init__(self) -> None:
        validate_chunk_size(self.chunk_size)

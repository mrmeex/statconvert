"""Backend-neutral chunk, writer, progress, and result structures."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from statconvert.dataset import Dataset


@dataclass(frozen=True)
class DatasetChunk:
    """One ordered row chunk represented by a normal Dataset."""

    dataset: Dataset
    index: int
    start_row: int
    rows: int
    total_rows: int | None = None

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("Chunk index must be zero or greater.")
        if self.start_row < 0:
            raise ValueError("Chunk start_row must be zero or greater.")
        if self.rows != self.dataset.rows:
            raise ValueError("Chunk rows must match dataset.rows.")
        if self.total_rows is not None and self.total_rows < self.start_row + self.rows:
            raise ValueError("Chunk total_rows cannot be smaller than its row range.")


class ChunkWriter(ABC):
    """Stateful backend-owned writer for transactional chunk output."""

    @abstractmethod
    def write_chunk(self, chunk: DatasetChunk) -> None:
        """Validate and append one chunk."""

    @abstractmethod
    def finalize(self) -> Path | None:
        """Commit the completed output and return its sidecar path."""

    @abstractmethod
    def abort(self) -> None:
        """Close and remove writer-owned temporary artifacts."""

    def __enter__(self) -> ChunkWriter:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.abort()


@dataclass(frozen=True)
class StreamingProgressEvent:
    """Deterministic business-layer progress for one completed chunk."""

    event_type: str
    chunk_index: int | None = None
    rows: int = 0
    cumulative_rows: int = 0
    total_rows: int | None = None


@dataclass(frozen=True)
class StreamingExecutionResult:
    """Summary of one successful internal streaming conversion."""

    source_path: Path
    target_path: Path
    source_extension: str
    target_extension: str
    chunk_size: int
    chunks_processed: int
    rows_processed: int
    completed: bool
    output_path: Path
    sidecar_path: Path | None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable result."""

        return {
            "source_path": str(self.source_path),
            "target_path": str(self.target_path),
            "source_extension": self.source_extension,
            "target_extension": self.target_extension,
            "chunk_size": self.chunk_size,
            "chunks_processed": self.chunks_processed,
            "rows_processed": self.rows_processed,
            "completed": self.completed,
            "output_path": str(self.output_path),
            "sidecar_path": (
                str(self.sidecar_path)
                if self.sidecar_path is not None
                else None
            ),
        }

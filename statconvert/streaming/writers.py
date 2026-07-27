"""Shared transactional lifecycle for backend-owned chunk writers."""

from __future__ import annotations

import os
import tempfile
from abc import abstractmethod
from pathlib import Path

from statconvert.dataset import Dataset
from statconvert.metadata.sidecar import sidecar_path
from statconvert.output_paths import validate_output_file_path
from statconvert.streaming.chunks import ChunkWriter, DatasetChunk
from statconvert.streaming.errors import StreamingWriteError
from statconvert.streaming.schema import StreamingSchemaGuard


class TransactionalChunkWriter(ChunkWriter):
    """Write chunks to a temporary sibling and commit only on success."""

    def __init__(
        self,
        target_path: str | Path,
        *,
        overwrite: bool = False,
        create_dirs: bool = False,
    ) -> None:
        self.target_path = validate_output_file_path(
            target_path,
            overwrite=overwrite,
            create_dirs=create_dirs,
        )
        self.schema = StreamingSchemaGuard()
        self.chunks_written = 0
        self.rows_written = 0
        self._metadata_dataset: Dataset | None = None
        self._committed = False
        self._finalized = False
        self._temporary_sidecars: set[Path] = set()
        self.temporary_path = self._create_temporary_sibling()

    def write_chunk(self, chunk: DatasetChunk) -> None:
        """Validate and append one chunk, cleaning temporary output on failure."""

        if self._finalized:
            raise StreamingWriteError("Cannot write a chunk after finalization.")
        try:
            self.schema.validate(chunk.dataset)
            self._write_dataset(
                chunk.dataset,
                first_chunk=self.chunks_written == 0,
            )
        except Exception:
            self.abort()
            raise

        if self._metadata_dataset is None:
            self._metadata_dataset = chunk.dataset.copy(deep=True)
        self.chunks_written += 1
        self.rows_written += chunk.rows

    def finalize(self) -> Path | None:
        """Commit data, then atomically create the final sidecar."""

        if self._finalized:
            raise StreamingWriteError("Streaming output is already finalized.")
        if self.chunks_written == 0 or self._metadata_dataset is None:
            self.abort()
            raise StreamingWriteError("Cannot finalize streaming output without chunks.")

        try:
            os.replace(self.temporary_path, self.target_path)
            self._committed = True
            self._finalized = True
        except OSError as exc:
            self.abort()
            raise StreamingWriteError(
                f"Could not commit streaming output: {self.target_path}. {exc}"
            ) from exc

        try:
            return self._commit_sidecar(self._metadata_dataset)
        except Exception as exc:
            self._cleanup_temporary_sidecars()
            raise StreamingWriteError(
                "Streaming data was committed successfully, but its metadata "
                f"sidecar could not be written: {self.target_path}. {exc}"
            ) from exc

    def abort(self) -> None:
        """Remove only writer-owned temporary artifacts."""

        if not self._committed:
            self.temporary_path.unlink(missing_ok=True)
        self._cleanup_temporary_sidecars()

    @abstractmethod
    def _write_dataset(self, dataset: Dataset, *, first_chunk: bool) -> None:
        """Append one validated dataset to the temporary output."""

    def _create_temporary_sibling(self) -> Path:
        parent = self.target_path.parent
        if parent == Path("."):
            parent = Path.cwd()
        handle = tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{self.target_path.name}.statconvert-",
            suffix=".tmp",
            dir=parent,
            delete=False,
        )
        path = Path(handle.name)
        handle.close()
        return path

    def _commit_sidecar(self, dataset: Dataset) -> Path:
        temporary_base = Path(f"{self.temporary_path}.metadata")
        temporary_sidecar = sidecar_path(temporary_base)
        self._temporary_sidecars.add(temporary_sidecar)
        dataset.write_sidecar(temporary_base)

        final_sidecar = sidecar_path(self.target_path)
        os.replace(temporary_sidecar, final_sidecar)
        self._temporary_sidecars.discard(temporary_sidecar)
        return final_sidecar

    def _cleanup_temporary_sidecars(self) -> None:
        for path in self._temporary_sidecars:
            path.unlink(missing_ok=True)
        self._temporary_sidecars.clear()

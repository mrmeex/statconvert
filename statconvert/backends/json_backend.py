from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd

from statconvert.backends.base import Backend
from statconvert.backends.capabilities import BackendCapabilities
from statconvert.dataset import Dataset
from statconvert.exceptions import ConversionError
from statconvert.metadata import build_basic_metadata
from statconvert.metadata.sidecar import read_sidecar, restore_metadata
from statconvert.streaming.chunks import ChunkWriter, DatasetChunk
from statconvert.streaming.errors import StreamingNotSupportedError
from statconvert.streaming.options import ChunkedReadOptions, ChunkedWriteOptions
from statconvert.streaming.writers import TransactionalChunkWriter


class JsonBackend(Backend):
    """
    JSON reader/writer backend.
    """

    name = "json"
    capabilities = BackendCapabilities(
        can_read=True,
        can_write=True,
        supports_custom_metadata=False,
        supports_multiple_tables=False,
    )

    write_chunk_rows = 10_000

    def iter_chunks(
        self,
        filename: str,
        options: ChunkedReadOptions,
        **kwargs: Any,
    ) -> Iterator[DatasetChunk]:
        """Yield JSONL/NDJSON records without enabling JSON-array streaming."""

        extension = Path(filename).suffix.lower()
        if extension not in {".jsonl", ".ndjson"}:
            raise StreamingNotSupportedError(
                "Chunked JSON reading supports only .jsonl and .ndjson files."
            )

        automatic_payload = read_sidecar(filename)
        metadata = {
            "file_type": extension,
            "lines": True,
            "backend": self.name,
        }
        read_options = {**kwargs, "lines": True}
        yielded = False
        try:
            with pd.read_json(
                filename,
                chunksize=options.chunk_size,
                **read_options,
            ) as reader:
                start_row = 0
                for index, dataframe in enumerate(reader):
                    yielded = True
                    dataset = self._chunk_dataset(
                        dataframe,
                        filename=filename,
                        metadata=metadata,
                        automatic_payload=automatic_payload,
                    )
                    yield DatasetChunk(
                        dataset=dataset,
                        index=index,
                        start_row=start_row,
                        rows=dataset.rows,
                    )
                    start_row += dataset.rows
        except ConversionError:
            raise
        except Exception as exc:
            raise ConversionError(
                f"Failed reading chunked JSON Lines file: {exc}"
            ) from exc

        if not yielded:
            dataframe = pd.DataFrame()
            dataset = self._chunk_dataset(
                dataframe,
                filename=filename,
                metadata=metadata,
                automatic_payload=automatic_payload,
            )
            yield DatasetChunk(
                dataset=dataset,
                index=0,
                start_row=0,
                rows=0,
            )

    def open_chunk_writer(
        self,
        filename: str,
        options: ChunkedWriteOptions,
        *,
        overwrite: bool = False,
        create_dirs: bool = False,
        **kwargs: Any,
    ) -> ChunkWriter:
        """Open a transactional JSONL/NDJSON chunk writer."""

        extension = Path(filename).suffix.lower()
        if extension not in {".jsonl", ".ndjson"}:
            raise StreamingNotSupportedError(
                "Chunked JSON writing supports only .jsonl and .ndjson files."
            )
        return _JsonLinesChunkWriter(
            filename,
            overwrite=overwrite,
            create_dirs=create_dirs,
            write_kwargs=kwargs,
        )


    def read(
        self,
        filename: str,
        **kwargs
    ) -> Dataset:
        """
        Read a JSON file into a Dataset.
        """

        try:
            extension = Path(filename).suffix.lower()
            lines_mode = extension in {".ndjson", ".jsonl"}

            read_options = {
                "lines": lines_mode,
            }
            read_options.update(kwargs)

            df = pd.read_json(
                filename,
                **read_options
            )

        except Exception as e:
            raise ConversionError(
                f"Failed reading JSON file: {e}"
            )


        metadata = {
            "file_type": extension,
            "lines": read_options["lines"],
            "backend": self.name,
        }


        restored = restore_metadata(
            dataframe=df,
            filename=filename,
            base_metadata=build_basic_metadata(
                dataframe=df,
                source_format=extension.lstrip("."),
                source_backend=self.name,
                raw_metadata=metadata,
            ),
        )

        return Dataset(
            dataframe=df,
            metadata=metadata,
            source_format=extension.lstrip("."),
            source_file=str(filename),
            normalized_metadata=restored.metadata,
            column_metadata=restored.column_metadata,
            metadata_provenance=restored.provenance,
        )


    def write(
        self,
        dataset: Dataset,
        filename: str,
        **kwargs
    ) -> None:
        """
        Write Dataset to JSON.
        """

        try:
            extension = Path(filename).suffix.lower()
            lines_mode = extension in {".ndjson", ".jsonl"}

            write_options = {
                "orient": "records",
                "force_ascii": False,
            }

            if lines_mode:
                write_options["lines"] = True
            else:
                write_options["indent"] = 2

            write_options.update(kwargs)

            if self._can_use_chunked_records(write_options):
                self._write_record_chunks(
                    dataset.dataframe,
                    filename,
                    write_options,
                )
            else:
                dataset.dataframe.to_json(
                    filename,
                    **write_options
                )
            dataset.write_sidecar(
                filename
            )

        except Exception as e:
            raise ConversionError(
                f"Failed writing JSON file: {e}"
            )

    @staticmethod
    def _can_use_chunked_records(write_options: dict[str, object]) -> bool:
        """Return whether options preserve the bounded records writer contract."""

        unsupported = {"compression", "storage_options"}.intersection(write_options)
        return (
            write_options.get("orient") == "records"
            and write_options.get("mode", "w") == "w"
            and not unsupported
        )

    def _write_record_chunks(
        self,
        dataframe: pd.DataFrame,
        filename: str,
        write_options: dict[str, object],
    ) -> None:
        """Write records in bounded pandas serialization chunks."""

        options = dict(write_options)
        lines_mode = bool(options.get("lines", False))
        indent = options.get("indent")
        with Path(filename).open("w", encoding="utf-8", newline="") as output:
            if lines_mode:
                for start in range(0, len(dataframe), self.write_chunk_rows):
                    chunk = dataframe.iloc[start : start + self.write_chunk_rows]
                    text = chunk.to_json(path_or_buf=None, **options)
                    if text:
                        output.write(text)
                        if not text.endswith("\n"):
                            output.write("\n")
                return

            output.write("[")
            wrote_records = False
            for start in range(0, len(dataframe), self.write_chunk_rows):
                chunk = dataframe.iloc[start : start + self.write_chunk_rows]
                text = chunk.to_json(path_or_buf=None, **options)
                if text is None:
                    continue
                body = text[1:-1].strip("\n")
                if not body.strip():
                    continue
                if wrote_records:
                    output.write(",\n" if indent else ",")
                elif indent:
                    output.write("\n")
                output.write(body)
                wrote_records = True
            if wrote_records and indent:
                output.write("\n")
            output.write("]")

    def _chunk_dataset(
        self,
        dataframe: pd.DataFrame,
        *,
        filename: str,
        metadata: dict[str, Any],
        automatic_payload,
    ) -> Dataset:
        extension = Path(filename).suffix.lower()
        restored = restore_metadata(
            dataframe=dataframe,
            filename=filename,
            automatic_payload=automatic_payload,
            base_metadata=build_basic_metadata(
                dataframe=dataframe,
                source_format=extension.lstrip("."),
                source_backend=self.name,
                raw_metadata=metadata,
            ),
        )
        return Dataset(
            dataframe=dataframe,
            metadata=dict(metadata),
            source_format=extension.lstrip("."),
            source_file=str(filename),
            normalized_metadata=restored.metadata,
            column_metadata=restored.column_metadata,
            metadata_provenance=restored.provenance,
        )


class _JsonLinesChunkWriter(TransactionalChunkWriter):
    """Transactional line-delimited JSON writer owned by the JSON backend."""

    def __init__(
        self,
        target_path: str | Path,
        *,
        overwrite: bool,
        create_dirs: bool,
        write_kwargs: dict[str, Any],
    ) -> None:
        self.write_kwargs = {
            **write_kwargs,
            "orient": "records",
            "lines": True,
            "force_ascii": False,
        }
        super().__init__(
            target_path,
            overwrite=overwrite,
            create_dirs=create_dirs,
        )

    def _write_dataset(self, dataset: Dataset, *, first_chunk: bool) -> None:
        del first_chunk
        if dataset.rows == 0:
            return
        try:
            text = dataset.dataframe.to_json(
                path_or_buf=None,
                **self.write_kwargs,
            )
            if not text:
                return
            with self.temporary_path.open(
                "a",
                encoding="utf-8",
                newline="",
            ) as output:
                output.write(text)
                if not text.endswith("\n"):
                    output.write("\n")
        except Exception as exc:
            raise ConversionError(
                f"Failed writing chunked JSON Lines file: {exc}"
            ) from exc

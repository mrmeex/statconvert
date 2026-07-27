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
from statconvert.streaming.options import ChunkedReadOptions, ChunkedWriteOptions
from statconvert.streaming.writers import TransactionalChunkWriter


class CSVBackend(Backend):
    """
    CSV reader/writer backend.
    """

    name = "csv"
    capabilities = BackendCapabilities(
        can_read=True,
        can_write=True,
    )

    def iter_chunks(
        self,
        filename: str,
        options: ChunkedReadOptions,
        **kwargs: Any,
    ) -> Iterator[DatasetChunk]:
        """Yield CSV rows through pandas without changing normal reads."""

        automatic_payload = read_sidecar(filename)
        metadata = {
            "delimiter": kwargs.get("sep", ","),
            "encoding": kwargs.get("encoding", "utf-8"),
        }
        try:
            with pd.read_csv(
                filename,
                chunksize=options.chunk_size,
                **kwargs,
            ) as reader:
                start_row = 0
                for index, dataframe in enumerate(reader):
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
                f"Failed reading chunked CSV file: {exc}"
            ) from exc

    def open_chunk_writer(
        self,
        filename: str,
        options: ChunkedWriteOptions,
        *,
        overwrite: bool = False,
        create_dirs: bool = False,
        **kwargs: Any,
    ) -> ChunkWriter:
        """Open a transactional CSV chunk writer."""

        return _CSVChunkWriter(
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
        Read CSV file into Dataset.
        """

        try:
            df = pd.read_csv(
                filename,
                **kwargs
            )

        except Exception as e:
            raise ConversionError(
                f"Failed reading CSV file: {e}"
            )


        metadata = {
            "delimiter": ",",
            "encoding": "utf-8",
        }


        restored = restore_metadata(
            dataframe=df,
            filename=filename,
            base_metadata=build_basic_metadata(
                dataframe=df,
                source_format="csv",
                source_backend=self.name,
                raw_metadata=metadata,
            ),
        )

        return Dataset(
            dataframe=df,
            metadata=metadata,
            source_format="csv",
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
    ):
        """
        Write Dataset to CSV.
        """

        try:
            dataset.dataframe.to_csv(
                filename,
                index=False,
                **kwargs
            )
            dataset.write_sidecar(
                filename
            )

        except Exception as e:
            raise ConversionError(
                f"Failed writing CSV file: {e}"
            )

    def _chunk_dataset(
        self,
        dataframe: pd.DataFrame,
        *,
        filename: str,
        metadata: dict[str, Any],
        automatic_payload,
    ) -> Dataset:
        restored = restore_metadata(
            dataframe=dataframe,
            filename=filename,
            automatic_payload=automatic_payload,
            base_metadata=build_basic_metadata(
                dataframe=dataframe,
                source_format="csv",
                source_backend=self.name,
                raw_metadata=metadata,
            ),
        )
        return Dataset(
            dataframe=dataframe,
            metadata=dict(metadata),
            source_format="csv",
            source_file=str(filename),
            normalized_metadata=restored.metadata,
            column_metadata=restored.column_metadata,
            metadata_provenance=restored.provenance,
        )


class _CSVChunkWriter(TransactionalChunkWriter):
    """Transactional CSV writer owned by the CSV backend."""

    def __init__(
        self,
        target_path: str | Path,
        *,
        overwrite: bool,
        create_dirs: bool,
        write_kwargs: dict[str, Any],
    ) -> None:
        self.write_kwargs = dict(write_kwargs)
        super().__init__(
            target_path,
            overwrite=overwrite,
            create_dirs=create_dirs,
        )

    def _write_dataset(self, dataset: Dataset, *, first_chunk: bool) -> None:
        try:
            dataset.dataframe.to_csv(
                self.temporary_path,
                mode="w" if first_chunk else "a",
                header=first_chunk,
                index=False,
                **self.write_kwargs,
            )
        except Exception as exc:
            raise ConversionError(
                f"Failed writing chunked CSV file: {exc}"
            ) from exc

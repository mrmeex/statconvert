from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.feather as feather
import pyarrow.parquet as parquet

from statconvert.backends.base import Backend
from statconvert.backends.capabilities import BackendCapabilities
from statconvert.dataset import Dataset
from statconvert.exceptions import ConversionError
from statconvert.metadata import build_basic_metadata
from statconvert.metadata.sidecar import (
    MetadataPayload,
    parse_payload_bytes,
    payload_bytes,
    restore_metadata,
)


STATCONVERT_METADATA_KEY = b"statconvert.metadata"


class ArrowBackend(Backend):
    """
    Apache Arrow reader/writer backend for Parquet and Feather.
    """

    name = "arrow"
    capabilities = BackendCapabilities(
        can_read=True,
        can_write=True,
        supports_custom_metadata=True,
        supports_compression=True,
        supports_streaming=False,
    )


    def read(
        self,
        filename: str,
        **kwargs
    ) -> Dataset:
        """
        Read an Arrow-backed file into a Dataset.
        """

        try:
            extension = Path(filename).suffix.lower()
            embedded_payload = self._read_embedded_payload(filename, extension)

            if extension == ".parquet":
                options = {
                    "engine": "pyarrow",
                }
                options.update(kwargs)

                df = pd.read_parquet(
                    filename,
                    **options
                )
                arrow_format = "parquet"

            elif extension == ".feather":
                df = pd.read_feather(
                    filename,
                    **kwargs
                )
                arrow_format = "feather"

            else:
                raise ValueError(
                    f"Unsupported Arrow format: {extension}"
                )

        except ConversionError:
            raise
        except Exception as e:
            raise ConversionError(
                f"Failed reading Arrow file: {e}"
            )


        metadata = {
            "file_type": extension,
            "backend": self.name,
            "arrow_format": arrow_format,
        }


        restored = restore_metadata(
            dataframe=df,
            filename=filename,
            embedded_payload=embedded_payload,
            base_metadata=build_basic_metadata(
                dataframe=df,
                source_format=arrow_format,
                source_backend=self.name,
                raw_metadata=metadata,
            ),
        )

        return Dataset(
            dataframe=df,
            metadata=metadata,
            source_format=arrow_format,
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
        Write Dataset to an Arrow-backed file.
        """

        try:
            extension = Path(filename).suffix.lower()
            embedded_payload = payload_bytes(dataset)

            if extension == ".parquet":
                options = {
                    "compression": "snappy",
                }
                options.update(kwargs)
                engine = options.pop("engine", "pyarrow")
                if engine != "pyarrow":
                    raise ConversionError(
                        "Embedded StatConvert metadata requires the pyarrow "
                        "Parquet engine."
                    )
                preserve_index = bool(options.pop("index", False))
                table = pa.Table.from_pandas(
                    dataset.dataframe,
                    preserve_index=preserve_index,
                )
                table = self._embed_payload(table, embedded_payload)
                parquet.write_table(
                    table,
                    filename,
                    **options
                )

            elif extension == ".feather":
                dataframe = dataset.dataframe
                index = dataframe.index
                if not (
                    isinstance(index, pd.RangeIndex)
                    and index.start == 0
                    and index.step == 1
                    and index.name is None
                ):
                    dataframe = dataframe.reset_index(
                        drop=True
                    )

                table = pa.Table.from_pandas(
                    dataframe,
                    preserve_index=False,
                )
                table = self._embed_payload(table, embedded_payload)
                feather.write_feather(
                    table,
                    filename,
                    **kwargs
                )

            else:
                raise ValueError(
                    f"Unsupported Arrow format: {extension}"
                )

            dataset.write_sidecar(
                filename
            )

        except ConversionError:
            raise
        except Exception as e:
            raise ConversionError(
                f"Failed writing Arrow file: {e}"
            )

    def _read_embedded_payload(
        self,
        filename: str,
        extension: str,
    ) -> MetadataPayload | None:
        """Read the namespaced payload without loading dataset values."""

        if extension == ".parquet":
            schema = parquet.read_schema(filename)
        elif extension == ".feather":
            with pa.memory_map(str(filename), "r") as source:
                schema = pa.ipc.open_file(source).schema
        else:
            return None

        raw_payload = (schema.metadata or {}).get(STATCONVERT_METADATA_KEY)
        if raw_payload is None:
            return None
        return parse_payload_bytes(
            raw_payload,
            source=f"embedded metadata in {filename}",
        )

    @staticmethod
    def _embed_payload(
        table: pa.Table,
        embedded_payload: bytes,
    ) -> pa.Table:
        """Add StatConvert metadata while retaining pandas/Arrow metadata."""

        schema_metadata = dict(table.schema.metadata or {})
        schema_metadata[STATCONVERT_METADATA_KEY] = embedded_payload
        return table.replace_schema_metadata(schema_metadata)

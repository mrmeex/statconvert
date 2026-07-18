from pathlib import Path

import pandas as pd

from statconvert.backends.base import Backend
from statconvert.backends.capabilities import BackendCapabilities
from statconvert.dataset import Dataset
from statconvert.exceptions import ConversionError
from statconvert.metadata import build_basic_metadata, metadata_from_sidecar


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


        column_metadata = Dataset.read_sidecar(filename)
        normalized_metadata = metadata_from_sidecar(
            build_basic_metadata(
                dataframe=df,
                source_format=extension.lstrip("."),
                source_backend=self.name,
                raw_metadata=metadata,
            ),
            column_metadata,
        )

        return Dataset(
            dataframe=df,
            metadata=metadata,
            source_format=extension.lstrip("."),
            source_file=str(filename),
            normalized_metadata=normalized_metadata,
            column_metadata=column_metadata,
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

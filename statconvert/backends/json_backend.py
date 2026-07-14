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

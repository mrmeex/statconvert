from pathlib import Path

import pandas as pd

from statconvert.backends.base import Backend
from statconvert.backends.capabilities import BackendCapabilities
from statconvert.dataset import Dataset
from statconvert.exceptions import ConversionError
from statconvert.metadata import build_basic_metadata, metadata_from_sidecar


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

        except Exception as e:
            raise ConversionError(
                f"Failed reading Arrow file: {e}"
            )


        metadata = {
            "file_type": extension,
            "backend": self.name,
            "arrow_format": arrow_format,
        }


        column_metadata = Dataset.read_sidecar(filename)
        normalized_metadata = metadata_from_sidecar(
            build_basic_metadata(
                dataframe=df,
                source_format=arrow_format,
                source_backend=self.name,
                raw_metadata=metadata,
            ),
            column_metadata,
        )

        return Dataset(
            dataframe=df,
            metadata=metadata,
            source_format=arrow_format,
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
        Write Dataset to an Arrow-backed file.
        """

        try:
            extension = Path(filename).suffix.lower()

            if extension == ".parquet":
                options = {
                    "engine": "pyarrow",
                    "index": False,
                    "compression": "snappy",
                }
                options.update(kwargs)

                dataset.dataframe.to_parquet(
                    filename,
                    **options
                )

            elif extension == ".feather":
                dataframe = dataset.dataframe.reset_index(
                    drop=True
                )

                dataframe.to_feather(
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

        except Exception as e:
            raise ConversionError(
                f"Failed writing Arrow file: {e}"
            )

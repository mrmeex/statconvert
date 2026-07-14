from statconvert.backends.base import Backend
from statconvert.backends.capabilities import BackendCapabilities

import pandas as pd

from statconvert.dataset import Dataset
from statconvert.exceptions import ConversionError
from statconvert.metadata import build_basic_metadata, metadata_from_sidecar


class CSVBackend(Backend):
    """
    CSV reader/writer backend.
    """

    name = "csv"
    capabilities = BackendCapabilities(
        can_read=True,
        can_write=True,
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


        column_metadata = Dataset.read_sidecar(filename)
        normalized_metadata = metadata_from_sidecar(
            build_basic_metadata(
                dataframe=df,
                source_format="csv",
                source_backend=self.name,
                raw_metadata=metadata,
            ),
            column_metadata,
        )

        return Dataset(
            dataframe=df,
            metadata=metadata,
            source_format="csv",
            source_file=str(filename),
            normalized_metadata=normalized_metadata,
            column_metadata=column_metadata,
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

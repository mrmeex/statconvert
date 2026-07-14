from pathlib import Path

import pandas as pd

from statconvert.backends.base import Backend
from statconvert.backends.capabilities import BackendCapabilities
from statconvert.backends.objects import (
    DatasetObjectInfo,
    dataset_objects_from_names,
    resolve_object_selector,
)
from statconvert.dataset import Dataset
from statconvert.exceptions import (
    AmbiguousObjectError,
    ConversionError,
    ObjectNotFoundError,
)
from statconvert.metadata import build_basic_metadata, metadata_from_sidecar


class ODSBackend(Backend):
    """
    OpenDocument Spreadsheet reader/writer backend.
    """

    name = "ods"
    capabilities = BackendCapabilities(
        can_read=True,
        can_write=True,
        supports_multiple_sheets=True,
        is_container=True,
        object_selection=True,
        object_kind="sheet",
    )


    def read_object(
        self,
        path: Path,
        object_selector: str,
    ) -> Dataset:
        """Read one sheet through the backend-neutral selector."""

        return self.read(
            str(path),
            object_selector=object_selector,
        )


    def list_objects(self, path: Path) -> list[DatasetObjectInfo]:
        """List ODS sheets without loading their data."""

        self._extension(str(path))
        try:
            with pd.ExcelFile(path, engine="odf") as workbook:
                return dataset_objects_from_names(
                    workbook.sheet_names,
                    kind="sheet",
                )
        except Exception as exc:
            raise ConversionError(
                f"Failed listing ODS workbook sheets: {exc}"
            ) from None


    def read(
        self,
        filename: str,
        *,
        object_selector: str | None = None,
        **kwargs
    ) -> Dataset:
        """
        Read an ODS file into a Dataset.
        """

        try:
            extension = self._extension(
                filename
            )
            sheet_name = kwargs.pop("sheet_name", None)
            if sheet_name is not None and object_selector is not None:
                raise ConversionError(
                    "Use object_selector or sheet_name, not both."
                )

            selector = object_selector
            if sheet_name is not None:
                selector = str(sheet_name)
            selected = resolve_object_selector(
                self.list_objects(Path(filename)),
                selector,
                path=filename,
                object_label="Sheet",
            )
            options = {
                "engine": "odf",
                "sheet_name": selected.name,
            }
            options.update(kwargs)

            df = pd.read_excel(
                filename,
                **options
            )

        except (ConversionError, ObjectNotFoundError, AmbiguousObjectError):
            raise

        except Exception as exc:
            raise ConversionError(
                f"Failed reading ODS file: {exc}"
            ) from None


        metadata = {
            "backend": self.name,
            "file_type": extension,
            "sheet_name": (
                sheet_name
                if sheet_name is not None
                else selected.name if object_selector is not None else 0
            ),
            "selected_object": selected.name,
            "sheet_index": selected.index,
            "engine": "odf",
        }


        column_metadata = Dataset.read_sidecar(filename)
        normalized_metadata = metadata_from_sidecar(
            build_basic_metadata(
                dataframe=df,
                source_format="ods",
                source_backend=self.name,
                raw_metadata=metadata,
            ),
            column_metadata,
        )

        return Dataset(
            dataframe=df,
            metadata=metadata,
            source_format="ods",
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
        Write Dataset to ODS.
        """

        try:
            self._extension(
                filename
            )
            options = {
                "engine": "odf",
                "index": False,
                "sheet_name": "Sheet1",
            }
            options.update(kwargs)

            dataset.dataframe.to_excel(
                filename,
                **options
            )
            dataset.write_sidecar(
                filename
            )

        except Exception as e:
            raise ConversionError(
                f"Failed writing ODS file: {e}"
            )


    def _extension(
        self,
        filename: str
    ) -> str:
        """
        Return normalized ODS file extension.
        """

        extension = Path(filename).suffix.lower()

        if extension != ".ods":
            raise ValueError(
                f"Unsupported ODS format: {extension}"
            )

        return extension

from statconvert.backends.base import Backend
from statconvert.backends.capabilities import BackendCapabilities
from statconvert.backends.excel_constraints import (
    XLS_MAX_COLUMNS,
    XLS_MAX_DATA_ROWS,
    validate_excel_sheet_name,
)
from statconvert.backends.objects import (
    DatasetObjectInfo,
    dataset_objects_from_names,
    resolve_object_selector,
)

from importlib.util import find_spec
from datetime import date, datetime
from numbers import Number
from pathlib import Path
from typing import Any

import pandas as pd

from statconvert.dataset import Dataset
from statconvert.exceptions import ConversionError
from statconvert.metadata import build_basic_metadata, metadata_from_sidecar


class ExcelBackend(Backend):
    """
    Excel reader/writer backend.
    """

    name = "excel"
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
        """List workbook sheets without loading their data."""

        engine = self._read_engine(path)
        try:
            with pd.ExcelFile(path, engine=engine) as workbook:
                return dataset_objects_from_names(
                    workbook.sheet_names,
                    kind="sheet",
                )
        except ConversionError:
            raise
        except Exception as exc:
            raise ConversionError(
                f"Failed listing Excel workbook sheets: {exc}"
            ) from None


    def read(
        self,
        filename: str,
        sheet_name: str | int | None = None,
        *,
        object_selector: str | None = None,
        **kwargs,
    ) -> Dataset:
        """
        Read an Excel file into a Dataset.
        """

        path = Path(filename)
        if sheet_name is not None and object_selector is not None:
            raise ConversionError(
                "Use object_selector or sheet_name, not both."
            )

        selector = object_selector
        if sheet_name is not None:
            selector = str(sheet_name)

        selected = resolve_object_selector(
            self.list_objects(path),
            selector,
            path=path,
            object_label="Sheet",
        )
        engine = self._read_engine(path)

        try:
            df = pd.read_excel(
                filename,
                sheet_name=selected.name,
                engine=engine,
                **kwargs,
            )

        except Exception as exc:
            raise ConversionError(
                f"Failed reading Excel file: {exc}"
            ) from None


        metadata = {
            "sheet_name": (
                sheet_name
                if sheet_name is not None
                else selected.name if object_selector is not None else 0
            ),
            "selected_object": selected.name,
            "sheet_index": selected.index,
            "file_type": path.suffix.lower(),
        }


        column_metadata = Dataset.read_sidecar(filename)
        normalized_metadata = metadata_from_sidecar(
            build_basic_metadata(
                dataframe=df,
                source_format="excel",
                source_backend=self.name,
                raw_metadata=metadata,
            ),
            column_metadata,
        )

        return Dataset(
            dataframe=df,
            metadata=metadata,
            source_format="excel",
            source_file=filename,
            normalized_metadata=normalized_metadata,
            column_metadata=column_metadata,
        )


    def _read_engine(self, path: Path) -> str:
        """Return the installed pandas engine for an Excel workbook."""

        extension = path.suffix.lower()
        if extension == ".xlsx":
            return "openpyxl"
        if extension == ".xls":
            if find_spec("xlrd") is None:
                raise ConversionError(
                    "Reading .xls requires the 'xlrd' dependency. "
                    "Reinstall StatConvert or convert the workbook to .xlsx."
                )
            return "xlrd"
        raise ConversionError(
            f"Unsupported Excel format: {extension or '<none>'}"
        )


    def write(
        self,
        dataset: Dataset,
        filename: str,
        sheet_name: str = "Sheet1",
        *,
        object_selector: str | None = None,
    ) -> None:
        """
        Write Dataset to Excel.
        """

        if object_selector is not None and sheet_name != "Sheet1":
            raise ConversionError(
                "Use object_selector or sheet_name, not both."
            )
        output_sheet = object_selector or sheet_name
        try:
            validate_excel_sheet_name(output_sheet)
        except ValueError as exc:
            raise ConversionError(str(exc)) from None

        extension = Path(filename).suffix.lower()
        try:
            if extension == ".xlsx":
                self._write_xlsx(dataset, filename, output_sheet)
            elif extension == ".xls":
                self._write_xls(dataset, filename, output_sheet)
            else:
                raise ConversionError(
                    f"Writing {extension or 'this Excel format'} is not supported."
                )
            dataset.write_sidecar(filename)
        except ConversionError:
            raise
        except Exception as exc:
            raise ConversionError(
                f"Failed writing Excel file: {exc}"
            ) from None


    def _write_xlsx(
        self,
        dataset: Dataset,
        filename: str,
        sheet_name: str,
    ) -> None:
        """Write modern OOXML through the existing xlsxwriter path."""

        dataset.dataframe.to_excel(
            filename,
            sheet_name=sheet_name,
            index=False,
            engine="xlsxwriter",
        )


    def _write_xls(
        self,
        dataset: Dataset,
        filename: str,
        sheet_name: str,
    ) -> None:
        """Write a genuine legacy BIFF workbook with xlwt."""

        if find_spec("xlwt") is None:
            raise ConversionError(
                "Writing .xls requires dependency 'xlwt'. "
                "Reinstall StatConvert to restore format dependencies."
            )
        self._validate_xls_size(dataset)

        import xlwt

        workbook = xlwt.Workbook()
        worksheet = workbook.add_sheet(sheet_name)
        date_style = xlwt.easyxf(num_format_str="YYYY-MM-DD")
        datetime_style = xlwt.easyxf(num_format_str="YYYY-MM-DD HH:MM:SS")

        for column_index, column in enumerate(dataset.dataframe.columns):
            worksheet.write(0, column_index, self._xls_cell_value(column))

        for row_index, row in enumerate(
            dataset.dataframe.itertuples(index=False, name=None),
            start=1,
        ):
            for column_index, value in enumerate(row):
                cell_value, style = self._xls_cell(value, date_style, datetime_style)
                if style is None:
                    worksheet.write(row_index, column_index, cell_value)
                else:
                    worksheet.write(row_index, column_index, cell_value, style)

        workbook.save(filename)


    def _validate_xls_size(self, dataset: Dataset) -> None:
        """Reject datasets that cannot fit in one header-bearing XLS sheet."""

        if dataset.rows > XLS_MAX_DATA_ROWS:
            raise ConversionError(
                f"Writing .xls is limited to {XLS_MAX_DATA_ROWS:,} data rows "
                "because row 1 is used for headers. Use .xlsx for larger data."
            )
        if len(dataset.columns) > XLS_MAX_COLUMNS:
            raise ConversionError(
                f"Writing .xls is limited to {XLS_MAX_COLUMNS} columns. "
                "Use .xlsx for wider data."
            )


    def _xls_cell(
        self,
        value: Any,
        date_style: Any,
        datetime_style: Any,
    ) -> tuple[Any, Any | None]:
        """Normalize one pandas/Python scalar and its optional xlwt style."""

        if self._is_missing(value):
            return "", None
        if isinstance(value, pd.Timestamp):
            value = value.to_pydatetime()
        if isinstance(value, datetime):
            if value.tzinfo is not None and value.utcoffset() is not None:
                return value.isoformat(), None
            return value, datetime_style
        if isinstance(value, date):
            return value, date_style
        return self._xls_cell_value(value), None


    def _xls_cell_value(self, value: Any) -> Any:
        """Return a scalar accepted safely by xlwt."""

        if self._is_missing(value):
            return ""
        if isinstance(value, bool):
            return value
        if isinstance(value, complex):
            return str(value)
        if isinstance(value, Number):
            if hasattr(value, "item"):
                value = value.item()
            return value if isinstance(value, int) else float(value)
        if isinstance(value, str):
            return value
        return str(value)


    def _is_missing(self, value: Any) -> bool:
        """Return whether a scalar is a pandas-style missing value."""

        try:
            missing = pd.isna(value)
        except (TypeError, ValueError):
            return False
        try:
            return bool(missing)
        except (TypeError, ValueError):
            return False

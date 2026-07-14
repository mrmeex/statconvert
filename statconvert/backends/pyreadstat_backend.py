from statconvert.backends.base import Backend
from statconvert.backends.capabilities import BackendCapabilities

from typing import Any

import pandas as pd
import pyreadstat

from statconvert.dataset import ColumnMetadata, Dataset
from statconvert.exceptions import ConversionError
from statconvert.metadata import (
    column_labels_from_metadata,
    display_widths_from_metadata,
    missing_ranges_from_metadata,
    missing_values_from_metadata,
    metadata_from_pyreadstat,
    variable_value_labels_from_metadata,
)


class PyReadstatBackend(Backend):
    """
    Backend for SPSS, Stata and SAS statistical files.
    """

    name = "pyreadstat"
    capabilities = BackendCapabilities(
        can_read=True,
        can_write=True,
        supports_variable_labels=True,
        supports_value_labels=True,
        supports_missing_values=True,
        supports_display_formats=True,
        supports_measurement_levels=True,
        supports_custom_metadata=True,
        supports_compression=False,
    )


    def _read_file(
        self,
        filename: str,
        extension: str,
        **kwargs
    ):
        """
        Read a file with the matching pyreadstat reader.
        """

        if extension in ("sav", "zsav"):
            return pyreadstat.read_sav(
                filename,
                **kwargs
            )

        if extension == "por":
            return pyreadstat.read_por(
                filename,
                **kwargs
            )

        if extension == "dta":
            return pyreadstat.read_dta(
                filename,
                **kwargs
            )

        if extension == "sas7bdat":
            return pyreadstat.read_sas7bdat(
                filename,
                **kwargs
            )

        if extension == "xpt":
            return pyreadstat.read_xport(
                filename,
                **kwargs
            )

        raise ValueError(
            f"Unsupported statistical format: {extension}"
        )


    def _should_retry_without_datetime_conversion(
        self,
        error: Exception,
        kwargs: dict
    ) -> bool:
        """
        Return whether pyreadstat should retry without datetime conversion.
        """

        if kwargs.get(
            "disable_datetime_conversion"
        ):
            return False

        message = str(error).lower()

        return (
            "string type" in message
            and "date type" in message
        )


    def _build_column_metadata(
        self,
        dataset,
        meta,
        source_format: str
    ) -> dict[str, ColumnMetadata]:
        """
        Build format-independent column metadata from pyreadstat metadata.
        """

        labels = getattr(
            meta,
            "column_names_to_labels",
            {}
        ) or {}
        value_labels = getattr(
            meta,
            "variable_value_labels",
            {}
        ) or {}
        original_formats = getattr(
            meta,
            "original_variable_types",
            {}
        ) or {}
        readstat_types = getattr(
            meta,
            "readstat_variable_types",
            {}
        ) or {}
        display_width = getattr(
            meta,
            "variable_display_width",
            {}
        ) or {}
        alignment = getattr(
            meta,
            "variable_alignment",
            {}
        ) or {}
        missing_ranges = getattr(
            meta,
            "missing_ranges",
            {}
        ) or {}
        missing_user_values = getattr(
            meta,
            "missing_user_values",
            {}
        ) or {}

        column_metadata = {}

        for column in dataset.columns:
            name = str(column)
            original_format = original_formats.get(
                name
            )
            column_value_labels = value_labels.get(
                name,
                {}
            )

            column_metadata[name] = ColumnMetadata(
                name=name,
                label=labels.get(name),
                physical_type=str(dataset[column].dtype),
                logical_type=self._infer_logical_type(
                    dataset[column],
                    dataset[column].dtype,
                    original_format,
                    readstat_types.get(name),
                    column_value_labels,
                ),
                source_format=source_format,
                original_format=original_format,
                value_labels=column_value_labels,
                missing_values=self._column_missing_values(
                    name,
                    missing_ranges,
                    missing_user_values,
                ),
                display_width=display_width.get(name),
                alignment=alignment.get(name),
                readstat_variable_type=readstat_types.get(name),
            )

        return column_metadata


    def _infer_logical_type(
        self,
        series,
        dtype,
        original_format,
        readstat_type,
        value_labels
    ) -> str:
        """
        Infer logical type from metadata first, then pandas dtype.
        """

        format_name = str(
            original_format or ""
        ).lower()

        if self._is_datetime_format(
            format_name
        ):
            return "datetime"

        if self._is_date_format(
            format_name
        ):
            return "date"

        if value_labels and not pd.api.types.is_string_dtype(
            dtype
        ):
            return "labelled"

        if readstat_type == "string" or pd.api.types.is_string_dtype(
            dtype
        ):
            return "string"

        if pd.api.types.is_integer_dtype(
            dtype
        ):
            return "integer"

        if (
            pd.api.types.is_float_dtype(
                dtype
            )
            and self._is_integer_format(
                format_name
            )
            and self._series_is_whole_number(
                series
            )
        ):
            return "integer"

        if pd.api.types.is_float_dtype(
            dtype
        ):
            return "float"

        if pd.api.types.is_datetime64_any_dtype(
            dtype
        ):
            return "datetime"

        return "unknown"


    def _series_is_whole_number(
        self,
        series
    ) -> bool:
        """
        Return whether all non-missing values are whole numbers.
        """

        numeric = pd.to_numeric(
            series,
            errors="coerce"
        )

        if numeric.isna().sum() > series.isna().sum():
            return False

        non_missing = numeric.dropna()

        if non_missing.empty:
            return False

        return bool(
            (
                non_missing % 1 == 0
            ).all()
        )


    def _is_integer_format(
        self,
        format_name: str
    ) -> bool:
        """
        Return whether a numeric display format has no decimals.
        """

        if not format_name:
            return False

        return (
            (
                format_name.startswith("f")
                and format_name.endswith(".0")
            )
            or (
                format_name.startswith("%")
                and ".0" in format_name
            )
        )


    def _is_date_format(
        self,
        format_name: str
    ) -> bool:
        """
        Return whether a readstat format represents a date.
        """

        date_formats = (
            "date",
            "adate",
            "edate",
            "jdate",
            "sdate",
            "qyr",
            "moyr",
            "wkyr",
            "%td",
            "%tw",
            "%tm",
            "%tq",
            "%th",
            "%ty",
        )

        return any(
            token in format_name
            for token in date_formats
        )


    def _is_datetime_format(
        self,
        format_name: str
    ) -> bool:
        """
        Return whether a readstat format represents a datetime.
        """

        datetime_formats = (
            "datetime",
            "dt",
            "%tc",
            "%tC".lower(),
        )

        return any(
            token in format_name
            for token in datetime_formats
        )


    def _column_missing_values(
        self,
        name: str,
        missing_ranges: dict,
        missing_user_values: dict
    ):
        """
        Return missing value metadata for one column.
        """

        values = {}

        if name in missing_ranges:
            values["ranges"] = missing_ranges[name]

        if name in missing_user_values:
            values["user_values"] = missing_user_values[name]

        return values or None


    def _column_labels(
        self,
        dataset: Dataset
    ) -> dict[str, str]:
        """
        Return column labels for writing.
        """

        return {
            name: column.label
            for name, column in dataset.column_metadata.items()
            if column.label
        }


    def _metadata_write_options(
        self,
        dataset: Dataset,
        include_value_labels: bool = True
    ) -> dict[str, Any]:
        """
        Return metadata write options from normalized Dataset metadata.
        """

        options: dict[str, Any] = {}

        column_labels = column_labels_from_metadata(
            dataset
        )

        if column_labels:
            options["column_labels"] = column_labels

        if include_value_labels:
            variable_value_labels = variable_value_labels_from_metadata(
                dataset
            )

            if variable_value_labels:
                options["variable_value_labels"] = variable_value_labels

        return options


    def _value_labels(
        self,
        dataset: Dataset
    ) -> dict:
        """
        Return value labels for writing.
        """

        return {
            name: column.value_labels
            for name, column in dataset.column_metadata.items()
            if column.value_labels
        }


    def _missing_ranges(
        self,
        dataset: Dataset
    ) -> dict:
        """
        Return SPSS missing ranges for writing.
        """

        return missing_ranges_from_metadata(dataset)


    def _missing_user_values(
        self,
        dataset: Dataset
    ) -> dict:
        """
        Return Stata missing user values for writing.
        """

        return missing_values_from_metadata(dataset)


    def _display_widths(
        self,
        dataset: Dataset
    ) -> dict[str, int]:
        """
        Return variable display widths for writing.
        """

        return display_widths_from_metadata(dataset)


    def _variable_formats(
        self,
        dataset: Dataset,
        target_format: str
    ) -> dict[str, str]:
        """
        Return variable formats supported by the target format.
        """

        normalized_formats = dataset.display_formats()
        formats = {}

        for name, column in dataset.column_metadata.items():
            normalized_format = normalized_formats.get(name)
            format_matches_target = (
                target_format == "dta" and str(normalized_format).startswith("%")
            ) or (
                target_format in {"sav", "zsav", "xpt"}
                and normalized_format
                and not str(normalized_format).startswith("%")
                and normalized_format not in {"date", "datetime"}
            )
            if format_matches_target:
                formats[name] = normalized_format
                continue
            variable_format = self._format_for_target(
                column,
                target_format
            )

            if variable_format:
                formats[name] = variable_format

        return formats


    def _format_for_target(
        self,
        column: ColumnMetadata,
        target_format: str
    ) -> str | None:
        """
        Convert logical type metadata into a target-specific format string.
        """

        original_format = column.original_format

        if target_format == "dta":
            if original_format and str(
                original_format
            ).startswith("%"):
                return original_format

            if column.logical_type == "date":
                return "%td"

            if column.logical_type == "datetime":
                return "%tc"

            return None

        if target_format in {
            "sav",
            "zsav",
            "xpt",
        }:
            if original_format and not str(
                original_format
            ).startswith("%"):
                return original_format

            if column.logical_type == "date":
                return "DATE10"

            if column.logical_type == "datetime":
                return "DATETIME20"

            if column.logical_type == "integer":
                return "F8.0"

        return None


    def _dataframe_for_write(
        self,
        dataset: Dataset
    ) -> pd.DataFrame:
        """
        Return a copy coerced according to logical metadata for writing.
        """

        dataframe = dataset.dataframe.copy()

        for name, column in dataset.column_metadata.items():
            if name not in dataframe.columns:
                continue

            if column.logical_type == "integer":
                dataframe[name] = self._as_integer_series(
                    dataframe[name]
                )

            elif (
                column.logical_type == "labelled"
                and self._value_labels_are_integer_like(
                    column.value_labels
                )
            ):
                dataframe[name] = self._as_integer_series(
                    dataframe[name]
                )

        return dataframe


    def _as_integer_series(
        self,
        series
    ):
        """
        Convert a whole-number series to a nullable integer series.
        """

        numeric = pd.to_numeric(
            series,
            errors="coerce"
        )

        if numeric.isna().sum() > series.isna().sum():
            return series

        non_missing = numeric.dropna()

        if not (
            non_missing % 1 == 0
        ).all():
            return series

        if numeric.isna().any():
            return numeric.astype(
                "Int64"
            )

        return numeric.astype(
            "int64"
        )


    def _value_labels_are_integer_like(
        self,
        value_labels: dict
    ) -> bool:
        """
        Return whether all value label keys represent whole numbers.
        """

        if not value_labels:
            return False

        for value in value_labels:
            try:
                if float(value) % 1 != 0:
                    return False

            except (TypeError, ValueError):
                return False

        return True


    def read(
        self,
        filename: str,
        **kwargs
    ) -> Dataset:
        """
        Read a statistical file into a Dataset.
        """

        datetime_conversion_disabled = bool(
            kwargs.get(
                "disable_datetime_conversion"
            )
        )

        try:
            extension = str(filename).lower().split(".")[-1]

            df, meta = self._read_file(
                filename,
                extension,
                **kwargs
            )

        except Exception as e:
            if self._should_retry_without_datetime_conversion(
                e,
                kwargs
            ):
                try:
                    retry_kwargs = {
                        **kwargs,
                        "disable_datetime_conversion": True,
                    }

                    df, meta = self._read_file(
                        filename,
                        extension,
                        **retry_kwargs
                    )
                    datetime_conversion_disabled = True

                except Exception as retry_error:
                    raise ConversionError(
                        f"Failed reading {filename}: {retry_error}"
                    )

            else:
                raise ConversionError(
                    f"Failed reading {filename}: {e}"
                )


        metadata = {
            "pyreadstat": meta
        }

        if datetime_conversion_disabled:
            metadata["datetime_conversion_disabled"] = True


        return Dataset(
            dataframe=df,
            metadata=metadata,
            source_format=extension,
            source_file=str(filename),
            normalized_metadata=metadata_from_pyreadstat(
                dataframe=df,
                pyreadstat_metadata=meta,
                source_format=extension,
                source_backend=self.name,
            ),
            column_metadata=self._build_column_metadata(
                df,
                meta,
                extension,
            ),
        )


    def write(
        self,
        dataset: Dataset,
        filename: str,
        **kwargs
    ):
        """
        Write a Dataset to a statistical file.
        """

        try:
            extension = str(filename).lower().split(".")[-1]


            variable_format = self._variable_formats(
                dataset,
                extension,
            )
            missing_ranges = self._missing_ranges(
                dataset
            )
            missing_user_values = self._missing_user_values(
                dataset
            )
            variable_display_width = self._display_widths(
                dataset
            )
            dataframe = self._dataframe_for_write(
                dataset
            )


            if extension == "sav":
                write_options = self._metadata_write_options(
                    dataset
                )

                if variable_format:
                    write_options["variable_format"] = variable_format

                if missing_ranges:
                    write_options["missing_ranges"] = missing_ranges

                if variable_display_width:
                    write_options["variable_display_width"] = variable_display_width

                write_options.update(kwargs)

                pyreadstat.write_sav(
                    dataframe,
                    filename,
                    **write_options
                )


            elif extension == "dta":
                write_options = self._metadata_write_options(
                    dataset
                )

                if variable_format:
                    write_options["variable_format"] = variable_format

                if missing_user_values:
                    write_options["missing_user_values"] = missing_user_values

                write_options.update(kwargs)

                pyreadstat.write_dta(
                    dataframe,
                    filename,
                    **write_options
                )


            elif extension == "xpt":
                write_options = {
                    "table_name": "DATA",
                }

                write_options.update(
                    self._metadata_write_options(
                        dataset,
                        include_value_labels=False,
                    )
                )

                if variable_format:
                    write_options["variable_format"] = variable_format

                write_options.update(kwargs)

                pyreadstat.write_xport(
                    dataframe,
                    filename,
                    **write_options
                )


            else:
                raise ValueError(
                    f"Cannot write statistical format: {extension}"
                )


        except Exception as e:
            raise ConversionError(
                f"Failed writing {filename}: {e}"
            )

from __future__ import annotations

import copy as copy_module
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
import json
from pathlib import Path
from typing import Any

import pandas as pd

from statconvert.metadata import (
    DatasetMetadata,
    VariableMetadata,
    build_basic_metadata,
    metadata_from_pyreadstat,
    variable_metadata_from_legacy,
)


@dataclass
class ColumnMetadata:
    """
    Format-independent metadata for a single dataset column.
    """

    name: str
    label: str | None = None
    physical_type: str | None = None
    logical_type: str | None = None
    source_format: str | None = None
    original_format: str | None = None
    value_labels: dict[Any, Any] = field(default_factory=dict)
    missing_values: Any = None
    missing_ranges: list[dict[str, Any]] = field(default_factory=list)
    display_format: str | None = None
    display_width: int | None = None
    measure: str | None = None
    role: str | None = None
    width: int | None = None
    decimals: int | None = None
    display_width: int | None = None
    alignment: str | None = None
    readstat_variable_type: str | None = None


@dataclass
class Dataset:
    """
    Internal representation of a statistical dataset.
    """

    dataframe: pd.DataFrame

    metadata: dict[str, Any] = field(default_factory=dict)

    source_format: str | None = None

    source_file: str | None = None

    normalized_metadata: DatasetMetadata | None = None

    column_metadata: dict[str, ColumnMetadata] = field(default_factory=dict)

    _provided_column_metadata_names: set[str] = field(
        default_factory=set,
        init=False,
        repr=False,
    )


    def __post_init__(self) -> None:
        """
        Ensure every DataFrame column has metadata.
        """

        self._provided_column_metadata_names = set(self.column_metadata)

        for index, column in enumerate(
            self.dataframe.columns
        ):
            name = str(column)

            if name in self.column_metadata:
                continue

            series = self.dataframe.iloc[
                :,
                index,
            ]
            self.column_metadata[name] = ColumnMetadata(
                name=name,
                physical_type=str(series.dtype),
                logical_type=self._infer_logical_type_from_dtype(
                    series.dtype
                ),
                source_format=self.source_format,
            )

        self.ensure_normalized_metadata()
        self.sync_metadata()


    @property
    def rows(self):
        return len(self.dataframe)


    @property
    def columns(self):
        return list(self.dataframe.columns)


    def summary(self):
        return {
            "rows": self.rows,
            "columns": len(self.columns),
            "column_names": self.columns,
            "source_format": self.source_format,
        }


    def variable_labels(self) -> dict[str, str]:
        """
        Return variable labels if available.
        """

        return {
            name: variable.label
            for name, variable in self.variables_metadata().items()
            if variable.label
        }


    def value_labels(self) -> dict[str, dict[Any, str]]:
        """
        Return value labels if available.
        """

        return {
            name: self._copy_value(variable.value_labels)
            for name, variable in self.variables_metadata().items()
            if variable.value_labels
        }


    def missing_values(self) -> dict[str, list[Any]]:
        """
        Return missing value metadata if available.
        """

        return {
            name: self._copy_value(variable.missing_values)
            for name, variable in self.variables_metadata().items()
            if variable.missing_values
        }


    def missing_ranges(self) -> dict[str, list[dict[str, Any]]]:
        """Return normalized missing ranges without flattening them."""

        return {
            name: self._copy_value(variable.missing_ranges)
            for name, variable in self.variables_metadata().items()
            if variable.missing_ranges
        }


    def get_normalized_metadata(self) -> DatasetMetadata:
        """
        Return normalized metadata, creating a minimal model if needed.
        """

        return self.ensure_normalized_metadata()


    def ensure_normalized_metadata(self) -> DatasetMetadata:
        """Fill normalized metadata gaps from compatibility representations."""

        if self.normalized_metadata is None:
            self.normalized_metadata = build_basic_metadata(
                dataframe=self.dataframe,
                source_format=self.source_format,
                source_backend=self.metadata.get("backend"),
                raw_metadata=self.metadata.copy(),
            )

        raw_pyreadstat = self.metadata.get("pyreadstat")
        if raw_pyreadstat is not None:
            fallback = metadata_from_pyreadstat(
                dataframe=self.dataframe,
                pyreadstat_metadata=raw_pyreadstat,
                source_format=self.source_format,
            )
            self._merge_normalized_metadata(fallback)

        self._merge_column_metadata()
        return self.normalized_metadata


    def variable_metadata(
        self,
        name: str
    ) -> VariableMetadata | None:
        """
        Return normalized metadata for one variable.
        """

        return self.get_normalized_metadata().get_variable(
            name
        )


    def variables_metadata(self) -> dict[str, VariableMetadata]:
        """
        Return normalized metadata for all variables.
        """

        current_columns = {str(column) for column in self.dataframe.columns}
        return {
            name: variable
            for name, variable in self.get_normalized_metadata().variables.items()
            if name in current_columns
        }


    def storage_types(self) -> dict[str, str]:
        """
        Return storage types for all variables.
        """

        metadata = self.get_normalized_metadata()
        storage_types = {}

        for index, column in enumerate(
            self.dataframe.columns
        ):
            name = str(column)
            series = self.dataframe.iloc[
                :,
                index,
            ]
            variable = metadata.get_variable(
                name
            )
            storage_type = None

            if variable:
                storage_type = variable.storage_type

            storage_types[name] = storage_type or str(
                series.dtype
            )

        return storage_types


    def display_formats(self) -> dict[str, str]:
        """
        Return display formats for variables that define one.
        """

        return {
            name: variable.display_format
            for name, variable in self.variables_metadata().items()
            if variable.display_format
        }


    def measurement_levels(self) -> dict[str, str]:
        """
        Return measurement levels for variables that define one.
        """

        return {
            name: variable.measure
            for name, variable in self.variables_metadata().items()
            if variable.measure
        }


    def sync_metadata(self) -> None:
        """Synchronize known legacy column fields from normalized metadata."""

        metadata = self.normalized_metadata
        if metadata is None:
            return

        for index, dataframe_column in enumerate(self.dataframe.columns):
            name = str(dataframe_column)
            variable = metadata.get_variable(name)
            if variable is None:
                continue
            column = self.column_metadata.get(name)
            if column is None:
                column = ColumnMetadata(name=name)
                self.column_metadata[name] = column

            column.name = name
            column.label = variable.label
            column.value_labels = self._copy_value(variable.value_labels)
            column.missing_ranges = self._copy_value(variable.missing_ranges)
            column.missing_values = self._legacy_missing_values(variable)
            column.physical_type = variable.storage_type or str(
                self.dataframe.iloc[:, index].dtype
            )
            column.display_format = variable.display_format
            if variable.display_format:
                column.original_format = variable.display_format
            column.display_width = variable.display_width
            column.measure = variable.measure
            column.role = variable.role
            column.width = variable.width
            column.decimals = variable.decimals
            if variable.display_format in {"date", "datetime"}:
                column.logical_type = variable.display_format


    def has_metadata(self) -> bool:
        """
        Return whether variables contain meaningful metadata.
        """

        if any(
            self._variable_has_metadata(variable)
            for variable in self.variables_metadata().values()
        ):
            return True

        return any(
            [
                bool(self.variable_labels()),
                bool(self.value_labels()),
                bool(self.missing_values()),
                bool(self.missing_ranges()),
                bool(self.display_formats()),
                bool(self.measurement_levels()),
            ]
        )


    def metadata_summary(self) -> dict[str, int | bool]:
        """
        Return a compact summary of normalized metadata.
        """

        metadata = self.get_normalized_metadata()

        return {
            "variables": len(metadata.variables),
            "variable_labels": len(self.variable_labels()),
            "value_label_sets": len(self.value_labels()),
            "missing_value_sets": len(self.missing_values()),
            "missing_range_sets": len(self.missing_ranges()),
            "display_formats": len(self.display_formats()),
            "measurement_levels": len(self.measurement_levels()),
            "has_metadata": self.has_metadata(),
        }

            
    def preview(self, rows: int = 5):
        """
        Return first rows of the dataset.
        """

        return self.dataframe.head(rows)


    def copy(
        self,
        deep: bool = True
    ) -> Dataset:
        """
        Return a copy of the dataset and its metadata.
        """

        return Dataset(
            dataframe=self.dataframe.copy(
                deep=deep
            ),
            metadata=self._copy_value(
                self.metadata,
                deep=deep,
            ),
            source_format=self.source_format,
            source_file=self.source_file,
            normalized_metadata=self._copy_value(
                self.normalized_metadata,
                deep=deep,
            ),
            column_metadata=self._copy_value(
                self.column_metadata,
                deep=deep,
            ),
        )


    def to_sidecar_dict(self) -> dict[str, Any]:
        """
        Return JSON-serializable metadata for sidecar files.
        """

        self.sync_metadata()
        columns = []
        for column in self.column_metadata.values():
            item = self._json_ready(asdict(column))
            item["value_label_items"] = [
                {
                    "value": self._json_ready(value),
                    "label": self._json_ready(label),
                }
                for value, label in column.value_labels.items()
            ]
            columns.append(item)

        return {
            "sidecar_version": 2,
            "source_format": self.source_format,
            "source_file": self._json_ready(
                self.source_file
            ),
            "columns": columns,
        }


    def write_sidecar(self, filename: str | Path) -> None:
        """
        Write Dataset metadata next to a metadata-poor output file.
        """

        sidecar = self.sidecar_path(filename)

        sidecar.write_text(
            json.dumps(
                self.to_sidecar_dict(),
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )


    @classmethod
    def read_sidecar(
        cls,
        filename: str | Path
    ) -> dict[str, ColumnMetadata]:
        """
        Read sidecar metadata if it exists.
        """

        sidecar = cls.sidecar_path(filename)

        if not sidecar.exists():
            return {}

        data = json.loads(
            sidecar.read_text(
                encoding="utf-8"
            )
        )

        columns = {}

        for item in data.get(
            "columns",
            []
        ):
            item = dict(item)
            value_label_items = item.pop("value_label_items", None)
            if value_label_items is not None:
                item["value_labels"] = {
                    entry.get("value"): entry.get("label")
                    for entry in value_label_items
                }

            name = item.get(
                "name"
            )

            if not name:
                continue

            columns[name] = ColumnMetadata(
                **item
            )

        return columns


    @staticmethod
    def sidecar_path(filename: str | Path) -> Path:
        """
        Return the sidecar path for an output filename.
        """

        return Path(
            f"{filename}.statconvert-metadata.json"
        )


    @staticmethod
    def _infer_logical_type_from_dtype(dtype: Any) -> str:
        """
        Infer a basic logical type from a pandas dtype.
        """

        if pd.api.types.is_datetime64_any_dtype(dtype):
            return "datetime"

        if pd.api.types.is_string_dtype(dtype):
            return "string"

        if pd.api.types.is_integer_dtype(dtype):
            return "integer"

        if pd.api.types.is_float_dtype(dtype):
            return "float"

        if pd.api.types.is_bool_dtype(dtype):
            return "boolean"

        return "unknown"


    @staticmethod
    def _variable_has_metadata(
        variable: VariableMetadata
    ) -> bool:
        """
        Return whether a variable has metadata beyond name and storage type.
        """

        return any(
            [
                bool(variable.label),
                bool(variable.value_labels),
                bool(variable.missing_values),
                bool(variable.missing_ranges),
                bool(variable.display_format),
                bool(variable.measure),
                bool(variable.role),
                bool(variable.raw),
            ]
        )


    def _merge_normalized_metadata(self, fallback: DatasetMetadata) -> None:
        """Fill only absent normalized fields from another metadata model."""

        metadata = self.normalized_metadata
        if metadata is None:
            self.normalized_metadata = self._copy_value(fallback)
            return

        metadata.source_format = metadata.source_format or fallback.source_format
        metadata.source_backend = metadata.source_backend or fallback.source_backend
        metadata.dataset_label = metadata.dataset_label or fallback.dataset_label
        for name, fallback_variable in fallback.variables.items():
            variable = metadata.get_variable(name)
            if variable is None:
                metadata.add_variable(self._copy_value(fallback_variable))
                continue
            self._fill_variable_gaps(variable, fallback_variable)


    def _merge_column_metadata(self) -> None:
        metadata = self.normalized_metadata
        if metadata is None:
            return
        for name in self._provided_column_metadata_names:
            column = self.column_metadata.get(name)
            if column is None:
                continue
            fallback = variable_metadata_from_legacy(column)
            variable = metadata.get_variable(name)
            if variable is None:
                metadata.add_variable(fallback)
            else:
                self._fill_variable_gaps(variable, fallback)


    @classmethod
    def _fill_variable_gaps(
        cls,
        variable: VariableMetadata,
        fallback: VariableMetadata,
    ) -> None:
        scalar_fields = (
            "label", "storage_type", "display_format", "display_width",
            "measure", "role", "width", "decimals",
        )
        for field_name in scalar_fields:
            if getattr(variable, field_name) is None:
                setattr(variable, field_name, cls._copy_value(getattr(fallback, field_name)))
        if not variable.value_labels:
            variable.value_labels = cls._copy_value(fallback.value_labels)
        if not variable.missing_values:
            variable.missing_values = cls._copy_value(fallback.missing_values)
        if not variable.missing_ranges:
            variable.missing_ranges = cls._copy_value(fallback.missing_ranges)


    @classmethod
    def _legacy_missing_values(cls, variable: VariableMetadata) -> Any:
        if variable.missing_ranges or variable.missing_values:
            return {
                "ranges": cls._copy_value(variable.missing_ranges),
                "user_values": cls._copy_value(variable.missing_values),
            }
        return None


    @staticmethod
    def _copy_value(
        value: Any,
        deep: bool = True
    ) -> Any:
        """
        Copy a metadata value, falling back gracefully if deep copy fails.
        """

        if not deep:
            if isinstance(
                value,
                dict
            ):
                return value.copy()

            return value

        try:
            return copy_module.deepcopy(
                value
            )

        except Exception:
            if isinstance(
                value,
                dict
            ):
                return value.copy()

            return value


    @classmethod
    def _json_ready(
        cls,
        value: Any
    ) -> Any:
        """
        Convert nested metadata values to JSON-compatible values.
        """

        if isinstance(
            value,
            dict
        ):
            return {
                str(key): cls._json_ready(item)
                for key, item in value.items()
            }

        if isinstance(
            value,
            list
        ):
            return [
                cls._json_ready(item)
                for item in value
            ]

        if isinstance(
            value,
            tuple
        ):
            return [
                cls._json_ready(item)
                for item in value
            ]

        if pd.isna(value):
            return None

        if isinstance(
            value,
            Path
        ):
            return str(value)

        if isinstance(
            value,
            (date, datetime, pd.Timestamp)
        ):
            return value.isoformat()

        if hasattr(
            value,
            "item"
        ):
            return cls._json_ready(
                value.item()
            )

        if isinstance(
            value,
            (str, int, float, bool)
        ) or value is None:
            return value

        return str(value)

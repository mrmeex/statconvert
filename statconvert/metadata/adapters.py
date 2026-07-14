import copy
from typing import Any

import pandas as pd

from statconvert.metadata.model import DatasetMetadata, VariableMetadata


def build_basic_metadata(
    dataframe: pd.DataFrame,
    source_format: str | None = None,
    source_backend: str | None = None,
    raw_metadata: dict[str, Any] | None = None,
) -> DatasetMetadata:
    """
    Build minimal normalized metadata from a DataFrame.
    """

    metadata = DatasetMetadata(
        source_format=source_format,
        source_backend=source_backend,
        raw_metadata=raw_metadata or {},
    )

    for index, column in enumerate(dataframe.columns):
        name = str(column)

        metadata.add_variable(
            VariableMetadata(
                name=name,
                storage_type=str(dataframe.iloc[:, index].dtype),
            )
        )

    return metadata


def metadata_from_pyreadstat(
    dataframe: pd.DataFrame,
    pyreadstat_metadata: Any,
    source_format: str | None = None,
    source_backend: str = "pyreadstat",
) -> DatasetMetadata:
    """
    Build normalized metadata from a pyreadstat metadata object.
    """

    metadata = build_basic_metadata(
        dataframe=dataframe,
        source_format=source_format,
        source_backend=source_backend,
        raw_metadata={
            "pyreadstat": pyreadstat_metadata,
        },
    )

    labels = getattr(
        pyreadstat_metadata,
        "column_names_to_labels",
        {},
    ) or {}
    value_labels = getattr(
        pyreadstat_metadata,
        "variable_value_labels",
        {},
    ) or {}
    original_variable_types = getattr(
        pyreadstat_metadata,
        "original_variable_types",
        {},
    ) or {}
    readstat_variable_types = getattr(
        pyreadstat_metadata,
        "readstat_variable_types",
        {},
    ) or {}
    variable_storage_width = getattr(
        pyreadstat_metadata,
        "variable_storage_width",
        {},
    ) or {}
    variable_display_width = getattr(
        pyreadstat_metadata,
        "variable_display_width",
        {},
    ) or {}
    variable_measure = getattr(
        pyreadstat_metadata,
        "variable_measure",
        {},
    ) or {}
    variable_format = getattr(
        pyreadstat_metadata,
        "variable_format",
        {},
    ) or {}
    missing_ranges = getattr(
        pyreadstat_metadata,
        "missing_ranges",
        {},
    ) or {}
    missing_user_values = getattr(
        pyreadstat_metadata,
        "missing_user_values",
        {},
    ) or {}

    for column in dataframe.columns:
        name = str(column)
        variable = metadata.get_variable(
            name
        )

        if variable is None:
            continue

        variable.label = labels.get(
            name
        )
        variable.value_labels = value_labels.get(
            name,
            {},
        )
        variable.width = variable_storage_width.get(
            name
        )
        variable.measure = variable_measure.get(
            name
        )
        variable.display_format = variable_format.get(
            name
        )

        original_type = original_variable_types.get(
            name
        )
        readstat_type = readstat_variable_types.get(
            name
        )
        display_width = variable_display_width.get(
            name
        )
        ranges = missing_ranges.get(
            name
        )
        user_values = missing_user_values.get(
            name
        )

        if original_type is not None:
            variable.raw["original_variable_type"] = original_type

            if variable.display_format is None:
                variable.display_format = original_type

        if readstat_type is not None:
            variable.raw["readstat_variable_type"] = readstat_type

        if display_width is not None:
            variable.display_width = display_width
            variable.raw["display_width"] = display_width

        if ranges:
            variable.missing_ranges = list(ranges)
            variable.raw["missing_ranges"] = ranges

        if user_values:
            variable.raw["missing_user_values"] = user_values

            if isinstance(
                user_values,
                list,
            ):
                variable.missing_values = user_values

    return metadata


def metadata_from_sidecar(
    base_metadata: DatasetMetadata,
    column_metadata: dict[str, Any],
) -> DatasetMetadata:
    """Restore normalized variable metadata from a sidecar representation."""

    metadata = copy.deepcopy(base_metadata)
    for name, column in column_metadata.items():
        restored = variable_metadata_from_legacy(column)
        restored.name = name
        variable = metadata.get_variable(name)
        if variable is None:
            metadata.add_variable(restored)
            continue
        for field_name in (
            "label", "storage_type", "display_format", "display_width",
            "measure", "role", "width", "decimals",
        ):
            value = getattr(restored, field_name)
            if value is not None:
                setattr(variable, field_name, value)
        variable.value_labels = restored.value_labels
        variable.missing_values = restored.missing_values
        variable.missing_ranges = restored.missing_ranges
    return metadata


def variable_metadata_from_legacy(column: Any) -> VariableMetadata:
    """Translate one compatibility ColumnMetadata-like object."""

    missing_values: list[Any] = []
    missing_ranges = copy.deepcopy(getattr(column, "missing_ranges", []) or [])
    legacy_missing = getattr(column, "missing_values", None)
    if isinstance(legacy_missing, dict):
        missing_values = copy.deepcopy(legacy_missing.get("user_values", []) or [])
        if not missing_ranges:
            missing_ranges = copy.deepcopy(legacy_missing.get("ranges", []) or [])
    elif isinstance(legacy_missing, list):
        missing_values = copy.deepcopy(legacy_missing)

    return VariableMetadata(
        name=str(getattr(column, "name", "")),
        label=getattr(column, "label", None),
        value_labels=copy.deepcopy(getattr(column, "value_labels", {}) or {}),
        missing_values=missing_values,
        missing_ranges=missing_ranges,
        storage_type=getattr(column, "physical_type", None),
        display_format=(
            getattr(column, "display_format", None)
            or getattr(column, "original_format", None)
        ),
        display_width=getattr(column, "display_width", None),
        measure=getattr(column, "measure", None),
        role=getattr(column, "role", None),
        width=getattr(column, "width", None),
        decimals=getattr(column, "decimals", None),
    )

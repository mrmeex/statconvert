from __future__ import annotations

import copy
from typing import Any

from statconvert.dataset import ColumnMetadata, Dataset
from statconvert.metadata import DatasetMetadata, VariableMetadata
from statconvert.transformations.base import Transformation
from statconvert.transformations.exceptions import TransformationError


class SelectColumnsTransformation(Transformation):
    """
    Keep only selected columns in the requested order.
    """

    name = "select-columns"
    description = "Keep only the requested dataset columns."


    def __init__(
        self,
        columns: list[str],
        ignore_missing: bool = False,
    ) -> None:
        self.columns = columns
        self.ignore_missing = ignore_missing


    def apply(
        self,
        dataset: Dataset
    ) -> Dataset:
        """
        Return a Dataset containing only selected columns.
        """

        selected_columns = _validate_selected_columns(
            available_columns=list(
                dataset.dataframe.columns
            ),
            requested_columns=self.columns,
            ignore_missing=self.ignore_missing,
            operation="--select",
        )

        return _dataset_with_columns(
            dataset,
            selected_columns,
        )


class DropColumnsTransformation(Transformation):
    """
    Remove selected columns from a dataset.
    """

    name = "drop-columns"
    description = "Remove the requested dataset columns."


    def __init__(
        self,
        columns: list[str],
        ignore_missing: bool = False,
    ) -> None:
        self.columns = columns
        self.ignore_missing = ignore_missing


    def apply(
        self,
        dataset: Dataset
    ) -> Dataset:
        """
        Return a Dataset with selected columns removed.
        """

        if not self.columns:
            raise TransformationError(
                "At least one column must be provided."
            )

        available_columns = list(
            dataset.dataframe.columns
        )
        columns_to_drop = _validate_requested_columns(
            available_columns=available_columns,
            requested_columns=self.columns,
            ignore_missing=self.ignore_missing,
            operation="--drop",
        )
        drop_names = {
            str(column)
            for column in columns_to_drop
        }
        remaining_columns = [
            column
            for column in available_columns
            if str(column) not in drop_names
        ]

        if not remaining_columns:
            raise TransformationError(
                "Cannot drop all columns from a dataset."
            )

        return _dataset_with_columns(
            dataset,
            remaining_columns,
        )


class RenameColumnsTransformation(Transformation):
    """
    Rename dataset columns while preserving column order.
    """

    name = "rename-columns"
    description = "Rename dataset columns."


    def __init__(
        self,
        rename_map: dict[str, str],
        ignore_missing: bool = False,
        allow_overwrite: bool = False,
    ) -> None:
        self.rename_map = rename_map
        self.ignore_missing = ignore_missing
        self.allow_overwrite = allow_overwrite


    def apply(
        self,
        dataset: Dataset
    ) -> Dataset:
        """
        Return a Dataset with columns renamed.
        """

        validated_map = _validate_rename_map(
            available_columns=list(
                dataset.dataframe.columns
            ),
            rename_map=self.rename_map,
            ignore_missing=self.ignore_missing,
            allow_overwrite=self.allow_overwrite,
        )

        return _dataset_with_renamed_columns(
            dataset,
            validated_map,
        )


def _validate_selected_columns(
    available_columns: list[Any],
    requested_columns: list[str],
    ignore_missing: bool = False,
    operation: str = "--select",
) -> list[Any]:
    """
    Validate selected columns and return matching DataFrame labels.
    """

    if not requested_columns:
        raise TransformationError(
            "At least one column must be provided."
        )

    selected_columns = _validate_requested_columns(
        available_columns=available_columns,
        requested_columns=requested_columns,
        ignore_missing=ignore_missing,
        operation=operation,
    )

    if not selected_columns:
        raise TransformationError(
            "No requested columns were found."
        )

    return selected_columns


def _validate_requested_columns(
    available_columns: list[Any],
    requested_columns: list[str],
    ignore_missing: bool = False,
    operation: str | None = None,
) -> list[Any]:
    """
    Validate requested columns and return matching DataFrame labels.
    """

    column_lookup = {
        str(column): column
        for column in available_columns
    }
    missing_columns = [
        column
        for column in requested_columns
        if column not in column_lookup
    ]

    if missing_columns and not ignore_missing:
        operation_detail = f" (operation: {operation})" if operation else ""
        raise TransformationError(
            "Column not found: "
            + ", ".join(
                missing_columns
            )
            + operation_detail
        )

    return [
        column_lookup[column]
        for column in requested_columns
        if column in column_lookup
    ]


def _validate_rename_map(
    available_columns: list[Any],
    rename_map: dict[str, str],
    ignore_missing: bool = False,
    allow_overwrite: bool = False,
) -> dict[str, str]:
    """
    Validate a rename map and return mappings for existing columns.
    """

    if not rename_map:
        raise TransformationError(
            "At least one column rename must be provided."
        )

    _validate_target_names(
        rename_map
    )

    column_names = [
        str(column)
        for column in available_columns
    ]
    available_names = set(
        column_names
    )
    missing_columns = [
        source
        for source in rename_map
        if source not in available_names
    ]

    if missing_columns and not ignore_missing:
        raise TransformationError(
            "Column not found: "
            + ", ".join(
                missing_columns
            )
            + " (operation: --rename)"
        )

    validated_map = {
        source: target
        for source, target in rename_map.items()
        if source in available_names
    }

    if not validated_map:
        raise TransformationError(
            "No requested columns were found."
        )

    renamed_sources = set(
        validated_map
    )
    existing_target_collisions = [
        target
        for target in validated_map.values()
        if target in available_names and target not in renamed_sources
    ]

    if existing_target_collisions and not allow_overwrite:
        raise TransformationError(
            "Target column already exists: "
            + ", ".join(
                existing_target_collisions
            )
        )

    resulting_columns = [
        validated_map.get(
            column,
            column,
        )
        for column in column_names
    ]

    duplicate_columns = _duplicates(
        resulting_columns
    )

    if duplicate_columns:
        raise TransformationError(
            "Renaming would create duplicate columns: "
            + ", ".join(
                duplicate_columns
            )
        )

    return validated_map


def _validate_target_names(
    rename_map: dict[str, str]
) -> None:
    """
    Validate rename target names.
    """

    invalid_targets = [
        source
        for source, target in rename_map.items()
        if not target or not target.strip()
    ]

    if invalid_targets:
        raise TransformationError(
            "Target column name cannot be empty."
        )


def _duplicates(
    values: list[str]
) -> list[str]:
    """
    Return duplicate values in original encounter order.
    """

    seen = set()
    duplicates = []

    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(
                value
            )

        seen.add(
            value
        )

    return duplicates


def _dataset_with_columns(
    dataset: Dataset,
    columns: list[Any],
) -> Dataset:
    """
    Return a copied Dataset containing only the provided columns.
    """

    column_names = [
        str(column)
        for column in columns
    ]

    return Dataset(
        dataframe=dataset.dataframe.loc[
            :,
            columns,
        ].copy(
            deep=True
        ),
        metadata=_safe_deepcopy(
            dataset.metadata
        ),
        source_format=dataset.source_format,
        source_file=dataset.source_file,
        normalized_metadata=_filter_normalized_metadata(
            dataset,
            column_names,
        ),
        column_metadata=_filter_column_metadata(
            dataset,
            column_names,
        ),
    )


def _dataset_with_renamed_columns(
    dataset: Dataset,
    rename_map: dict[str, str],
) -> Dataset:
    """
    Return a copied Dataset with renamed columns.
    """

    source_columns = list(
        dataset.dataframe.columns
    )
    source_names = [
        str(column)
        for column in source_columns
    ]
    resulting_names = [
        rename_map.get(
            name,
            name,
        )
        for name in source_names
    ]
    dataframe = dataset.dataframe.copy(
        deep=True
    )
    dataframe.columns = resulting_names

    return Dataset(
        dataframe=dataframe,
        metadata=_safe_deepcopy(
            dataset.metadata
        ),
        source_format=dataset.source_format,
        source_file=dataset.source_file,
        normalized_metadata=_rename_normalized_metadata(
            dataset,
            rename_map,
            source_names,
            resulting_names,
        ),
        column_metadata=_rename_column_metadata(
            dataset,
            rename_map,
            source_names,
            resulting_names,
        ),
    )


def _filter_normalized_metadata(
    dataset: Dataset,
    columns: list[str],
) -> DatasetMetadata:
    """
    Return normalized metadata for the provided columns.
    """

    source_metadata = _source_normalized_metadata(
        dataset
    )
    filtered_metadata = DatasetMetadata(
        source_format=source_metadata.source_format,
        source_backend=source_metadata.source_backend,
        dataset_label=source_metadata.dataset_label,
        notes=_safe_deepcopy(
            source_metadata.notes
        ),
        raw_metadata=_safe_deepcopy(
            source_metadata.raw_metadata
        ),
    )

    for column in columns:
        variable = source_metadata.get_variable(
            column
        )

        if variable:
            filtered_metadata.add_variable(
                _safe_deepcopy(
                    variable
                )
            )

        else:
            filtered_metadata.add_variable(
                VariableMetadata(
                    name=column
                )
            )

    return filtered_metadata


def _rename_normalized_metadata(
    dataset: Dataset,
    rename_map: dict[str, str],
    source_columns: list[str],
    resulting_columns: list[str],
) -> DatasetMetadata:
    """
    Return normalized metadata with variable names renamed.
    """

    source_metadata = _source_normalized_metadata(
        dataset
    )
    renamed_metadata = DatasetMetadata(
        source_format=source_metadata.source_format,
        source_backend=source_metadata.source_backend,
        dataset_label=source_metadata.dataset_label,
        notes=_safe_deepcopy(
            source_metadata.notes
        ),
        raw_metadata=_safe_deepcopy(
            source_metadata.raw_metadata
        ),
    )

    for source_name, result_name in zip(
        source_columns,
        resulting_columns,
    ):
        variable = source_metadata.get_variable(
            source_name
        )

        if variable:
            renamed_variable = _safe_deepcopy(
                variable
            )
            renamed_variable.name = result_name

        else:
            renamed_variable = VariableMetadata(
                name=result_name
            )

        renamed_metadata.add_variable(
            renamed_variable
        )

    return renamed_metadata


def _filter_column_metadata(
    dataset: Dataset,
    columns: list[str],
) -> dict[str, ColumnMetadata]:
    """
    Return legacy column metadata for the provided columns.
    """

    return {
        column: _safe_deepcopy(
            dataset.column_metadata[column]
        )
        for column in columns
        if column in dataset.column_metadata
    }


def _rename_column_metadata(
    dataset: Dataset,
    rename_map: dict[str, str],
    source_columns: list[str],
    resulting_columns: list[str],
) -> dict[str, ColumnMetadata]:
    """
    Return legacy column metadata with column names renamed.
    """

    column_metadata = {}

    for source_name, result_name in zip(
        source_columns,
        resulting_columns,
    ):
        if source_name not in dataset.column_metadata:
            continue

        column = _safe_deepcopy(
            dataset.column_metadata[source_name]
        )
        column.name = result_name
        column_metadata[result_name] = column

    return column_metadata


def _source_normalized_metadata(
    dataset: Dataset
) -> DatasetMetadata:
    """
    Return normalized metadata without mutating the source dataset.
    """

    if dataset.normalized_metadata:
        return dataset.normalized_metadata

    dataset_copy = dataset.copy()

    return dataset_copy.get_normalized_metadata()


def _safe_deepcopy(
    value: Any
) -> Any:
    """
    Deep-copy a value, falling back to a shallow copy where needed.
    """

    try:
        return copy.deepcopy(
            value
        )

    except Exception:
        if isinstance(
            value,
            dict
        ):
            return value.copy()

        return value

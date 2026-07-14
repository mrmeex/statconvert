from __future__ import annotations

from typing import Any

import pandas as pd

from statconvert.compare.exceptions import CompareError
from statconvert.compare.models import (
    ColumnComparison,
    CompareIssue,
    DatasetComparison,
    MetadataComparison,
    SchemaComparison,
    ShapeComparison,
    ValueComparison,
)
from statconvert.dataset import Dataset


def resolve_compare_object_selectors(
    object_selector: str | None,
    left_object_selector: str | None,
    right_object_selector: str | None,
) -> tuple[str | None, str | None]:
    """Resolve shared and side-specific compare object selectors."""

    if object_selector is not None and (
        left_object_selector is not None or right_object_selector is not None
    ):
        raise CompareError(
            "--object cannot be combined with --left-object or --right-object."
        )
    if object_selector is not None:
        return object_selector, object_selector
    return left_object_selector, right_object_selector


def compare_shape(left: Dataset, right: Dataset) -> ShapeComparison:
    """Compare the full dimensions of two datasets."""

    return ShapeComparison(
        left_rows=left.rows,
        right_rows=right.rows,
        left_columns=len(left.columns),
        right_columns=len(right.columns),
        rows_match=left.rows == right.rows,
        columns_match=len(left.columns) == len(right.columns),
    )


def compare_columns(left: Dataset, right: Dataset) -> ColumnComparison:
    """Compare full column membership and ordering."""

    left_columns = [str(column) for column in left.columns]
    right_columns = [str(column) for column in right.columns]
    left_names = set(left_columns)
    right_names = set(right_columns)

    return ColumnComparison(
        left_columns=left_columns,
        right_columns=right_columns,
        common_columns=[name for name in left_columns if name in right_names],
        left_only_columns=[name for name in left_columns if name not in right_names],
        right_only_columns=[name for name in right_columns if name not in left_names],
        same_columns=left_names == right_names,
        same_order=left_columns == right_columns,
    )


def compare_schema(
    left: Dataset,
    right: Dataset,
    columns: list[str] | None = None,
) -> SchemaComparison:
    """Compare normalized schema information for selected columns."""

    selected = _comparison_columns(left, right, columns)
    left_types = left.storage_types()
    right_types = right.storage_types()
    left_formats = left.display_formats()
    right_formats = right.display_formats()
    left_levels = left.measurement_levels()
    right_levels = right.measurement_levels()

    type_changes = _changed_values(selected, left_types, right_types)
    format_changes = _changed_values(selected, left_formats, right_formats)
    level_changes = _changed_values(selected, left_levels, right_levels)

    return SchemaComparison(
        storage_type_changes=type_changes,
        same_storage_types=not type_changes,
        display_format_changes=format_changes,
        measurement_level_changes=level_changes,
    )


def compare_metadata(
    left: Dataset,
    right: Dataset,
    columns: list[str] | None = None,
) -> MetadataComparison:
    """Compare normalized public metadata for selected columns."""

    selected = _comparison_columns(left, right, columns)
    variable_changes = _changed_values(
        selected, left.variable_labels(), right.variable_labels()
    )
    value_changes = _changed_mappings(
        selected, left.value_labels(), right.value_labels()
    )
    missing_changes = _changed_lists(
        selected, left.missing_values(), right.missing_values()
    )

    return MetadataComparison(
        variable_label_changes=variable_changes,
        value_label_changes=value_changes,
        missing_value_changes=missing_changes,
        same_variable_labels=not variable_changes,
        same_value_labels=not value_changes,
        same_missing_values=not missing_changes,
    )


def compare_values_summary(
    left: Dataset,
    right: Dataset,
    columns: list[str] | None = None,
    sample_size: int | None = None,
) -> ValueComparison:
    """Compare cell values by position and return difference counts."""

    selected = _comparison_columns(left, right, columns)
    if sample_size is not None and sample_size < 0:
        raise CompareError("Sample size must be zero or greater.")

    comparable_rows = min(left.rows, right.rows)
    compared_rows = (
        comparable_rows if sample_size is None else min(comparable_rows, sample_size)
    )
    differences: dict[str, int] = {}

    for column in selected:
        left_values = left.dataframe[column].iloc[:compared_rows].reset_index(drop=True)
        right_values = right.dataframe[column].iloc[:compared_rows].reset_index(drop=True)
        differences[column] = _count_differences(left_values, right_values)

    differing_cells = sum(differences.values())
    return ValueComparison(
        compared_rows=compared_rows,
        compared_columns=len(selected),
        cells_compared=compared_rows * len(selected),
        differing_cells=differing_cells,
        same_values=differing_cells == 0,
        sampled=sample_size is not None,
        sample_size=sample_size,
        differences_by_column=differences,
    )


def compare_datasets(
    left: Dataset,
    right: Dataset,
    compare_values: bool = True,
    sample_size: int | None = None,
    columns: list[str] | None = None,
) -> DatasetComparison:
    """Build a complete backend-independent dataset comparison."""

    shape = compare_shape(left, right)
    column_result = compare_columns(left, right)
    schema = compare_schema(left, right, columns)
    metadata = compare_metadata(left, right, columns)
    values = (
        compare_values_summary(left, right, columns, sample_size)
        if compare_values
        else None
    )
    issues = _build_issues(shape, column_result, schema, metadata, values)

    return DatasetComparison(
        left_source=left.source_file,
        right_source=right.source_file,
        shape=shape,
        columns=column_result,
        schema=schema,
        metadata=metadata,
        values=values,
        issues=issues,
    )


def _comparison_columns(
    left: Dataset,
    right: Dataset,
    columns: list[str] | None,
) -> list[str]:
    left_columns = [str(column) for column in left.columns]
    right_columns = [str(column) for column in right.columns]
    if columns is None:
        right_names = set(right_columns)
        return [name for name in left_columns if name in right_names]

    missing_left = [name for name in columns if name not in left_columns]
    missing_right = [name for name in columns if name not in right_columns]
    if missing_left or missing_right:
        details = []
        if missing_left:
            details.append(f"missing from left: {', '.join(missing_left)}")
        if missing_right:
            details.append(f"missing from right: {', '.join(missing_right)}")
        raise CompareError(f"Requested comparison columns are invalid ({'; '.join(details)}).")

    return list(columns)


def _changed_values(
    columns: list[str],
    left: dict[str, Any],
    right: dict[str, Any],
) -> dict[str, tuple[Any, Any]]:
    return {
        column: (left.get(column), right.get(column))
        for column in columns
        if left.get(column) != right.get(column)
    }


def _changed_mappings(
    columns: list[str],
    left: dict[str, dict[Any, str]],
    right: dict[str, dict[Any, str]],
) -> dict[str, tuple[dict[Any, str], dict[Any, str]]]:
    return {
        column: (left.get(column, {}), right.get(column, {}))
        for column in columns
        if left.get(column, {}) != right.get(column, {})
    }


def _changed_lists(
    columns: list[str],
    left: dict[str, list[Any]],
    right: dict[str, list[Any]],
) -> dict[str, tuple[list[Any], list[Any]]]:
    return {
        column: (left.get(column, []), right.get(column, []))
        for column in columns
        if left.get(column, []) != right.get(column, [])
    }


def _count_differences(left: pd.Series, right: pd.Series) -> int:
    both_missing = left.isna() & right.isna()
    one_missing = left.isna() ^ right.isna()
    try:
        unequal = left.ne(right).fillna(False)
        return int((one_missing | (unequal & ~both_missing)).sum())
    except (TypeError, ValueError):
        return sum(
            not _values_equal(left_value, right_value)
            for left_value, right_value in zip(left, right)
        )


def _values_equal(left: Any, right: Any) -> bool:
    left_missing = _is_scalar_missing(left)
    right_missing = _is_scalar_missing(right)
    if left_missing or right_missing:
        return left_missing and right_missing
    try:
        result = left == right
        return bool(result) if pd.api.types.is_scalar(result) else False
    except (TypeError, ValueError):
        return False


def _is_scalar_missing(value: Any) -> bool:
    try:
        result = pd.isna(value)
        return bool(result) if pd.api.types.is_scalar(result) else False
    except (TypeError, ValueError):
        return False


def _build_issues(
    shape: ShapeComparison,
    columns: ColumnComparison,
    schema: SchemaComparison,
    metadata: MetadataComparison,
    values: ValueComparison | None,
) -> list[CompareIssue]:
    issues: list[CompareIssue] = []
    if not shape.rows_match:
        issues.append(CompareIssue("error", "shape_rows_differ", "Row counts differ."))
    if not shape.columns_match:
        issues.append(
            CompareIssue("warning", "shape_columns_differ", "Column counts differ.")
        )
    if columns.right_only_columns:
        issues.append(
            CompareIssue(
                "warning", "columns_missing_left", "Columns are missing from the left dataset."
            )
        )
    if columns.left_only_columns:
        issues.append(
            CompareIssue(
                "warning", "columns_missing_right", "Columns are missing from the right dataset."
            )
        )
    if columns.same_columns and not columns.same_order:
        issues.append(
            CompareIssue("info", "column_order_changed", "Column order changed.")
        )
    issue_specs = (
        (not schema.same_storage_types, "storage_types_changed", "Storage types changed."),
        (
            bool(schema.display_format_changes),
            "display_formats_changed",
            _change_count_message(
                "Display format", len(schema.display_format_changes)
            ),
        ),
        (
            bool(schema.measurement_level_changes),
            "measurement_levels_changed",
            _change_count_message(
                "Measurement level", len(schema.measurement_level_changes)
            ),
        ),
        (not metadata.same_variable_labels, "variable_labels_changed", "Variable labels changed."),
        (not metadata.same_value_labels, "value_labels_changed", "Value labels changed."),
        (not metadata.same_missing_values, "missing_values_changed", "Missing values changed."),
    )
    issues.extend(
        CompareIssue("warning", code, message)
        for changed, code, message in issue_specs
        if changed
    )
    if values is not None and not values.same_values:
        issues.append(CompareIssue("error", "values_changed", "Data values changed."))
    if values is not None and values.sampled:
        issues.append(CompareIssue("info", "values_sampled", "Data values were sampled."))
    return issues


def _change_count_message(change_type: str, count: int) -> str:
    noun = "column" if count == 1 else "columns"
    return f"{change_type} changed for {count} {noun}."

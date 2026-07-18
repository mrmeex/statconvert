from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from statconvert.compare.exceptions import CompareError
from statconvert.compare.models import (
    ColumnComparison,
    CompareOptions,
    CompareIssue,
    DatasetComparison,
    DifferenceDetail,
    MetadataComparison,
    SchemaComparison,
    ShapeComparison,
    ValueComparison,
)
from statconvert.dataset import Dataset


@dataclass(frozen=True)
class _RowAlignment:
    left: pd.DataFrame
    right: pd.DataFrame
    matched_rows: int
    rows_only_left: int
    rows_only_right: int
    left_only_keys: pd.MultiIndex | None = None
    right_only_keys: pd.MultiIndex | None = None


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


def compare_shape(
    left: Dataset,
    right: Dataset,
    ignore_columns: tuple[str, ...] = (),
) -> ShapeComparison:
    """Compare dimensions after removing explicitly ignored columns."""

    ignored = set(ignore_columns)
    left_columns = [column for column in left.columns if str(column) not in ignored]
    right_columns = [column for column in right.columns if str(column) not in ignored]

    return ShapeComparison(
        left_rows=left.rows,
        right_rows=right.rows,
        left_columns=len(left_columns),
        right_columns=len(right_columns),
        rows_match=left.rows == right.rows,
        columns_match=len(left_columns) == len(right_columns),
    )


def compare_columns(
    left: Dataset,
    right: Dataset,
    ignore_columns: tuple[str, ...] = (),
) -> ColumnComparison:
    """Compare column membership and order after applying ignored columns."""

    ignored = set(ignore_columns)
    left_columns = [
        str(column) for column in left.columns if str(column) not in ignored
    ]
    right_columns = [
        str(column) for column in right.columns if str(column) not in ignored
    ]
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
    ignore_columns: tuple[str, ...] = (),
) -> SchemaComparison:
    """Compare normalized schema information for selected columns."""

    selected = _comparison_columns(left, right, columns, ignore_columns)
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
    ignore_columns: tuple[str, ...] = (),
) -> MetadataComparison:
    """Compare normalized public metadata for selected columns."""

    selected = _comparison_columns(left, right, columns, ignore_columns)
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
    ignore_columns: tuple[str, ...] = (),
    numeric_tolerance: float = 0.0,
    key_columns: tuple[str, ...] = (),
) -> ValueComparison:
    """Compare cell values after positional or key-based row alignment."""

    options = CompareOptions(
        ignore_columns=ignore_columns,
        numeric_tolerance=numeric_tolerance,
        key_columns=key_columns,
    )
    selected = _comparison_columns(left, right, columns, options.ignore_columns)
    if sample_size is not None and sample_size < 0:
        raise CompareError("Sample size must be zero or greater.")
    alignment = _resolve_row_alignment(left, right, options.key_columns)
    compared_rows = (
        alignment.matched_rows
        if sample_size is None
        else min(alignment.matched_rows, sample_size)
    )
    values, _ = _compare_aligned_values(
        alignment,
        selected,
        compared_rows=compared_rows,
        sample_size=sample_size,
        numeric_tolerance=options.numeric_tolerance,
        row_matching_mode="key" if options.key_columns else "positional",
        key_columns=options.key_columns,
        detail_limit=0,
    )
    return values


def _compare_aligned_values(
    alignment: _RowAlignment,
    selected: list[str],
    *,
    compared_rows: int,
    sample_size: int | None,
    numeric_tolerance: float,
    row_matching_mode: str,
    key_columns: tuple[str, ...],
    detail_limit: int,
) -> tuple[ValueComparison, list[DifferenceDetail]]:
    differences: dict[str, int] = {}
    details: list[DifferenceDetail] = []

    for column in selected:
        left_values = alignment.left[column].iloc[:compared_rows]
        right_values = alignment.right[column].iloc[:compared_rows]
        difference_count, positions = _difference_summary(
            left_values,
            right_values,
            numeric_tolerance=numeric_tolerance,
            position_limit=max(detail_limit - len(details), 0),
        )
        differences[column] = difference_count
        for position in positions:
            details.append(
                DifferenceDetail(
                    kind="value",
                    row=position if row_matching_mode == "positional" else None,
                    key=(
                        _key_detail(alignment.left.iloc[position], key_columns)
                        if row_matching_mode == "key"
                        else None
                    ),
                    column=column,
                    left=_detail_value(left_values.iloc[position]),
                    right=_detail_value(right_values.iloc[position]),
                    message="Cell values differ.",
                )
            )

    differing_cells = sum(differences.values())
    return (
        ValueComparison(
            compared_rows=compared_rows,
            compared_columns=len(selected),
            cells_compared=compared_rows * len(selected),
            differing_cells=differing_cells,
            same_values=differing_cells == 0,
            sampled=sample_size is not None,
            sample_size=sample_size,
            differences_by_column=differences,
        ),
        details,
    )


def compare_datasets(
    left: Dataset,
    right: Dataset,
    compare_values: bool = True,
    sample_size: int | None = None,
    columns: list[str] | None = None,
    options: CompareOptions | None = None,
) -> DatasetComparison:
    """Build a complete backend-independent dataset comparison."""

    resolved_options = options or CompareOptions()
    if sample_size is not None and sample_size < 0:
        raise CompareError("Sample size must be zero or greater.")
    alignment = _resolve_row_alignment(
        left,
        right,
        resolved_options.key_columns,
    )
    compared_columns = _comparison_columns(
        left,
        right,
        columns,
        resolved_options.ignore_columns,
    )
    shape = compare_shape(left, right, resolved_options.ignore_columns)
    column_result = compare_columns(left, right, resolved_options.ignore_columns)
    schema = compare_schema(
        left,
        right,
        columns,
        resolved_options.ignore_columns,
    )
    metadata = compare_metadata(
        left,
        right,
        columns,
        resolved_options.ignore_columns,
    )
    row_matching_mode = "key" if resolved_options.key_columns else "positional"
    details, detailed_total = _structural_difference_details(
        alignment,
        shape,
        column_result,
        schema,
        row_matching_mode=row_matching_mode,
        key_columns=resolved_options.key_columns,
        detail_limit=resolved_options.max_differences,
    )
    if compare_values:
        values, value_details = _compare_aligned_values(
            alignment,
            compared_columns,
            compared_rows=(
                alignment.matched_rows
                if sample_size is None
                else min(alignment.matched_rows, sample_size)
            ),
            sample_size=sample_size,
            numeric_tolerance=resolved_options.numeric_tolerance,
            row_matching_mode=row_matching_mode,
            key_columns=resolved_options.key_columns,
            detail_limit=max(resolved_options.max_differences - len(details), 0),
        )
        details.extend(value_details)
        detailed_total += values.differing_cells
    else:
        values = None
    issues = _build_issues(
        shape,
        column_result,
        schema,
        metadata,
        values,
        row_matching_mode=row_matching_mode,
        rows_only_left=alignment.rows_only_left,
        rows_only_right=alignment.rows_only_right,
    )

    return DatasetComparison(
        left_source=left.source_file,
        right_source=right.source_file,
        shape=shape,
        columns=column_result,
        schema=schema,
        metadata=metadata,
        values=values,
        issues=issues,
        options=resolved_options,
        columns_compared=compared_columns,
        row_matching_mode=row_matching_mode,
        key_columns=list(resolved_options.key_columns),
        matched_rows=alignment.matched_rows,
        rows_only_left=alignment.rows_only_left,
        rows_only_right=alignment.rows_only_right,
        differences=details,
        detailed_differences_total=detailed_total,
        detailed_differences_shown=len(details),
        detailed_differences_truncated=detailed_total > len(details),
    )


def _resolve_row_alignment(
    left: Dataset,
    right: Dataset,
    key_columns: tuple[str, ...],
) -> _RowAlignment:
    if not key_columns:
        matched_rows = min(left.rows, right.rows)
        return _RowAlignment(
            left=left.dataframe.iloc[:matched_rows],
            right=right.dataframe.iloc[:matched_rows],
            matched_rows=matched_rows,
            rows_only_left=max(left.rows - right.rows, 0),
            rows_only_right=max(right.rows - left.rows, 0),
        )

    _validate_key_columns(left, right, key_columns)
    _validate_unique_keys(left.dataframe, key_columns, side="left")
    _validate_unique_keys(right.dataframe, key_columns, side="right")

    left_keys = pd.MultiIndex.from_frame(left.dataframe[list(key_columns)])
    right_keys = pd.MultiIndex.from_frame(right.dataframe[list(key_columns)])
    matched_keys = left_keys.intersection(right_keys, sort=False)
    left_only_keys = left_keys.difference(right_keys, sort=False)
    right_only_keys = right_keys.difference(left_keys, sort=False)
    left_positions = left_keys.get_indexer(matched_keys)
    right_positions = right_keys.get_indexer(matched_keys)

    return _RowAlignment(
        left=left.dataframe.iloc[left_positions].reset_index(drop=True),
        right=right.dataframe.iloc[right_positions].reset_index(drop=True),
        matched_rows=len(matched_keys),
        rows_only_left=len(left_only_keys),
        rows_only_right=len(right_only_keys),
        left_only_keys=left_only_keys,
        right_only_keys=right_only_keys,
    )


def _structural_difference_details(
    alignment: _RowAlignment,
    shape: ShapeComparison,
    columns: ColumnComparison,
    schema: SchemaComparison,
    *,
    row_matching_mode: str,
    key_columns: tuple[str, ...],
    detail_limit: int,
) -> tuple[list[DifferenceDetail], int]:
    details: list[DifferenceDetail] = []
    total = 0

    if row_matching_mode == "key":
        row_groups = (
            ("row_only_left", alignment.left_only_keys, "Row found only on the left."),
            (
                "row_only_right",
                alignment.right_only_keys,
                "Row found only on the right.",
            ),
        )
        for kind, keys, message in row_groups:
            if keys is None:
                continue
            total += len(keys)
            for key_values in keys[: max(detail_limit - len(details), 0)]:
                details.append(
                    DifferenceDetail(
                        kind=kind,
                        key=_key_values_detail(key_values, key_columns),
                        message=message,
                    )
                )
    else:
        row_groups = (
            (
                "row_only_left",
                range(alignment.matched_rows, shape.left_rows),
                "Row found only on the left.",
            ),
            (
                "row_only_right",
                range(alignment.matched_rows, shape.right_rows),
                "Row found only on the right.",
            ),
        )
        for kind, rows, message in row_groups:
            total += len(rows)
            for row in rows[: max(detail_limit - len(details), 0)]:
                details.append(
                    DifferenceDetail(kind=kind, row=row, message=message)
                )

    column_groups = (
        ("column_only_left", columns.left_only_columns, "Column found only on the left."),
        (
            "column_only_right",
            columns.right_only_columns,
            "Column found only on the right.",
        ),
    )
    for kind, names, message in column_groups:
        total += len(names)
        for column in names[: max(detail_limit - len(details), 0)]:
            details.append(
                DifferenceDetail(kind=kind, column=column, message=message)
            )

    schema_groups = (
        ("storage type", schema.storage_type_changes),
        ("display format", schema.display_format_changes),
        ("measurement level", schema.measurement_level_changes),
    )
    for label, changes in schema_groups:
        total += len(changes)
        for column, (left_value, right_value) in list(changes.items())[
            : max(detail_limit - len(details), 0)
        ]:
            details.append(
                DifferenceDetail(
                    kind="schema",
                    column=column,
                    left=_detail_value(left_value),
                    right=_detail_value(right_value),
                    message=f"Column {label} differs.",
                )
            )

    return details, total


def _validate_key_columns(
    left: Dataset,
    right: Dataset,
    key_columns: tuple[str, ...],
) -> None:
    left_columns = {str(column) for column in left.columns}
    right_columns = {str(column) for column in right.columns}
    for column in key_columns:
        if column not in left_columns:
            raise CompareError(f"Key column not found in left dataset: {column}")
        if column not in right_columns:
            raise CompareError(f"Key column not found in right dataset: {column}")


def _validate_unique_keys(
    dataframe: pd.DataFrame,
    key_columns: tuple[str, ...],
    *,
    side: str,
) -> None:
    duplicate_rows = dataframe.duplicated(subset=list(key_columns), keep=False)
    if bool(duplicate_rows.any()):
        raise CompareError(f"Duplicate key values found in {side} dataset.")


def _comparison_columns(
    left: Dataset,
    right: Dataset,
    columns: list[str] | None,
    ignore_columns: tuple[str, ...] = (),
) -> list[str]:
    ignored = set(ignore_columns)
    left_columns = [
        str(column) for column in left.columns if str(column) not in ignored
    ]
    right_columns = [
        str(column) for column in right.columns if str(column) not in ignored
    ]
    if columns is None:
        right_names = set(right_columns)
        selected = [name for name in left_columns if name in right_names]
        if ignored and not selected:
            raise CompareError(
                "No columns remain to compare after applying --ignore-columns."
            )
        return selected

    requested = [name for name in columns if name not in ignored]
    if ignored and not requested:
        raise CompareError(
            "No columns remain to compare after applying --ignore-columns."
        )

    missing_left = [name for name in requested if name not in left_columns]
    missing_right = [name for name in requested if name not in right_columns]
    if missing_left or missing_right:
        details = []
        if missing_left:
            details.append(f"missing from left: {', '.join(missing_left)}")
        if missing_right:
            details.append(f"missing from right: {', '.join(missing_right)}")
        raise CompareError(f"Requested comparison columns are invalid ({'; '.join(details)}).")

    return requested


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


def _count_differences(
    left: pd.Series,
    right: pd.Series,
    *,
    numeric_tolerance: float = 0.0,
) -> int:
    count, _ = _difference_summary(
        left,
        right,
        numeric_tolerance=numeric_tolerance,
        position_limit=0,
    )
    return count


def _difference_summary(
    left: pd.Series,
    right: pd.Series,
    *,
    numeric_tolerance: float,
    position_limit: int,
) -> tuple[int, list[int]]:
    if numeric_tolerance > 0 and _uses_numeric_tolerance(left, right):
        count = 0
        positions: list[int] = []
        for position, (left_value, right_value) in enumerate(zip(left, right)):
            if _numeric_values_equal(left_value, right_value, numeric_tolerance):
                continue
            count += 1
            if len(positions) < position_limit:
                positions.append(position)
        return count, positions

    both_missing = left.isna() & right.isna()
    one_missing = left.isna() ^ right.isna()
    try:
        unequal = left.ne(right).fillna(False)
        difference_mask = one_missing | (unequal & ~both_missing)
        count = int(difference_mask.sum())
        positions = _bounded_true_positions(
            difference_mask.fillna(False),
            limit=position_limit,
        )
        return count, positions
    except (TypeError, ValueError):
        count = 0
        positions = []
        for position, (left_value, right_value) in enumerate(zip(left, right)):
            if _values_equal(left_value, right_value):
                continue
            count += 1
            if len(positions) < position_limit:
                positions.append(position)
        return count, positions


def _bounded_true_positions(
    mask: pd.Series,
    *,
    limit: int,
    block_size: int = 8_192,
) -> list[int]:
    """Return at most ``limit`` true positions without a full Python list."""

    if limit <= 0:
        return []
    positions: list[int] = []
    for start in range(0, len(mask), block_size):
        block = mask.iloc[start : start + block_size].to_numpy(
            dtype=bool,
            na_value=False,
            copy=False,
        )
        local_positions = block.nonzero()[0]
        remaining = limit - len(positions)
        positions.extend(
            int(start + position) for position in local_positions[:remaining]
        )
        if len(positions) == limit:
            break
    return positions


def _uses_numeric_tolerance(left: pd.Series, right: pd.Series) -> bool:
    return all(
        pd.api.types.is_numeric_dtype(series.dtype)
        and not pd.api.types.is_bool_dtype(series.dtype)
        for series in (left, right)
    )


def _numeric_values_equal(left: Any, right: Any, tolerance: float) -> bool:
    left_missing = _is_scalar_missing(left)
    right_missing = _is_scalar_missing(right)
    if left_missing or right_missing:
        return left_missing and right_missing

    left_value = _python_scalar(left)
    right_value = _python_scalar(right)
    try:
        if bool(left_value == right_value):
            return True
        return bool(abs(left_value - right_value) <= tolerance)
    except (ArithmeticError, TypeError, ValueError):
        return False


def _python_scalar(value: Any) -> Any:
    try:
        return value.item()
    except (AttributeError, ValueError):
        return value


def _detail_value(value: Any) -> Any:
    if _is_scalar_missing(value):
        return None
    return _python_scalar(value)


def _key_detail(
    row: pd.Series,
    key_columns: tuple[str, ...],
) -> dict[str, Any]:
    return {column: _detail_value(row[column]) for column in key_columns}


def _key_values_detail(
    values: tuple[Any, ...] | Any,
    key_columns: tuple[str, ...],
) -> dict[str, Any]:
    key_values = values if isinstance(values, tuple) else (values,)
    return {
        column: _detail_value(value)
        for column, value in zip(key_columns, key_values)
    }


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
    *,
    row_matching_mode: str = "positional",
    rows_only_left: int = 0,
    rows_only_right: int = 0,
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
    if row_matching_mode == "key" and rows_only_left:
        issues.append(
            CompareIssue(
                "error",
                "rows_only_left",
                f"{rows_only_left} key row(s) found only in the left dataset.",
            )
        )
    if row_matching_mode == "key" and rows_only_right:
        issues.append(
            CompareIssue(
                "error",
                "rows_only_right",
                f"{rows_only_right} key row(s) found only in the right dataset.",
            )
        )
    if values is not None and values.sampled:
        issues.append(CompareIssue("info", "values_sampled", "Data values were sampled."))
    return issues


def _change_count_message(change_type: str, count: int) -> str:
    noun = "column" if count == 1 else "columns"
    return f"{change_type} changed for {count} {noun}."

from __future__ import annotations

import re
import warnings
from collections import Counter
from datetime import date, datetime
from numbers import Number
from typing import Any

import pandas as pd

from statconvert.backends.excel_constraints import (
    XLS_MAX_COLUMNS,
    XLS_MAX_DATA_ROWS,
)
from statconvert.dataset import Dataset
from statconvert.inspection.models import ValidationIssue
from statconvert.registry import resolve_format_info


STATA_NAME_PATTERN = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*$"
)
SPSS_NAME_PATTERN = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_@#$]*$"
)


def validate_dataset(
    dataset: Dataset,
    target_format: str | None = None,
    strict: bool = False,
) -> list[ValidationIssue]:
    """
    Return validation issues for a dataset.

    The strict flag is accepted for API symmetry with the CLI; exit-code policy remains
    the responsibility of the caller.
    """

    issues = []
    issues.extend(
        validate_basic_structure(
            dataset
        )
    )
    issues.extend(
        validate_metadata_consistency(
            dataset
        )
    )
    issues.extend(
        validate_data_quality(
            dataset
        )
    )

    if target_format:
        issues.extend(
            validate_target_compatibility(
                dataset,
                target_format,
            )
        )

    return issues


def validate_basic_structure(
    dataset: Dataset
) -> list[ValidationIssue]:
    """
    Validate dataset shape and basic structural quality.
    """

    dataframe = dataset.dataframe
    issues = [
        ValidationIssue(
            severity="info",
            code="readable",
            message="Input file was read successfully.",
        )
    ]

    if len(
        dataframe
    ) == 0:
        issues.append(
            ValidationIssue(
                severity="warning",
                code="empty_dataset",
                message="Dataset contains no rows.",
            )
        )

    if len(
        dataframe.columns
    ) == 0:
        issues.append(
            ValidationIssue(
                severity="error",
                code="no_columns",
                message="Dataset contains no columns.",
            )
        )
        return issues

    duplicate_columns = _duplicate_column_names(
        dataframe
    )

    if duplicate_columns:
        issues.append(
            ValidationIssue(
                severity="error",
                code="duplicate_columns",
                message="Duplicate column names found: "
                + ", ".join(
                    duplicate_columns
                ),
            )
        )

    for column in dataframe.columns:
        name = str(
            column
        )

        if not name.strip():
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="empty_column_name",
                    column=name,
                    message="Column name is empty or whitespace only.",
                )
            )

    duplicate_rows = int(
        dataframe.duplicated().sum()
    )

    if duplicate_rows:
        issues.append(
            ValidationIssue(
                severity="warning",
                code="duplicate_rows",
                message=f"Dataset contains {duplicate_rows:,} duplicate rows.",
            )
        )

    for index, column in enumerate(
        dataframe.columns
    ):
        series = dataframe.iloc[
            :,
            index,
        ]

        if len(
            series
        ) > 0 and bool(
            series.isna().all()
        ):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="empty_column",
                    column=str(
                        column
                    ),
                    message="Column is entirely missing.",
                )
            )

    return issues


def validate_metadata_consistency(
    dataset: Dataset
) -> list[ValidationIssue]:
    """
    Validate normalized metadata against DataFrame columns.
    """

    issues = []
    metadata = dataset.get_normalized_metadata()
    dataframe_columns = {
        str(
            column
        )
        for column in dataset.dataframe.columns
    }
    metadata_columns = set(
        metadata.variables
    )

    for name in sorted(
        metadata_columns - dataframe_columns
    ):
        issues.append(
            ValidationIssue(
                severity="warning",
                code="metadata_extra_variable",
                column=name,
                message="Metadata contains a variable that is not present in the DataFrame.",
            )
        )

    for name in sorted(
        dataframe_columns - metadata_columns
    ):
        issues.append(
            ValidationIssue(
                severity="warning",
                code="metadata_missing_variable",
                column=name,
                message="DataFrame column is missing from normalized metadata.",
            )
        )

    for name in sorted(
        set(
            metadata.variable_labels()
        )
        - dataframe_columns
    ):
        issues.append(
            ValidationIssue(
                severity="warning",
                code="label_for_missing_column",
                column=name,
                message="Variable label exists for a column that is not present in the DataFrame.",
            )
        )

    value_labels = metadata.value_labels()

    for name, labels in sorted(
        value_labels.items()
    ):
        if name not in dataframe_columns:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="value_labels_for_missing_column",
                    column=name,
                    message="Value labels exist for a column that is not present in the DataFrame.",
                )
            )
            continue

        if not labels:
            continue

        series = _series_by_name(
            dataset.dataframe,
            name,
        )
        values = _unique_non_missing_values(
            series
        )

        if values and not any(
            _value_in_values(
                labelled_value,
                values,
            )
            for labelled_value in labels
        ):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="unused_value_labels",
                    column=name,
                    message="Value labels are defined, but none of their values appear in the data.",
                )
            )

        unlabelled_values = [
            value
            for value in values
            if not _value_in_values(
                value,
                list(
                    labels
                ),
            )
        ]

        if unlabelled_values and len(
            values
        ) <= max(
            10,
            len(
                labels
            )
            * 2,
        ):
            issues.append(
                ValidationIssue(
                    severity="info",
                    code="unlabelled_values",
                    column=name,
                    message="Some observed values do not have value labels.",
                )
            )

    for name, values in sorted(
        dataset.missing_values().items()
    ):
        if not values:
            continue

        issues.append(
            ValidationIssue(
                severity="info",
                code="metadata_missing_values_defined",
                column=name,
                message="Metadata-defined missing values are present and may not be pandas null values.",
            )
        )

    return issues


def validate_data_quality(
    dataset: Dataset
) -> list[ValidationIssue]:
    """
    Validate common data-quality concerns.
    """

    dataframe = dataset.dataframe
    issues = []

    for index, column in enumerate(
        dataframe.columns
    ):
        name = str(
            column
        )
        series = dataframe.iloc[
            :,
            index,
        ]
        row_count = len(
            series
        )
        non_missing = series.dropna()

        if row_count == 0:
            continue

        missing_count = int(
            series.isna().sum()
        )
        missing_percent = missing_count / row_count * 100

        if missing_percent > 50 and missing_percent < 100:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="high_missingness",
                    column=name,
                    message=f"Column is {missing_percent:.1f}% missing.",
                )
            )

        unique_count = _safe_unique_count(
            non_missing
        )

        if unique_count == 1:
            issues.append(
                ValidationIssue(
                    severity="info",
                    code="constant_column",
                    column=name,
                    message="Column has only one unique non-missing value.",
                )
            )

        if _is_text_like(
            series
        ):
            if _has_mixed_obvious_types(
                non_missing
            ):
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="mixed_object_types",
                        column=name,
                        message="Column contains a mixture of obvious value types.",
                    )
                )

            if len(
                non_missing
            ) > 0 and unique_count / len(
                non_missing
            ) > 0.9:
                issues.append(
                    ValidationIssue(
                        severity="info",
                        code="high_cardinality",
                        column=name,
                        message="Text-like column has very high uniqueness.",
                    )
                )

            if _mostly_parseable_datetimes(
                non_missing
            ):
                issues.append(
                    ValidationIssue(
                        severity="info",
                        code="possible_datetime",
                        column=name,
                        message="Column values appear mostly parseable as datetimes.",
                    )
                )

    return issues


def validate_target_compatibility(
    dataset: Dataset,
    target_format: str,
) -> list[ValidationIssue]:
    """
    Validate likely conversion-readiness for a target format.
    """

    issues = []
    format_result = resolve_format_info(
        target_format
    )

    if not format_result:
        issues.append(
            ValidationIssue(
                severity="error",
                code="unsupported_target_format",
                message=f"Unsupported target format: {target_format}",
            )
        )
        return issues

    extension, _ = format_result
    capabilities = _target_capabilities(extension)

    if not capabilities.can_write:
        from statconvert.registry import format_write_error

        issues.append(
            ValidationIssue(
                severity="error",
                code="target_not_writable",
                message=format_write_error(extension),
            )
        )
        return issues

    has_variable_labels = bool(
        dataset.variable_labels()
    )
    has_value_labels = bool(
        dataset.value_labels()
    )

    if (
        has_variable_labels
        and not capabilities.supports_variable_labels
    ) or (
        has_value_labels
        and not capabilities.supports_value_labels
    ):
        issues.append(
            ValidationIssue(
                severity="warning",
                code="metadata_may_not_be_preserved",
                message=f"Target format {extension} may not preserve all variable or value labels.",
            )
        )

    if extension == ".csv" and dataset.has_metadata():
        issues.append(
            ValidationIssue(
                severity="warning",
                code="csv_metadata_not_preserved",
                message="CSV output stores data only; normalized metadata will not be preserved in the data file.",
            )
        )

    if extension == ".dta":
        issues.extend(
            _validate_stata_target(
                dataset
            )
        )

    if extension == ".sav":
        issues.extend(
            _validate_spss_target(
                dataset
            )
        )

    if extension in {".xls", ".xlsx"}:
        issues.extend(
            _validate_excel_target(
                dataset,
                extension,
            )
        )

    return issues


def _target_capabilities(extension: str):
    """
    Import format capabilities lazily to avoid module-level registry cycles.
    """

    from statconvert.registry import get_format_capabilities

    return get_format_capabilities(extension)


def _validate_stata_target(
    dataset: Dataset
) -> list[ValidationIssue]:
    """
    Return conservative Stata compatibility warnings.
    """

    issues = []

    for column in dataset.dataframe.columns:
        name = str(
            column
        )

        if len(
            name
        ) > 32:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="stata_column_name_too_long",
                    column=name,
                    message="Stata variable names are limited to 32 characters.",
                )
            )

        if not STATA_NAME_PATTERN.match(
            name
        ):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="stata_invalid_column_name",
                    column=name,
                    message="Stata variable names should start with a letter or underscore and contain only letters, numbers and underscores.",
                )
            )

        series = _series_by_column_label(
            dataset.dataframe,
            column,
        )

        if _is_text_like(
            series
        ) and _has_long_strings(
            series,
            limit=2045,
        ):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="stata_long_string_values",
                    column=name,
                    message="Column contains very long string values that may be restricted by Stata output.",
                )
            )

    return issues


def _validate_spss_target(
    dataset: Dataset
) -> list[ValidationIssue]:
    """
    Return conservative SPSS compatibility warnings.
    """

    issues = []

    for column in dataset.dataframe.columns:
        name = str(
            column
        )

        if not name.strip():
            continue

        if not SPSS_NAME_PATTERN.match(
            name
        ):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="spss_column_name_may_need_sanitizing",
                    column=name,
                    message="SPSS output may need to sanitize this column name.",
                )
            )

    return issues


def _validate_excel_target(
    dataset: Dataset,
    extension: str,
) -> list[ValidationIssue]:
    """
    Return Excel worksheet size checks.
    """

    issues = []
    if extension == ".xls":
        row_limit = XLS_MAX_DATA_ROWS
        column_limit = XLS_MAX_COLUMNS
        format_name = ".xls"
        row_code = "xls_row_limit_exceeded"
        column_code = "xls_column_limit_exceeded"
        row_message = (
            f"Writing .xls is limited to {row_limit:,} data rows because row 1 "
            "is used for headers. Use .xlsx for larger data."
        )
        column_message = (
            f"Writing .xls is limited to {column_limit} columns. "
            "Use .xlsx for wider data."
        )
    else:
        row_limit = 1_048_576
        column_limit = 16_384
        format_name = "Excel"
        row_code = "excel_row_limit_exceeded"
        column_code = "excel_column_limit_exceeded"
        row_message = f"{format_name} output supports at most {row_limit:,} rows."
        column_message = (
            f"{format_name} output supports at most {column_limit:,} columns."
        )

    if len(
        dataset.dataframe
    ) > row_limit:
        issues.append(
            ValidationIssue(
                severity="error",
                code=row_code,
                message=row_message,
            )
        )

    if len(
        dataset.dataframe.columns
    ) > column_limit:
        issues.append(
            ValidationIssue(
                severity="error",
                code=column_code,
                message=column_message,
            )
        )

    return issues


def _duplicate_column_names(
    dataframe: pd.DataFrame
) -> list[str]:
    """
    Return duplicate column names as strings.
    """

    columns = [
        str(
            column
        )
        for column in dataframe.columns
    ]

    return sorted(
        column
        for column, count in Counter(columns).items()
        if count > 1
    )


def _series_by_name(
    dataframe: pd.DataFrame,
    name: str,
) -> pd.Series:
    """
    Return the first Series matching a stringified column name.
    """

    for index, column in enumerate(
        dataframe.columns
    ):
        if str(
            column
        ) == name:
            return dataframe.iloc[
                :,
                index,
            ]

    return pd.Series(
        dtype="object"
    )


def _series_by_column_label(
    dataframe: pd.DataFrame,
    column: Any,
) -> pd.Series:
    """
    Return the first Series matching a column label.
    """

    for index, dataframe_column in enumerate(
        dataframe.columns
    ):
        if dataframe_column == column:
            return dataframe.iloc[
                :,
                index,
            ]

    return pd.Series(
        dtype="object"
    )


def _unique_non_missing_values(
    series: pd.Series
) -> list[Any]:
    """
    Return unique non-missing values defensively.
    """

    non_missing = series.dropna()
    try:
        return non_missing.unique().tolist()
    except (TypeError, ValueError):
        pass

    values = []

    for value in non_missing.tolist():
        if not _value_in_values(
            value,
            values,
        ):
            values.append(
                value
            )

    return values


def _safe_unique_count(
    series: pd.Series
) -> int:
    """
    Return a unique count for normal and unhashable object values.
    """

    if series.empty:
        return 0

    try:
        return int(
            series.nunique()
        )

    except Exception:
        return len(
            _unique_non_missing_values(
                series
            )
        )


def _value_in_values(
    value: Any,
    values: list[Any],
) -> bool:
    """
    Return whether value equals any value in a list.
    """

    return any(
        _values_match(
            value,
            existing,
        )
        for existing in values
    )


def _values_match(
    left: Any,
    right: Any,
) -> bool:
    """
    Compare values defensively, treating missing values as equivalent.
    """

    try:
        if bool(
            pd.isna(
                left
            )
        ) and bool(
            pd.isna(
                right
            )
        ):
            return True

    except Exception:
        pass

    try:
        return bool(
            left == right
        )

    except Exception:
        return False


def _is_text_like(
    series: pd.Series
) -> bool:
    """
    Return whether a Series is object/string-like.
    """

    dtype = series.dtype

    return bool(
        pd.api.types.is_string_dtype(
            dtype
        )
        or pd.api.types.is_object_dtype(
            dtype
        )
    )


def _has_mixed_obvious_types(
    series: pd.Series
) -> bool:
    """
    Return whether an object column mixes obvious scalar types.
    """

    value_types = series.map(type).unique()
    categories = {
        _obvious_type_class(value_type)
        for value_type in value_types
    }
    categories.discard(
        "unknown"
    )

    return len(
        categories
    ) > 1


def _obvious_type_class(value_type: type[Any]) -> str:
    """Classify a scalar type using the same categories as ``_obvious_type``."""

    if issubclass(value_type, bool):
        return "boolean"

    if issubclass(value_type, Number):
        return "number"

    if issubclass(value_type, (date, datetime, pd.Timestamp)):
        return "datetime"

    if issubclass(value_type, str):
        return "string"

    return "unknown"


def _mostly_parseable_datetimes(
    series: pd.Series
) -> bool:
    """
    Return whether string values appear mostly parseable as datetimes.
    """

    sample = [
        value
        for value in series.head(
            100
        ).tolist()
        if isinstance(
            value,
            str,
        )
    ]

    if len(
        sample
    ) < 3:
        return False

    with warnings.catch_warnings():
        warnings.simplefilter(
            "ignore",
            UserWarning,
        )
        parsed = pd.to_datetime(
            sample,
            errors="coerce",
        )

    return bool(
        parsed.notna().sum() / len(
            sample
        )
        >= 0.8
    )


def _has_long_strings(
    series: pd.Series,
    limit: int,
) -> bool:
    """
    Return whether any non-missing string representation exceeds a limit.
    """

    return any(
        len(
            str(
                value
            )
        )
        > limit
        for value in series.dropna().head(
            1000
        )
    )

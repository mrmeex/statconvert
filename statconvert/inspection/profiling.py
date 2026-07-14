from __future__ import annotations

from typing import Any

import pandas as pd

from statconvert.dataset import Dataset
from statconvert.inspection.exceptions import InspectionError
from statconvert.inspection.models import (
    CategoricalProfile,
    ColumnProfile,
    DatasetSummary,
    FrequencyItem,
    FrequencyTable,
    MissingProfile,
    NumericProfile,
)


def summarize_dataset(
    dataset: Dataset
) -> DatasetSummary:
    """
    Return a high-level dataset summary.
    """

    dataframe = dataset.dataframe
    type_counts = _column_type_counts(
        dataframe
    )

    return DatasetSummary(
        row_count=len(
            dataframe
        ),
        column_count=len(
            dataframe.columns
        ),
        numeric_columns=type_counts["numeric"],
        text_columns=type_counts["text"],
        boolean_columns=type_counts["boolean"],
        datetime_columns=type_counts["datetime"],
        categorical_columns=type_counts["categorical"],
        other_columns=type_counts["other"],
        columns_with_variable_labels=len(
            dataset.variable_labels()
        ),
        columns_with_value_labels=len(
            dataset.value_labels()
        ),
        total_missing_cells=int(
            dataframe.isna().sum().sum()
        ),
        duplicate_rows=int(
            _safe_duplicate_rows(
                dataframe
            )
        ),
        memory_usage_bytes=int(
            dataframe.memory_usage(
                deep=True
            ).sum()
        ),
    )


def profile_column(
    dataset: Dataset,
    column: str,
) -> ColumnProfile:
    """
    Return a profile for one column.
    """

    column_label = _resolve_column(
        dataset,
        column,
    )
    name = str(
        column_label
    )
    series = dataset.dataframe[column_label]
    labels = dataset.variable_labels()
    missing_count = int(
        series.isna().sum()
    )
    row_count = len(
        series
    )
    non_missing_count = int(
        series.notna().sum()
    )
    unique_count = _safe_unique_count(
        series.dropna()
    )
    profile_type = _profile_type(
        series
    )
    profile = ColumnProfile(
        name=name,
        storage_type=dataset.storage_types().get(
            name,
            str(
                series.dtype
            ),
        ),
        label=labels.get(
            name
        ),
        non_missing_count=non_missing_count,
        missing_count=missing_count,
        missing_percent=_percent(
            missing_count,
            row_count,
        ),
        unique_count=unique_count,
        profile_type=profile_type,
    )

    if profile_type == "numeric":
        profile.numeric = _numeric_profile(
            series
        )

    elif profile_type == "categorical":
        profile.categorical = _categorical_profile(
            dataset,
            name,
            series,
        )

    return profile


def profile_columns(
    dataset: Dataset,
    columns: list[str] | None = None,
) -> list[ColumnProfile]:
    """
    Return profiles for requested columns, or all columns.
    """

    selected_columns = _selected_columns(
        dataset,
        columns,
    )

    return [
        profile_column(
            dataset,
            str(
                column
            ),
        )
        for column in selected_columns
    ]


def missing_profile(
    dataset: Dataset,
    columns: list[str] | None = None,
) -> list[MissingProfile]:
    """
    Return missing-value profiles.
    """

    dataframe = dataset.dataframe
    selected_columns = _selected_columns(
        dataset,
        columns,
    )
    labels = dataset.variable_labels()
    metadata_missing_values = dataset.missing_values()
    row_count = len(
        dataframe
    )
    profiles = []

    for column in selected_columns:
        name = str(
            column
        )
        count = int(
            dataframe[column].isna().sum()
        )
        profiles.append(
            MissingProfile(
                column=name,
                label=labels.get(
                    name
                ),
                missing_count=count,
                missing_percent=_percent(
                    count,
                    row_count,
                ),
                metadata_missing_values=list(
                    metadata_missing_values.get(
                        name,
                        [],
                    )
                ),
            )
        )

    return profiles


def frequency_table(
    dataset: Dataset,
    column: str,
    top: int | None = None,
    include_missing: bool = False,
) -> FrequencyTable:
    """
    Return a frequency table for one column.
    """

    column_label = _resolve_column(
        dataset,
        column,
    )
    name = str(
        column_label
    )
    series = dataset.dataframe[column_label]
    row_count = len(
        series
    )
    value_labels = dataset.value_labels().get(
        name,
        {},
    )
    counts = _safe_value_counts(
        series,
        include_missing=include_missing,
    )

    if top is not None:
        counts = counts[:top]

    items = [
        FrequencyItem(
            value=value,
            label=_lookup_value_label(
                value_labels,
                value,
            ),
            count=int(
                count
            ),
            percent=_percent(
                int(
                    count
                ),
                row_count,
            ),
        )
        for value, count in counts
    ]

    return FrequencyTable(
        column=name,
        label=dataset.variable_labels().get(
            name
        ),
        total_count=row_count,
        missing_count=int(
            series.isna().sum()
        ),
        items=items,
    )


def frequency_tables(
    dataset: Dataset,
    columns: list[str] | None = None,
    top: int | None = 20,
    include_missing: bool = False,
    max_unique: int | None = None,
) -> list[FrequencyTable]:
    """
    Return frequency tables for categorical-like columns.
    """

    selected_columns = _frequency_columns(
        dataset,
        columns,
        max_unique,
    )

    return [
        frequency_table(
            dataset,
            str(
                column
            ),
            top=top,
            include_missing=include_missing,
        )
        for column in selected_columns
    ]


def _column_type_counts(
    dataframe: pd.DataFrame
) -> dict[str, int]:
    """
    Count columns by broad dtype group.
    """

    counts = {
        "numeric": 0,
        "text": 0,
        "boolean": 0,
        "datetime": 0,
        "categorical": 0,
        "other": 0,
    }

    for column in dataframe.columns:
        dtype = dataframe[column].dtype

        if pd.api.types.is_bool_dtype(
            dtype
        ):
            counts["boolean"] += 1

        elif isinstance(
            dtype,
            pd.CategoricalDtype,
        ):
            counts["categorical"] += 1

        elif pd.api.types.is_datetime64_any_dtype(
            dtype
        ):
            counts["datetime"] += 1

        elif pd.api.types.is_numeric_dtype(
            dtype
        ):
            counts["numeric"] += 1

        elif pd.api.types.is_string_dtype(
            dtype
        ) or pd.api.types.is_object_dtype(
            dtype
        ):
            counts["text"] += 1

        else:
            counts["other"] += 1

    return counts


def _profile_type(
    series: pd.Series
) -> str:
    """
    Return the profile type for a Series.
    """

    dtype = series.dtype

    if pd.api.types.is_bool_dtype(
        dtype
    ):
        return "categorical"

    if isinstance(
        dtype,
        pd.CategoricalDtype,
    ):
        return "categorical"

    if pd.api.types.is_datetime64_any_dtype(
        dtype
    ):
        return "datetime"

    if pd.api.types.is_numeric_dtype(
        dtype
    ):
        return "numeric"

    if pd.api.types.is_string_dtype(
        dtype
    ) or pd.api.types.is_object_dtype(
        dtype
    ):
        return "categorical"

    return "other"


def _numeric_profile(
    series: pd.Series
) -> NumericProfile:
    """
    Return numeric statistics for a Series.
    """

    numeric = pd.to_numeric(
        series,
        errors="coerce",
    )
    non_missing = numeric.dropna()

    if non_missing.empty:
        return NumericProfile(
            count=0
        )

    quantiles = non_missing.quantile(
        [
            0.25,
            0.5,
            0.75,
        ]
    )

    return NumericProfile(
        count=int(
            non_missing.count()
        ),
        mean=_safe_float(
            non_missing.mean()
        ),
        std=_safe_float(
            non_missing.std()
        ),
        min=_safe_float(
            non_missing.min()
        ),
        q1=_safe_float(
            quantiles.loc[0.25]
        ),
        median=_safe_float(
            quantiles.loc[0.5]
        ),
        q3=_safe_float(
            quantiles.loc[0.75]
        ),
        max=_safe_float(
            non_missing.max()
        ),
    )


def _categorical_profile(
    dataset: Dataset,
    column: str,
    series: pd.Series,
) -> CategoricalProfile:
    """
    Return categorical statistics for a Series.
    """

    counts = _safe_value_counts(
        series,
        include_missing=False,
    )
    non_missing_count = int(
        series.notna().sum()
    )

    if not counts:
        return CategoricalProfile(
            count=0,
            unique_count=0,
        )

    top_value, top_count = counts[0]
    top_count = int(top_count)

    return CategoricalProfile(
        count=non_missing_count,
        unique_count=_safe_unique_count(series.dropna()),
        top_value=top_value,
        top_label=_lookup_value_label(
            dataset.value_labels().get(
                column,
                {},
            ),
            top_value,
        ),
        top_count=top_count,
        top_percent=_percent(
            top_count,
            len(
                series
            ),
        ),
    )


def _frequency_columns(
    dataset: Dataset,
    columns: list[str] | None,
    max_unique: int | None,
) -> list[Any]:
    """
    Return columns to use for frequency tables.
    """

    if columns is not None:
        return _selected_columns(
            dataset,
            columns,
        )

    value_label_columns = set(
        dataset.value_labels()
    )
    selected = []

    for column in dataset.dataframe.columns:
        name = str(
            column
        )
        series = dataset.dataframe[column]
        dtype = series.dtype
        has_value_labels = name in value_label_columns
        is_candidate = (
            has_value_labels
            or pd.api.types.is_bool_dtype(
                dtype
            )
            or isinstance(
                dtype,
                pd.CategoricalDtype,
            )
            or pd.api.types.is_string_dtype(
                dtype
            )
            or pd.api.types.is_object_dtype(
                dtype
            )
        )

        if not is_candidate:
            continue

        unique_count = _safe_unique_count(
            series.dropna()
        )

        if max_unique is not None and unique_count > max_unique and not has_value_labels:
            continue

        selected.append(
            column
        )

    return selected


def _selected_columns(
    dataset: Dataset,
    columns: list[str] | None,
) -> list[Any]:
    """
    Resolve and validate requested columns.
    """

    if columns is None:
        return list(
            dataset.dataframe.columns
        )

    return [
        _resolve_column(
            dataset,
            column,
        )
        for column in columns
    ]


def _resolve_column(
    dataset: Dataset,
    column: str,
) -> Any:
    """
    Resolve a string column name to the DataFrame column label.
    """

    column_lookup = {
        str(dataframe_column): dataframe_column
        for dataframe_column in dataset.dataframe.columns
    }

    if column not in column_lookup:
        raise InspectionError(
            f"Column not found: {column}"
        )

    return column_lookup[column]


def _lookup_value_label(
    value_labels: dict[Any, str],
    value: Any,
) -> str | None:
    """
    Return a value label, handling equivalent missing and scalar values.
    """

    for labelled_value, label in value_labels.items():
        if _values_match(
            labelled_value,
            value,
        ):
            return label

    return None


def _values_match(
    left: Any,
    right: Any,
) -> bool:
    """
    Compare scalar values defensively.
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


def _safe_unique_count(series: pd.Series) -> int:
    """Return a unique count for hashable and unhashable object values."""

    try:
        return int(series.nunique(dropna=True))
    except (TypeError, ValueError):
        unique_values = []
        for value in series.tolist():
            if not any(_values_match(value, existing) for existing in unique_values):
                unique_values.append(value)
        return len(unique_values)


def _safe_value_counts(
    series: pd.Series,
    include_missing: bool,
) -> list[tuple[Any, int]]:
    """Return stable value counts, including for unhashable object values."""

    try:
        counts = series.value_counts(dropna=not include_missing)
        return [(value, int(count)) for value, count in counts.items()]
    except (TypeError, ValueError):
        counted: list[list[Any]] = []
        for value in series.tolist():
            if not include_missing and _is_missing(value):
                continue
            for item in counted:
                if _values_match(value, item[0]):
                    item[1] += 1
                    break
            else:
                counted.append([value, 1])
        counted.sort(key=lambda item: item[1], reverse=True)
        return [(item[0], int(item[1])) for item in counted]


def _safe_duplicate_rows(dataframe: pd.DataFrame) -> int:
    """Count duplicate rows defensively when cells contain unhashable values."""

    try:
        return int(dataframe.duplicated().sum())
    except (TypeError, ValueError):
        seen: list[list[Any]] = []
        duplicates = 0
        for row in dataframe.itertuples(index=False, name=None):
            values = list(row)
            if any(_rows_match(values, existing) for existing in seen):
                duplicates += 1
            else:
                seen.append(values)
        return duplicates


def _rows_match(left: list[Any], right: list[Any]) -> bool:
    return len(left) == len(right) and all(
        _values_match(left_value, right_value)
        for left_value, right_value in zip(left, right)
    )


def _is_missing(value: Any) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _percent(
    count: int,
    total: int,
) -> float:
    """
    Return percentage for count/total.
    """

    if total == 0:
        return 0.0

    return count / total * 100


def _safe_float(
    value: Any
) -> float | None:
    """
    Return a finite-ish Python float or None for missing values.
    """

    if pd.isna(
        value
    ):
        return None

    return float(
        value
    )

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DatasetSummary:
    """
    High-level profile of a dataset.
    """

    row_count: int
    column_count: int
    numeric_columns: int
    text_columns: int
    boolean_columns: int
    datetime_columns: int
    categorical_columns: int
    other_columns: int
    columns_with_variable_labels: int
    columns_with_value_labels: int
    total_missing_cells: int
    duplicate_rows: int
    memory_usage_bytes: int | None = None


@dataclass
class NumericProfile:
    """
    Numeric descriptive statistics for one column.
    """

    count: int
    mean: float | None = None
    std: float | None = None
    min: float | None = None
    q1: float | None = None
    median: float | None = None
    q3: float | None = None
    max: float | None = None


@dataclass
class CategoricalProfile:
    """
    Categorical summary for one column.
    """

    count: int
    unique_count: int
    top_value: Any | None = None
    top_label: str | None = None
    top_count: int | None = None
    top_percent: float | None = None


@dataclass
class ColumnProfile:
    """
    Profile for one dataset column.
    """

    name: str
    storage_type: str
    label: str | None = None
    non_missing_count: int = 0
    missing_count: int = 0
    missing_percent: float = 0.0
    unique_count: int | None = None
    profile_type: str = "unknown"
    numeric: NumericProfile | None = None
    categorical: CategoricalProfile | None = None


@dataclass
class MissingProfile:
    """
    Missing-value summary for one column.
    """

    column: str
    missing_count: int
    missing_percent: float
    label: str | None = None
    metadata_missing_values: list[Any] = field(default_factory=list)


@dataclass
class FrequencyItem:
    """
    One value-count row.
    """

    value: Any
    count: int
    percent: float
    label: str | None = None


@dataclass
class FrequencyTable:
    """
    Frequency table for one column.
    """

    column: str
    total_count: int
    missing_count: int
    label: str | None = None
    items: list[FrequencyItem] = field(default_factory=list)


@dataclass
class ValidationIssue:
    """
    Future validation result.
    """

    severity: str
    code: str
    message: str
    column: str | None = None

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

from statconvert.compare.exceptions import CompareError


@dataclass(frozen=True)
class CompareOptions:
    """Options that refine dataset comparison."""

    ignore_columns: tuple[str, ...] = ()
    numeric_tolerance: float = 0.0
    key_columns: tuple[str, ...] = ()
    max_differences: int = 50

    def __post_init__(self) -> None:
        if self.numeric_tolerance < 0 or math.isnan(self.numeric_tolerance):
            raise CompareError(
                "--numeric-tolerance must be greater than or equal to 0."
            )
        if self.max_differences <= 0:
            raise CompareError("--max-differences must be greater than 0.")
        blank_keys = [column for column in self.key_columns if not column]
        if blank_keys:
            raise CompareError("Key column names cannot be blank.")
        duplicate_keys = _duplicates(self.key_columns)
        if duplicate_keys:
            raise CompareError(f"Duplicate key column specified: {duplicate_keys[0]}")
        ignored_keys = [
            column for column in self.key_columns if column in self.ignore_columns
        ]
        if ignored_keys:
            raise CompareError(
                f"Key columns cannot be ignored: {', '.join(ignored_keys)}"
            )


@dataclass
class CompareIssue:
    """One noteworthy difference between two datasets."""

    severity: str
    code: str
    message: str
    column: str | None = None


@dataclass
class DifferenceDetail:
    """One bounded, serializable example of a comparison difference."""

    kind: str
    row: int | None = None
    key: dict[str, Any] | None = None
    column: str | None = None
    left: Any = None
    right: Any = None
    message: str | None = None


@dataclass
class ShapeComparison:
    left_rows: int
    right_rows: int
    left_columns: int
    right_columns: int
    rows_match: bool
    columns_match: bool


@dataclass
class ColumnComparison:
    left_columns: list[str]
    right_columns: list[str]
    common_columns: list[str]
    left_only_columns: list[str]
    right_only_columns: list[str]
    same_columns: bool
    same_order: bool


@dataclass
class SchemaComparison:
    storage_type_changes: dict[str, tuple[str | None, str | None]]
    same_storage_types: bool
    display_format_changes: dict[str, tuple[str | None, str | None]] = field(
        default_factory=dict
    )
    measurement_level_changes: dict[str, tuple[str | None, str | None]] = field(
        default_factory=dict
    )


@dataclass
class MetadataComparison:
    variable_label_changes: dict[str, tuple[str | None, str | None]]
    value_label_changes: dict[str, tuple[dict[Any, str], dict[Any, str]]]
    missing_value_changes: dict[str, tuple[list[Any], list[Any]]]
    same_variable_labels: bool
    same_value_labels: bool
    same_missing_values: bool


@dataclass
class ValueComparison:
    compared_rows: int
    compared_columns: int
    cells_compared: int
    differing_cells: int
    same_values: bool
    sampled: bool = False
    sample_size: int | None = None
    differences_by_column: dict[str, int] = field(default_factory=dict)


@dataclass
class DatasetComparison:
    shape: ShapeComparison
    columns: ColumnComparison
    schema: SchemaComparison
    metadata: MetadataComparison
    values: ValueComparison | None = None
    left_source: str | None = None
    right_source: str | None = None
    issues: list[CompareIssue] = field(default_factory=list)
    options: CompareOptions = field(default_factory=CompareOptions)
    columns_compared: list[str] = field(default_factory=list)
    row_matching_mode: str = "positional"
    key_columns: list[str] = field(default_factory=list)
    matched_rows: int = 0
    rows_only_left: int = 0
    rows_only_right: int = 0
    differences: list[DifferenceDetail] = field(default_factory=list)
    detailed_differences_total: int = 0
    detailed_differences_shown: int = 0
    detailed_differences_truncated: bool = False

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(issue.severity == "warning" for issue in self.issues)

    @property
    def is_identical(self) -> bool:
        return all(
            (
                self.shape.rows_match,
                self.shape.columns_match,
                self.columns.same_columns,
                self.columns.same_order,
                self.schema.same_storage_types,
                not self.schema.display_format_changes,
                not self.schema.measurement_level_changes,
                self.metadata.same_variable_labels,
                self.metadata.same_value_labels,
                self.metadata.same_missing_values,
                self.rows_only_left == 0,
                self.rows_only_right == 0,
                self.values is not None and self.values.same_values,
            )
        )

    @property
    def is_compatible(self) -> bool:
        return not self.has_errors


def _duplicates(values: tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates

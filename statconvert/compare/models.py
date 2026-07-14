from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CompareIssue:
    """One noteworthy difference between two datasets."""

    severity: str
    code: str
    message: str
    column: str | None = None


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
                self.values is not None and self.values.same_values,
            )
        )

    @property
    def is_compatible(self) -> bool:
        return not self.has_errors

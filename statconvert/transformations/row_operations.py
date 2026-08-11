from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import pandas as pd

from statconvert.dataset import ColumnMetadata, Dataset
from statconvert.metadata import VariableMetadata
from statconvert.transformations.base import Transformation
from statconvert.transformations.exceptions import TransformationError


@dataclass(frozen=True)
class SortKey:
    """One validated stable-sort key."""

    column: str
    order: str = "ascending"
    nulls: str = "last"

    def __post_init__(self) -> None:
        if not isinstance(self.column, str) or not self.column.strip():
            raise TransformationError("Sort key column must be non-blank text.")
        if self.order not in {"ascending", "descending"}:
            raise TransformationError(
                "Sort key order must be 'ascending' or 'descending'."
            )
        if self.nulls not in {"first", "last"}:
            raise TransformationError("Sort key nulls must be 'first' or 'last'.")


class SortRowsTransformation(Transformation):
    """Stably sort rows by one or more ordered key specifications."""

    name = "sort-rows"
    description = "Stably sort rows by one or more columns."

    def __init__(self, keys: Sequence[SortKey]) -> None:
        self.keys = tuple(keys)
        if not self.keys:
            raise TransformationError("At least one sort key must be provided.")
        columns = [key.column for key in self.keys]
        duplicates = _duplicates(columns)
        if duplicates:
            raise TransformationError(
                "Duplicate sort key column(s): " + ", ".join(duplicates)
            )

    def apply(self, dataset: Dataset) -> Dataset:
        _validate_columns(dataset, [key.column for key in self.keys], "sort")
        result = dataset.copy()
        dataframe = result.dataframe
        # Sorting from the least-significant key to the most-significant key with
        # mergesort preserves authored lexicographic priority and per-key null policy.
        for key in reversed(self.keys):
            dataframe = dataframe.sort_values(
                by=key.column,
                ascending=key.order == "ascending",
                na_position=key.nulls,
                kind="mergesort",
            )
        result.dataframe = dataframe.reset_index(drop=True)
        return result


class DistinctRowsTransformation(Transformation):
    """Keep the first or last row for each authored key combination."""

    name = "distinct-rows"
    description = "Drop duplicate rows by key columns while preserving retained order."

    def __init__(self, columns: Sequence[str], keep: str = "first") -> None:
        self.columns = tuple(columns)
        self.keep = keep
        if not self.columns:
            raise TransformationError("At least one distinct column must be provided.")
        if not all(isinstance(column, str) and column.strip() for column in self.columns):
            raise TransformationError("Distinct columns must be non-blank text.")
        duplicates = _duplicates(self.columns)
        if duplicates:
            raise TransformationError(
                "Duplicate distinct column(s): " + ", ".join(duplicates)
            )
        if keep not in {"first", "last"}:
            raise TransformationError("Distinct keep must be 'first' or 'last'.")

    def apply(self, dataset: Dataset) -> Dataset:
        _validate_columns(dataset, list(self.columns), "distinct")
        result = dataset.copy()
        result.dataframe = result.dataframe.drop_duplicates(
            subset=list(self.columns),
            keep=self.keep,
        ).reset_index(drop=True)
        return result


class RowNumberTransformation(Transformation):
    """Append deterministic integer values based on current row order."""

    name = "row-number"
    description = "Append a deterministic row-number column."

    def __init__(self, column: str, start: int = 1, step: int = 1) -> None:
        if not isinstance(column, str) or not column.strip():
            raise TransformationError("Row-number column must be non-blank text.")
        if isinstance(start, bool) or not isinstance(start, int):
            raise TransformationError("Row-number start must be an integer.")
        if isinstance(step, bool) or not isinstance(step, int) or step <= 0:
            raise TransformationError("Row-number step must be a positive integer.")
        self.column = column
        self.start = start
        self.step = step

    def apply(self, dataset: Dataset) -> Dataset:
        if self.column in {str(column) for column in dataset.columns}:
            raise TransformationError(
                f"Row-number column already exists: {self.column}"
            )
        result = dataset.copy()
        stop = self.start + result.rows * self.step
        result.dataframe[self.column] = pd.Series(
            range(self.start, stop, self.step),
            index=result.dataframe.index,
            dtype="int64",
        )
        _add_row_number_metadata(result, self.column)
        return result


def _add_row_number_metadata(dataset: Dataset, column: str) -> None:
    series = dataset.dataframe[column]
    storage_type = str(series.dtype)
    dataset.get_normalized_metadata().add_variable(
        VariableMetadata(
            name=column,
            storage_type=storage_type,
            measure="scale",
        )
    )
    dataset.column_metadata[column] = ColumnMetadata(
        name=column,
        physical_type=storage_type,
        logical_type=Dataset._infer_logical_type_from_dtype(series.dtype),
        source_format=dataset.source_format,
        measure="scale",
    )
    columns_provenance = dataset.metadata_provenance.setdefault("columns", {})
    if isinstance(columns_provenance, dict):
        columns_provenance[column] = "generated"
    dataset.sync_metadata()


def _validate_columns(dataset: Dataset, columns: list[str], operation: str) -> None:
    available = {str(column) for column in dataset.columns}
    missing = [column for column in columns if column not in available]
    if missing:
        raise TransformationError(
            "Column not found: " + ", ".join(missing) + f" (operation: {operation})"
        )


def _duplicates(values: Sequence[Any]) -> list[str]:
    seen: list[Any] = []
    duplicates: list[str] = []
    for value in values:
        if value in seen and str(value) not in duplicates:
            duplicates.append(str(value))
        seen.append(value)
    return duplicates

"""Stable ordered-column and conservative dtype checks for streamed chunks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from numbers import Integral, Real

import pandas as pd
from pandas.api import types as pandas_types

from statconvert.dataset import Dataset
from statconvert.streaming.errors import StreamingSchemaError


_NUMERIC_KINDS = {"integer", "float"}


@dataclass
class StreamingSchemaGuard:
    """Validate chunks against the first observed ordered schema."""

    columns: tuple[str, ...] | None = None
    logical_kinds: list[str] = field(default_factory=list)

    def validate(self, dataset: Dataset) -> None:
        """Establish or validate ordered columns and compatible logical kinds."""

        columns = tuple(str(column) for column in dataset.dataframe.columns)
        if len(set(columns)) != len(columns):
            raise StreamingSchemaError(
                "Streaming schema contains duplicate column names."
            )

        kinds = [
            _series_kind(dataset.dataframe.iloc[:, index])
            for index in range(len(columns))
        ]
        if self.columns is None:
            self.columns = columns
            self.logical_kinds = kinds
            return

        if columns != self.columns:
            raise StreamingSchemaError(
                "Streaming schema drift: ordered columns changed from "
                f"{list(self.columns)} to {list(columns)}."
            )

        for index, (expected, actual) in enumerate(
            zip(self.logical_kinds, kinds, strict=True)
        ):
            column = columns[index]
            reconciled = _reconcile_kind(expected, actual)
            if reconciled is None:
                raise StreamingSchemaError(
                    "Streaming dtype drift for column "
                    f"'{column}': expected {expected}, received {actual}."
                )
            self.logical_kinds[index] = reconciled


def _reconcile_kind(expected: str, actual: str) -> str | None:
    if actual == "missing":
        return expected
    if expected == "missing":
        return actual
    if expected == actual:
        return expected
    if expected in _NUMERIC_KINDS and actual in _NUMERIC_KINDS:
        return "float"
    if {expected, actual} <= {"date", "datetime"}:
        return "datetime"
    return None


def _series_kind(series: pd.Series) -> str:
    non_missing = series.dropna()
    if non_missing.empty:
        return "missing"

    dtype = series.dtype
    if pandas_types.is_bool_dtype(dtype):
        return "boolean"
    if pandas_types.is_integer_dtype(dtype):
        return "integer"
    if pandas_types.is_float_dtype(dtype):
        return "float"
    if pandas_types.is_datetime64_any_dtype(dtype):
        return "datetime"
    if pandas_types.is_string_dtype(dtype) and not pandas_types.is_object_dtype(dtype):
        return "string"

    values = list(non_missing)
    if all(isinstance(value, bool) for value in values):
        return "boolean"
    if all(isinstance(value, Integral) and not isinstance(value, bool) for value in values):
        return "integer"
    if all(isinstance(value, Real) and not isinstance(value, bool) for value in values):
        return "float"
    if all(isinstance(value, str) for value in values):
        return "string"
    if all(isinstance(value, datetime) for value in values):
        return "datetime"
    if all(isinstance(value, date) for value in values):
        return "date"
    return "object"

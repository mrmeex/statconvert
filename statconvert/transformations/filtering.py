from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import pandas as pd

from statconvert.dataset import Dataset
from statconvert.transformations.base import Transformation
from statconvert.transformations.exceptions import TransformationError


@dataclass
class FilterCondition:
    """
    A single explicit row filter condition.
    """

    column: str
    operator: str
    value: Any = None


class FilterRowsTransformation(Transformation):
    """
    Filter dataset rows using explicit conditions.
    """

    name = "filter-rows"
    description = "Filter dataset rows using safe explicit conditions."


    def __init__(
        self,
        conditions: list[FilterCondition],
        mode: str = "and",
        reset_index: bool = True,
    ) -> None:
        if not conditions:
            raise TransformationError(
                "At least one filter condition must be provided."
            )

        if mode not in {
            "and",
            "or",
        }:
            raise TransformationError(
                f"Unsupported filter mode: {mode}"
            )

        self.conditions = conditions
        self.mode = mode
        self.reset_index = reset_index


    def apply(
        self,
        dataset: Dataset
    ) -> Dataset:
        """
        Return a Dataset containing rows that match the conditions.
        """

        dataframe = dataset.dataframe
        masks = [
            _condition_mask(
                dataframe,
                condition,
            )
            for condition in self.conditions
        ]
        combined_mask = _combine_masks(
            masks,
            self.mode,
        )
        result = dataset.copy()
        result.dataframe = result.dataframe.loc[
            combined_mask
        ].copy(
            deep=True
        )

        if self.reset_index:
            result.dataframe = result.dataframe.reset_index(
                drop=True
            )

        return result


def _normalize_operator(
    operator: str
) -> str:
    """
    Normalize supported operator aliases.
    """

    aliases = {
        "=": "eq",
        "==": "eq",
        "!=": "ne",
        "<>": "ne",
        ">": "gt",
        ">=": "gte",
        "<": "lt",
        "<=": "lte",
    }
    normalized = aliases.get(
        operator,
        operator,
    )

    if normalized not in _SUPPORTED_OPERATORS:
        raise TransformationError(
            f"Unsupported filter operator: {operator}"
        )

    return normalized


def _condition_mask(
    dataframe: pd.DataFrame,
    condition: FilterCondition,
) -> pd.Series:
    """
    Return a boolean mask for one condition.
    """

    column = _resolve_column(
        dataframe,
        condition.column,
    )
    operator = _normalize_operator(
        condition.operator
    )
    _validate_condition_value(
        condition,
        operator,
    )
    series = dataframe[column]

    if operator == "eq":
        return _clean_mask(
            series == condition.value,
            dataframe.index,
        )

    if operator == "ne":
        return _clean_mask(
            series != condition.value,
            dataframe.index,
        )

    if operator in _COMPARISON_OPERATORS:
        return _comparison_mask(
            series,
            operator,
            condition.value,
        )

    if operator == "in":
        return _clean_mask(
            series.isin(
                condition.value
            ),
            dataframe.index,
        )

    if operator == "not_in":
        return _clean_mask(
            ~series.isin(
                condition.value
            ),
            dataframe.index,
        )

    if operator in _STRING_OPERATORS:
        return _string_mask(
            series,
            operator,
            condition.value,
        )

    if operator == "is_missing":
        return _clean_mask(
            series.isna(),
            dataframe.index,
        )

    if operator == "not_missing":
        return _clean_mask(
            series.notna(),
            dataframe.index,
        )

    raise TransformationError(
        f"Unsupported filter operator: {condition.operator}"
    )


def _resolve_column(
    dataframe: pd.DataFrame,
    requested_column: str,
) -> Any:
    """
    Resolve a condition column name to the DataFrame's actual column label.
    """

    column_lookup = {
        str(column): column
        for column in dataframe.columns
    }

    if requested_column not in column_lookup:
        raise TransformationError(
            f"Column not found: {requested_column} (operation: --filter)"
        )

    return column_lookup[requested_column]


def _validate_condition_value(
    condition: FilterCondition,
    operator: str,
) -> None:
    """
    Validate whether a condition has the value shape required by its operator.
    """

    if operator in {
        "is_missing",
        "not_missing",
    }:
        return

    if condition.value is None:
        raise TransformationError(
            f"Filter operator '{condition.operator}' requires a value."
        )

    if operator in {
        "in",
        "not_in",
    } and not _is_membership_value(
        condition.value
    ):
        raise TransformationError(
            f"Filter operator '{condition.operator}' requires a list-like value."
        )


def _is_membership_value(
    value: Any
) -> bool:
    """
    Return whether a value can be safely used for membership filtering.
    """

    if isinstance(
        value,
        (
            str,
            bytes,
        ),
    ):
        return False

    return isinstance(
        value,
        Iterable,
    )


def _comparison_mask(
    series: pd.Series,
    operator: str,
    value: Any,
) -> pd.Series:
    """
    Return a mask for comparable operators.
    """

    try:
        if operator == "gt":
            mask = series > value
        elif operator == "gte":
            mask = series >= value
        elif operator == "lt":
            mask = series < value
        elif operator == "lte":
            mask = series <= value
        else:
            raise TransformationError(
                f"Unsupported comparison operator: {operator}"
            )

    except Exception as exc:
        raise TransformationError(
            f"Failed applying filter '{operator}' to column "
            f"'{series.name}': {exc}"
        ) from exc

    return _clean_mask(
        mask,
        series.index,
    )


def _string_mask(
    series: pd.Series,
    operator: str,
    value: Any,
) -> pd.Series:
    """
    Return a mask for string operators.
    """

    string_series = series.astype(
        "string"
    )
    text = str(
        value
    )

    if operator == "contains":
        mask = string_series.str.contains(
            text,
            regex=False,
            na=False,
        )

    elif operator == "not_contains":
        # Missing values are treated as non-matches, so they remain included
        # when applying the inverse "not contains" operation.
        mask = ~string_series.str.contains(
            text,
            regex=False,
            na=False,
        )

    elif operator == "startswith":
        mask = string_series.str.startswith(
            text,
            na=False,
        )

    elif operator == "endswith":
        mask = string_series.str.endswith(
            text,
            na=False,
        )

    else:
        raise TransformationError(
            f"Unsupported string operator: {operator}"
        )

    return _clean_mask(
        mask,
        series.index,
    )


def _combine_masks(
    masks: list[pd.Series],
    mode: str,
) -> pd.Series:
    """
    Combine condition masks using the requested mode.
    """

    combined = masks[0].copy()

    for mask in masks[1:]:
        if mode == "and":
            combined = combined & mask

        else:
            combined = combined | mask

    return _clean_mask(
        combined,
        combined.index,
    )


def _clean_mask(
    mask: pd.Series,
    index: pd.Index,
) -> pd.Series:
    """
    Return a strict boolean Series aligned to the provided index.
    """

    return pd.Series(
        mask,
        index=index,
    ).fillna(
        False
    ).astype(
        bool
    )


_COMPARISON_OPERATORS = {
    "gt",
    "gte",
    "lt",
    "lte",
}

_STRING_OPERATORS = {
    "contains",
    "not_contains",
    "startswith",
    "endswith",
}

_SUPPORTED_OPERATORS = {
    "eq",
    "ne",
    "in",
    "not_in",
    "is_missing",
    "not_missing",
    *_COMPARISON_OPERATORS,
    *_STRING_OPERATORS,
}

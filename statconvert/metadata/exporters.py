from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from statconvert.dataset import Dataset


def column_labels_from_metadata(
    dataset: Dataset
) -> dict[str, str]:
    """
    Return column labels supported by the dataset's current columns.
    """

    columns = _dataset_columns(
        dataset
    )

    return {
        name: label
        for name, label in dataset.variable_labels().items()
        if name in columns and label
    }


def variable_value_labels_from_metadata(
    dataset: Dataset
) -> dict[str, dict[Any, str]]:
    """
    Return value labels supported by the dataset's current columns.
    """

    columns = _dataset_columns(
        dataset
    )

    return {
        name: labels
        for name, labels in dataset.value_labels().items()
        if name in columns and labels
    }


def missing_values_from_metadata(
    dataset: Dataset
) -> dict[str, list[Any]]:
    """
    Return missing value metadata supported by the dataset's current columns.
    """

    columns = _dataset_columns(
        dataset
    )

    return {
        name: values
        for name, values in dataset.missing_values().items()
        if name in columns and values
    }


def missing_ranges_from_metadata(
    dataset: Dataset
) -> dict[str, list[dict[str, Any]]]:
    """Return explicit missing ranges for current dataset columns."""

    columns = _dataset_columns(dataset)
    return {
        name: ranges
        for name, ranges in dataset.missing_ranges().items()
        if name in columns and ranges
    }


def display_widths_from_metadata(dataset: Dataset) -> dict[str, int]:
    """Return normalized display widths for current dataset columns."""

    columns = _dataset_columns(dataset)
    return {
        name: variable.display_width
        for name, variable in dataset.variables_metadata().items()
        if name in columns and variable.display_width is not None
    }


def _dataset_columns(
    dataset: Dataset
) -> set[str]:
    """
    Return DataFrame column names as strings for metadata filtering.
    """

    return {
        str(column)
        for column in dataset.dataframe.columns
    }

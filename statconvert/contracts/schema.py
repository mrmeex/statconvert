from __future__ import annotations

import pandas as pd

from statconvert.dataset import Dataset


def resolved_logical_type(
    dataset: Dataset,
    name: str,
    series: pd.Series,
) -> str | None:
    """Return the resolved logical type for one physical column."""

    column = dataset.column_metadata.get(name)
    if column is not None and column.logical_type:
        return column.logical_type
    inferred = Dataset._infer_logical_type_from_dtype(series.dtype)
    return None if inferred == "unknown" else inferred

from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from decimal import Decimal
import math
from numbers import Integral, Real
from typing import Any

import numpy as np
import pandas as pd

from statconvert.metadata import VariableMetadata

from .models import ColumnScanSummary


MAX_VALUE_FAMILIES = 8


def scan_column(series: pd.Series, variable: VariableMetadata | None) -> ColumnScanSummary:
    """Fully scan one column and return aggregate deterministic evidence."""

    missing_mask = series.isna()
    values = series.loc[~missing_mask]
    families = Counter(_value_family(value) for value in values.tolist())
    family_items = sorted(families.items(), key=lambda item: item[0])
    bounded_families = dict(family_items[:MAX_VALUE_FAMILIES])
    omitted_families = max(0, len(family_items) - len(bounded_families))

    minimum, maximum = _numeric_bounds(values)
    string_lengths = [len(value) for value in values.tolist() if isinstance(value, str)]
    max_string_length = max(string_lengths) if string_lengths else None
    integer_exactness = _integer_exactness(values)
    float32_exactness = _float32_exactness(values)
    date_only = _date_only_compatible(values)
    timezone = _timezone_summary(values, series.dtype)

    category_count = None
    category_ordered = None
    if isinstance(series.dtype, pd.CategoricalDtype):
        category_count = len(series.cat.categories)
        category_ordered = bool(series.cat.ordered)

    return ColumnScanSummary(
        rows_scanned=len(series),
        non_missing_count=len(values),
        missing_count=int(missing_mask.sum()),
        minimum=minimum,
        maximum=maximum,
        max_string_length=max_string_length,
        string_length_unit="unicode_code_points" if max_string_length is not None else None,
        integer_exactness=integer_exactness,
        float32_exactness=float32_exactness,
        date_only_compatible=date_only,
        timezone_summary=timezone,
        value_family_counts=bounded_families,
        value_family_count_truncated=omitted_families,
        category_count=category_count,
        category_ordered=category_ordered,
    )


def protected_relationships(variable: VariableMetadata | None) -> dict[str, Any]:
    """Return counts/flags only; never expose label or missing-definition values."""

    if variable is None:
        return {
            "value_labels": 0,
            "missing_values": 0,
            "missing_ranges": 0,
            "protected": False,
        }
    return {
        "value_labels": len(variable.value_labels),
        "missing_values": len(variable.missing_values),
        "missing_ranges": len(variable.missing_ranges),
        "protected": bool(
            variable.value_labels or variable.missing_values or variable.missing_ranges
        ),
    }


def _numeric_bounds(values: pd.Series) -> tuple[int | float | None, int | float | None]:
    if values.empty or pd.api.types.is_bool_dtype(values.dtype):
        return None, None
    if not pd.api.types.is_numeric_dtype(values.dtype):
        if not all(isinstance(value, Real) and not isinstance(value, bool) for value in values):
            return None, None
    try:
        minimum = _safe_number(values.min())
        maximum = _safe_number(values.max())
    except (TypeError, ValueError):
        return None, None
    return minimum, maximum


def _safe_number(value: Any) -> int | float | None:
    if isinstance(value, Integral) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, Real) and not isinstance(value, bool):
        result = float(value)
        return result if math.isfinite(result) else None
    return None


def _integer_exactness(values: pd.Series) -> bool | None:
    if values.empty or pd.api.types.is_bool_dtype(values.dtype):
        return None
    if not pd.api.types.is_numeric_dtype(values.dtype):
        return None
    try:
        array = values.to_numpy(dtype="float64", na_value=np.nan)
    except (TypeError, ValueError):
        return None
    return bool(np.isfinite(array).all() and np.equal(array, np.trunc(array)).all())


def _float32_exactness(values: pd.Series) -> bool | None:
    if values.empty or not pd.api.types.is_float_dtype(values.dtype):
        return None
    array = values.to_numpy(dtype="float64", na_value=np.nan)
    with np.errstate(over="ignore", invalid="ignore"):
        narrowed = array.astype("float32")
    restored = narrowed.astype("float64")
    if not np.array_equal(array, restored, equal_nan=True):
        return False
    zero_mask = array == 0
    if zero_mask.any() and not np.array_equal(np.signbit(array[zero_mask]), np.signbit(restored[zero_mask])):
        return False
    return True


def _date_only_compatible(values: pd.Series) -> bool | None:
    if values.empty:
        return None
    saw_temporal = False
    for value in values.tolist():
        if isinstance(value, pd.Timestamp):
            value = value.to_pydatetime()
        if isinstance(value, datetime):
            saw_temporal = True
            if any((value.hour, value.minute, value.second, value.microsecond)):
                return False
        elif isinstance(value, date):
            saw_temporal = True
        else:
            return None
    return True if saw_temporal else None


def _timezone_summary(values: pd.Series, dtype: Any) -> str | None:
    timezone = getattr(dtype, "tz", None)
    if timezone is not None:
        return f"aware:{timezone}"
    temporal = []
    for value in values.tolist():
        if isinstance(value, pd.Timestamp):
            value = value.to_pydatetime()
        if isinstance(value, datetime):
            temporal.append(value)
    if not temporal:
        return None
    awareness = {value.tzinfo is not None and value.utcoffset() is not None for value in temporal}
    if awareness == {False}:
        return "naive"
    if awareness == {True}:
        zones = sorted({str(value.tzinfo) for value in temporal})
        return "aware:" + ",".join(zones[:4])
    return "mixed-aware-naive"


def _value_family(value: Any) -> str:
    if isinstance(value, (bool, np.bool_)):
        return "boolean"
    if isinstance(value, (Integral, np.integer)):
        return "integer"
    if isinstance(value, (Real, np.floating)):
        return "float"
    if isinstance(value, Decimal):
        return "decimal"
    if isinstance(value, str):
        return "string"
    if isinstance(value, datetime):
        return "datetime"
    if isinstance(value, date):
        return "date"
    if isinstance(value, bytes):
        return "bytes"
    if isinstance(value, dict):
        return "mapping"
    if isinstance(value, (list, tuple, set)):
        return "sequence"
    return type(value).__name__.lower()

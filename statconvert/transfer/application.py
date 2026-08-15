from __future__ import annotations

from dataclasses import dataclass
import re

import numpy as np
import pandas as pd

from statconvert.dataset import Dataset

from .models import ColumnTypeDecision, TransferPlan
from .policies import TransferPlanningError


_INTEGER_DTYPE = re.compile(r"(?:u?int|U?Int)(?:8|16|32|64)\Z")


@dataclass(frozen=True)
class TransferApplicationResult:
    """Result of applying exact supported decisions to a deep dataset copy."""

    dataset: Dataset
    applied_columns: tuple[str, ...]
    retained_columns: tuple[str, ...]
    unsupported_proposals: tuple[str, ...]

    @property
    def applied_count(self) -> int:
        return len(self.applied_columns)

    def to_summary_dict(self) -> dict[str, object]:
        return {
            "applied_count": self.applied_count,
            "applied_columns": list(self.applied_columns),
            "retained_count": len(self.retained_columns),
            "unsupported_proposal_count": len(self.unsupported_proposals),
            "unsupported_proposal_columns": list(self.unsupported_proposals),
        }


def apply_transfer_plan(dataset: Dataset, plan: TransferPlan) -> TransferApplicationResult:
    """Apply exact smallest-type storage decisions to a deep copy only."""

    if plan.policy != "smallest-types":
        raise TransferPlanningError(
            "Type optimization requires the smallest-types policy.",
            code="TRANSFER_APPLICATION_POLICY_INVALID",
        )
    if plan.status == "blocked":
        raise TransferPlanningError(
            "A blocked transfer plan cannot be applied.",
            code="TRANSFER_POLICY_BLOCKED",
        )

    result = dataset.copy(deep=True)
    original_columns = list(dataset.dataframe.columns)
    original_rows = dataset.rows
    applied: list[str] = []
    retained: list[str] = []
    unsupported: list[str] = []

    for decision in plan.decisions:
        if decision.action not in {"narrow", "widen", "semantic_convert"}:
            retained.append(decision.column)
            continue
        if decision.lossy or decision.metadata_impact.get("protected"):
            retained.append(decision.column)
            unsupported.append(decision.column)
            continue
        if not _is_supported_storage_application(decision):
            retained.append(decision.column)
            unsupported.append(decision.column)
            continue
        _apply_column(result, dataset, decision)
        applied.append(decision.column)

    if result.rows != original_rows or list(result.dataframe.columns) != original_columns:
        raise TransferPlanningError(
            "Type application changed dataset shape or column order.",
            code="TRANSFER_APPLICATION_INVARIANT_FAILED",
        )
    result.sync_metadata()
    return TransferApplicationResult(
        dataset=result,
        applied_columns=tuple(applied),
        retained_columns=tuple(retained),
        unsupported_proposals=tuple(unsupported),
    )


def _is_supported_storage_application(decision: ColumnTypeDecision) -> bool:
    proposed = decision.proposed_storage_type
    current = decision.current_storage_type.lower()
    if _INTEGER_DTYPE.fullmatch(proposed) and "int" in current:
        return True
    return proposed == "float32" and current.startswith("float64")


def _apply_column(
    result: Dataset,
    original: Dataset,
    decision: ColumnTypeDecision,
) -> None:
    column = decision.column
    source = original.dataframe[column]
    missing_before = source.isna()
    try:
        converted = source.astype(decision.proposed_storage_type)
    except (TypeError, ValueError, OverflowError) as exc:
        raise TransferPlanningError(
            f"Exact type application failed for column {column}: {exc}",
            code="TRANSFER_APPLICATION_FAILED",
        ) from exc

    if not converted.isna().equals(missing_before):
        raise TransferPlanningError(
            f"Type application changed missingness for column {column}.",
            code="TRANSFER_APPLICATION_INVARIANT_FAILED",
        )
    if not _values_equal(source, converted):
        raise TransferPlanningError(
            f"Type application changed values for column {column}.",
            code="TRANSFER_APPLICATION_INVARIANT_FAILED",
        )

    result.dataframe[column] = converted
    variable = result.get_normalized_metadata().get_variable(column)
    if variable is not None:
        variable.storage_type = decision.proposed_storage_type
    column_metadata = result.column_metadata.get(column)
    if column_metadata is not None:
        column_metadata.physical_type = decision.proposed_storage_type
        column_metadata.logical_type = decision.proposed_logical_type


def _values_equal(original: pd.Series, converted: pd.Series) -> bool:
    mask = ~original.isna()
    left = original.loc[mask]
    right = converted.loc[mask]
    if pd.api.types.is_float_dtype(original.dtype):
        left_values = left.to_numpy(dtype="float64")
        right_values = right.to_numpy(dtype="float64")
        if not np.array_equal(left_values, right_values, equal_nan=True):
            return False
        zero_mask = left_values == 0
        return not zero_mask.any() or np.array_equal(
            np.signbit(left_values[zero_mask]),
            np.signbit(right_values[zero_mask]),
        )
    try:
        return bool((left.to_numpy() == right.to_numpy()).all())
    except (TypeError, ValueError):
        return False

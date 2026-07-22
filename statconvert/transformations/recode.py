from __future__ import annotations

from typing import Any

import pandas as pd

from statconvert.dataset import Dataset
from statconvert.transformations.base import Transformation
from statconvert.transformations.exceptions import TransformationError


class RecodeValuesTransformation(Transformation):
    """
    Recode values in one or more dataset columns.
    """

    name = "recode-values"
    description = "Replace values in selected dataset columns."


    def __init__(
        self,
        recode_map: dict[str, dict[Any, Any]],
        default: Any = None,
        use_default: bool = False,
        update_value_labels: bool = True,
        drop_unmapped_value_labels: bool = False,
    ) -> None:
        if not recode_map:
            raise TransformationError(
                "At least one recode mapping must be provided."
            )

        _validate_mapping_shapes(
            recode_map
        )

        self.recode_map = recode_map
        self.default = default
        self.use_default = use_default
        self.update_value_labels = update_value_labels
        self.drop_unmapped_value_labels = drop_unmapped_value_labels


    def apply(
        self,
        dataset: Dataset
    ) -> Dataset:
        """
        Return a Dataset with requested values recoded.
        """

        _validate_columns_exist(
            dataset,
            list(
                self.recode_map
            ),
        )

        result = dataset.copy()

        for column, mapping in self.recode_map.items():
            result.dataframe[column] = _apply_recode(
                result.dataframe[column],
                mapping=mapping,
                default=self.default,
                use_default=self.use_default,
            )
            _update_variable_metadata(
                result,
                column=column,
                mapping=mapping,
                default=self.default,
                use_default=self.use_default,
                update_value_labels=self.update_value_labels,
                drop_unmapped_value_labels=self.drop_unmapped_value_labels,
            )

        result.sync_metadata()

        return result


def _validate_mapping_shapes(
    recode_map: dict[str, dict[Any, Any]]
) -> None:
    """
    Validate recode mapping structure.
    """

    for column, mapping in recode_map.items():
        if not isinstance(
            mapping,
            dict,
        ):
            raise TransformationError(
                f"Recode mapping for column '{column}' must be a dict."
            )

        if not mapping:
            raise TransformationError(
                f"Recode mapping for column '{column}' cannot be empty."
            )


def _validate_columns_exist(
    dataset: Dataset,
    columns: list[str],
) -> None:
    """
    Validate that all requested columns exist.
    """

    available_columns = {
        str(column)
        for column in dataset.dataframe.columns
    }
    missing_columns = [
        column
        for column in columns
        if column not in available_columns
    ]

    if missing_columns:
        raise TransformationError(
            "Column not found: "
            + ", ".join(
                missing_columns
            )
            + " (operation: --recode)"
        )


def _apply_recode(
    series: pd.Series,
    mapping: dict[Any, Any],
    default: Any = None,
    use_default: bool = False,
) -> pd.Series:
    """
    Return a recoded Series while preserving unmapped missing values.
    """

    values = [
        _recode_scalar(
            value,
            mapping=mapping,
            default=default,
            use_default=use_default,
        )
        for value in series
    ]

    return pd.Series(
        values,
        index=series.index,
        name=series.name,
        dtype=object,
    )


def _recode_scalar(
    value: Any,
    mapping: dict[Any, Any],
    default: Any = None,
    use_default: bool = False,
) -> Any:
    """
    Recode one scalar value.
    """

    was_mapped, mapped_value = _mapped_value(
        value,
        mapping,
    )

    if was_mapped:
        return mapped_value

    if _is_missing_value(
        value
    ):
        return value

    if use_default:
        # A default of None is allowed deliberately; callers can use it to
        # collapse unmapped non-missing values to missing-like Python None.
        return default

    return value


def _mapped_value(
    value: Any,
    mapping: dict[Any, Any],
) -> tuple[bool, Any]:
    """
    Return whether a value is mapped and the mapped value.
    """

    for old_value, new_value in mapping.items():
        if _values_match(
            value,
            old_value,
        ):
            return True, new_value

    return False, None


def _update_variable_metadata(
    dataset: Dataset,
    column: str,
    mapping: dict[Any, Any],
    default: Any = None,
    use_default: bool = False,
    update_value_labels: bool = True,
    drop_unmapped_value_labels: bool = False,
) -> None:
    """
    Update normalized metadata after a value recode.
    """

    metadata = dataset.get_normalized_metadata()
    variable = metadata.get_variable(
        column
    )

    if not variable:
        return

    variable.storage_type = str(
        dataset.dataframe[column].dtype
    )
    variable.missing_values = _recode_missing_values(
        variable.missing_values,
        mapping,
    )

    if not update_value_labels:
        return

    value_labels, notes = _recode_value_labels(
        value_labels=variable.value_labels,
        mapping=mapping,
        column=column,
        default=default,
        use_default=use_default,
        drop_unmapped=drop_unmapped_value_labels,
    )
    variable.value_labels = value_labels

    for note in notes:
        if note not in metadata.notes:
            metadata.notes.append(
                note
            )


def _recode_value_labels(
    value_labels: dict[Any, str],
    mapping: dict[Any, Any],
    column: str,
    default: Any = None,
    use_default: bool = False,
    drop_unmapped: bool = False,
) -> tuple[dict[Any, str], list[str]]:
    """
    Return recoded value labels and deterministic notes.
    """

    if not value_labels:
        return {}, []

    recoded_labels = {}
    notes = []
    default_label_count = 0

    for old_value, label in value_labels.items():
        was_mapped, new_value = _mapped_value(
            old_value,
            mapping,
        )

        if not was_mapped and use_default:
            new_value = default
            was_mapped = True
            default_label_count += 1

        if was_mapped:
            if new_value not in recoded_labels:
                recoded_labels[new_value] = label

            elif recoded_labels[new_value] != label:
                _append_note_once(
                    notes,
                    f"Value labels merged during recode for column {column}.",
                )

            continue

        if not drop_unmapped:
            recoded_labels[old_value] = label

    if use_default and default_label_count > 1:
        _append_note_once(
            notes,
            f"Unmapped value labels collapsed to default during recode for column {column}.",
        )

    return recoded_labels, notes


def _recode_missing_values(
    missing_values: list[Any],
    mapping: dict[Any, Any],
) -> list[Any]:
    """
    Return missing value metadata with mapped missing values updated.
    """

    recoded_values = []

    for value in missing_values:
        was_mapped, mapped_value = _mapped_value(
            value,
            mapping,
        )
        next_value = mapped_value if was_mapped else value

        if not _contains_value(
            recoded_values,
            next_value,
        ):
            recoded_values.append(
                next_value
            )

    return recoded_values


def _append_note_once(
    notes: list[str],
    note: str,
) -> None:
    """
    Append a note only once.
    """

    if note not in notes:
        notes.append(
            note
        )


def _contains_value(
    values: list[Any],
    candidate: Any,
) -> bool:
    """
    Return whether a list already contains an equivalent scalar value.
    """

    return any(
        _values_match(
            value,
            candidate,
        )
        for value in values
    )


def _values_match(
    left: Any,
    right: Any,
) -> bool:
    """
    Compare scalar values while treating missing values as equivalent.
    """

    if _is_missing_value(
        left
    ) and _is_missing_value(
        right
    ):
        return True

    try:
        return bool(
            left == right
        )

    except Exception:
        return False


def _is_missing_value(
    value: Any
) -> bool:
    """
    Return whether a scalar value is missing.
    """

    try:
        result = pd.isna(
            value
        )

    except Exception:
        return False

    try:
        return bool(
            result
        )

    except Exception:
        return False

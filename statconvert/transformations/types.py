from __future__ import annotations

import pandas as pd

from statconvert.dataset import Dataset
from statconvert.transformations.base import Transformation
from statconvert.transformations.exceptions import TransformationError


class ConvertTypesTransformation(Transformation):
    """
    Convert one or more columns to target data types.
    """

    name = "convert-types"
    description = "Convert dataset columns to requested data types."


    def __init__(
        self,
        type_map: dict[str, str],
        errors: str = "raise",
        datetime_format: str | None = None,
        true_values: list[str] | None = None,
        false_values: list[str] | None = None,
    ) -> None:
        if not type_map:
            raise TransformationError(
                "At least one type conversion must be provided."
            )

        if errors not in {
            "raise",
            "coerce",
            "ignore",
        }:
            raise TransformationError(
                f"Unsupported errors mode: {errors}"
            )

        self.type_map = {
            column: _normalize_target_type(
                target_type
            )
            for column, target_type in type_map.items()
        }
        self.errors = errors
        self.datetime_format = datetime_format
        self.true_values = true_values
        self.false_values = false_values


    def apply(
        self,
        dataset: Dataset
    ) -> Dataset:
        """
        Return a Dataset with requested column types converted.
        """

        _validate_columns_exist(
            dataset,
            list(
                self.type_map
            ),
        )

        result = dataset.copy()

        for column, target_type in self.type_map.items():
            original_series = result.dataframe[column]

            try:
                converted = _convert_series(
                    original_series,
                    target_type=target_type,
                    errors=self.errors,
                    datetime_format=self.datetime_format,
                    true_values=self.true_values,
                    false_values=self.false_values,
                )

            except Exception as exc:
                if self.errors == "ignore":
                    continue

                raise TransformationError(
                    f"Failed converting column '{column}' to "
                    f"'{target_type}': {exc}"
                ) from exc

            result.dataframe[column] = converted
            _update_variable_metadata(
                result,
                column=column,
                target_type=target_type,
            )

        result.sync_metadata()

        return result


def _normalize_target_type(
    target_type: str
) -> str:
    """
    Normalize type aliases to StatConvert target type names.
    """

    aliases = {
        "str": "string",
        "string": "string",
        "int": "integer",
        "integer": "integer",
        "float": "float",
        "double": "float",
        "numeric": "float",
        "bool": "boolean",
        "boolean": "boolean",
        "datetime": "datetime",
        "date": "date",
        "category": "category",
    }
    normalized = aliases.get(
        str(
            target_type
        ).lower()
    )

    if not normalized:
        raise TransformationError(
            f"Unsupported target type: {target_type}"
        )

    return normalized


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
            + " (operation: --type)"
        )


def _convert_series(
    series: pd.Series,
    target_type: str,
    errors: str,
    datetime_format: str | None = None,
    true_values: list[str] | None = None,
    false_values: list[str] | None = None,
) -> pd.Series:
    """
    Convert a pandas Series to a normalized target type.
    """

    if target_type == "string":
        return series.astype(
            "string"
        )

    if target_type == "integer":
        return _convert_integer_series(
            series,
            errors=errors,
        )

    if target_type == "float":
        return pd.to_numeric(
            series,
            errors=_pandas_errors(
                errors
            ),
        )

    if target_type == "boolean":
        return _convert_boolean_series(
            series,
            errors=errors,
            true_values=true_values,
            false_values=false_values,
        )

    if target_type == "datetime":
        return pd.to_datetime(
            series,
            errors=_pandas_errors(
                errors
            ),
            format=datetime_format,
        )

    if target_type == "date":
        # Store dates as pandas datetime64 values normalized to midnight.
        # This keeps the column vectorized while representing date-only values.
        return pd.to_datetime(
            series,
            errors=_pandas_errors(
                errors
            ),
            format=datetime_format,
        ).dt.normalize()

    if target_type == "category":
        return series.astype(
            "category"
        )

    raise TransformationError(
        f"Unsupported target type: {target_type}"
    )


def _convert_integer_series(
    series: pd.Series,
    errors: str,
) -> pd.Series:
    """
    Convert a Series to pandas nullable integer dtype.
    """

    numeric = pd.to_numeric(
        series,
        errors=_pandas_errors(
            errors
        ),
    )
    non_missing = numeric.dropna()
    whole_number_mask = (
        non_missing % 1 == 0
    )

    if not whole_number_mask.all():
        if errors == "coerce":
            numeric = numeric.mask(
                numeric.notna() & (numeric % 1 != 0),
                pd.NA,
            )

        else:
            raise TransformationError(
                "Non-integer values cannot be converted to integer."
            )

    return numeric.astype(
        "Int64"
    )


def _convert_boolean_series(
    series: pd.Series,
    errors: str,
    true_values: list[str] | None = None,
    false_values: list[str] | None = None,
) -> pd.Series:
    """
    Convert common boolean representations to nullable boolean dtype.
    """

    true_tokens = _normalized_boolean_tokens(
        [
            "true",
            "yes",
            "y",
            "1",
        ],
        true_values,
    )
    false_tokens = _normalized_boolean_tokens(
        [
            "false",
            "no",
            "n",
            "0",
        ],
        false_values,
    )
    converted = []
    invalid_values = []

    for value in series:
        if pd.isna(
            value
        ):
            converted.append(
                pd.NA
            )
            continue

        if isinstance(
            value,
            bool
        ):
            converted.append(
                value
            )
            continue

        token = str(
            value
        ).strip().lower()

        if token in true_tokens:
            converted.append(
                True
            )

        elif token in false_tokens:
            converted.append(
                False
            )

        else:
            invalid_values.append(
                value
            )
            converted.append(
                pd.NA
            )

    if invalid_values and errors == "raise":
        raise TransformationError(
            "Invalid boolean values: "
            + ", ".join(
                str(value)
                for value in invalid_values
            )
        )

    if invalid_values and errors == "ignore":
        raise TransformationError(
            "Invalid boolean values: "
            + ", ".join(
                str(value)
                for value in invalid_values
            )
        )

    return pd.Series(
        converted,
        index=series.index,
        name=series.name,
        dtype="boolean",
    )


def _normalized_boolean_tokens(
    defaults: list[str],
    custom_values: list[str] | None,
) -> set[str]:
    """
    Return normalized boolean tokens.
    """

    values = defaults + list(
        custom_values or []
    )

    return {
        str(value).strip().lower()
        for value in values
    }


def _pandas_errors(
    errors: str
) -> str:
    """
    Return the equivalent pandas errors mode.
    """

    if errors == "coerce":
        return "coerce"

    return "raise"


def _update_variable_metadata(
    dataset: Dataset,
    column: str,
    target_type: str,
) -> None:
    """
    Update normalized metadata after a type conversion.
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

    if target_type == "datetime" and not variable.display_format:
        variable.display_format = "datetime"

    if target_type == "date" and not variable.display_format:
        variable.display_format = "date"

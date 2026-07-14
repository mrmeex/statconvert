from __future__ import annotations

from typing import Any

from statconvert.transformations import (
    ConvertTypesTransformation,
    DropColumnsTransformation,
    FilterCondition,
    FilterRowsTransformation,
    RecodeValuesTransformation,
    RenameColumnsTransformation,
    SelectColumnsTransformation,
    TransformationPipeline,
)
from statconvert.transformations.exceptions import TransformationError


def parse_key_value_items(
    items: list[str],
    option_name: str,
) -> dict[str, str]:
    """
    Parse repeated KEY=VALUE CLI options.
    """

    parsed = {}

    for item in items:
        if "=" not in item:
            raise TransformationError(
                f"Invalid {option_name} value '{item}'. Expected KEY=VALUE."
            )

        key, value = item.split(
            "=",
            1,
        )
        key = key.strip()
        value = value.strip()

        if not key:
            raise TransformationError(
                f"Invalid {option_name} value '{item}'. Key cannot be empty."
            )

        if not value:
            raise TransformationError(
                f"Invalid {option_name} value '{item}'. Value cannot be empty."
            )

        if key in parsed:
            raise TransformationError(
                f"Duplicate {option_name} key: {key}"
            )

        parsed[key] = value

    return parsed


def parse_filter_items(
    items: list[str]
) -> list[FilterCondition]:
    """
    Parse repeated COLUMN,OPERATOR,VALUE filter options.
    """

    conditions = []

    for item in items:
        parts = [
            part.strip()
            for part in item.split(
                ","
            )
        ]

        if len(
            parts
        ) < 2 or len(
            parts
        ) > 3:
            raise TransformationError(
                f"Invalid filter '{item}'. Expected COLUMN,OPERATOR,VALUE."
            )

        column = parts[0]
        operator = parts[1]

        if not column or not operator:
            raise TransformationError(
                f"Invalid filter '{item}'. Column and operator are required."
            )

        if len(
            parts
        ) == 2:
            if operator not in {
                "is_missing",
                "not_missing",
            }:
                raise TransformationError(
                    f"Invalid filter '{item}'. Value is required."
                )

            value = None

        else:
            value = _parse_filter_value(
                parts[2],
                operator,
            )

        conditions.append(
            FilterCondition(
                column=column,
                operator=operator,
                value=value,
            )
        )

    return conditions


def parse_recode_items(
    items: list[str]
) -> dict[str, dict[Any, Any]]:
    """
    Parse repeated COLUMN:OLD=NEW,OLD=NEW recode options.
    """

    parsed = {}

    for item in items:
        if ":" not in item:
            raise TransformationError(
                f"Invalid recode '{item}'. Expected COLUMN:OLD=NEW,OLD=NEW."
            )

        column, mappings_text = item.split(
            ":",
            1,
        )
        column = column.strip()

        if not column:
            raise TransformationError(
                f"Invalid recode '{item}'. Column cannot be empty."
            )

        if column in parsed:
            raise TransformationError(
                f"Duplicate recode column: {column}"
            )

        mappings = {}

        for pair in mappings_text.split(
            ","
        ):
            if "=" not in pair:
                raise TransformationError(
                    f"Invalid recode mapping '{pair}'. Expected OLD=NEW."
                )

            old_value, new_value = pair.split(
                "=",
                1,
            )
            old_value = old_value.strip()
            new_value = new_value.strip()

            if not old_value or not new_value:
                raise TransformationError(
                    f"Invalid recode mapping '{pair}'. OLD and NEW are required."
                )

            if old_value in mappings:
                raise TransformationError(
                    f"Duplicate recode value for column {column}: {old_value}"
                )

            mappings[old_value] = new_value

        if not mappings:
            raise TransformationError(
                f"Recode mapping for column '{column}' cannot be empty."
            )

        parsed[column] = mappings

    return parsed


def build_pipeline_from_cli_options(
    select_columns: list[str] | None = None,
    drop_columns: list[str] | None = None,
    rename_items: list[str] | None = None,
    type_items: list[str] | None = None,
    type_errors: str = "raise",
    datetime_format: str | None = None,
    filter_items: list[str] | None = None,
    filter_mode: str = "and",
    recode_items: list[str] | None = None,
    recode_default: Any = None,
    update_value_labels: bool = True,
    ignore_missing_columns: bool = False,
    reset_index: bool = True,
) -> TransformationPipeline:
    """
    Build the CLI transformation pipeline in the documented order.
    """

    pipeline = TransformationPipeline()

    # Pipeline order is stable by design:
    # schema narrowing, renaming, typing, row filtering, then value recoding.
    if select_columns:
        pipeline.add(
            SelectColumnsTransformation(
                columns=list(
                    select_columns
                ),
                ignore_missing=ignore_missing_columns,
            )
        )

    if drop_columns:
        pipeline.add(
            DropColumnsTransformation(
                columns=list(
                    drop_columns
                ),
                ignore_missing=ignore_missing_columns,
            )
        )

    if rename_items:
        pipeline.add(
            RenameColumnsTransformation(
                rename_map=parse_key_value_items(
                    rename_items,
                    "--rename",
                ),
                ignore_missing=ignore_missing_columns,
            )
        )

    if type_items:
        pipeline.add(
            ConvertTypesTransformation(
                type_map=parse_key_value_items(
                    type_items,
                    "--type",
                ),
                errors=type_errors,
                datetime_format=datetime_format,
            )
        )

    if filter_items:
        pipeline.add(
            FilterRowsTransformation(
                conditions=parse_filter_items(
                    filter_items
                ),
                mode=filter_mode,
                reset_index=reset_index,
            )
        )

    if recode_items:
        pipeline.add(
            RecodeValuesTransformation(
                recode_map=parse_recode_items(
                    recode_items
                ),
                default=recode_default,
                use_default=recode_default is not None,
                update_value_labels=update_value_labels,
            )
        )

    return pipeline


def _parse_filter_value(
    value: str,
    operator: str,
) -> Any:
    """
    Parse simple filter values.
    """

    if not value:
        raise TransformationError(
            "Filter value cannot be empty."
        )

    if operator in {
        "in",
        "not_in",
    }:
        return [
            _parse_scalar(
                item.strip()
            )
            for item in value.split(
                "|"
            )
            if item.strip()
        ]

    return _parse_scalar(
        value
    )


def _parse_scalar(
    value: str
) -> Any:
    """
    Parse a small set of scalar CLI values.
    """

    lowered = value.lower()

    if lowered == "true":
        return True

    if lowered == "false":
        return False

    try:
        return int(
            value
        )

    except ValueError:
        pass

    try:
        return float(
            value
        )

    except ValueError:
        return value

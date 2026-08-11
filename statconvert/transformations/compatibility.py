from __future__ import annotations

from typing import Any

from statconvert.transformations.cli_parsing import (
    parse_filter_items,
    parse_key_value_items,
    parse_recode_items,
    parse_sort_items,
)
from statconvert.transformations.recipes import (
    TransformRecipe,
    TransformStep,
    TransformStepType,
)


def recipe_from_transform_options(
    *,
    input_file: str,
    output_file: str,
    select_columns: list[str] | None = None,
    drop_columns: list[str] | None = None,
    rename_items: list[str] | None = None,
    type_items: list[str] | None = None,
    type_errors: str = "raise",
    datetime_format: str | None = None,
    derive_items: list[str] | None = None,
    filter_items: list[str] | None = None,
    filter_expression_items: list[str] | None = None,
    filter_mode: str = "and",
    recode_items: list[str] | None = None,
    recode_default: Any = None,
    update_value_labels: bool = True,
    ignore_missing_columns: bool = False,
    reset_index: bool = True,
    sort_items: list[str] | None = None,
    sort_nulls: str = "last",
    distinct_columns: list[str] | None = None,
    distinct_keep: str = "first",
    row_number_column: str | None = None,
    row_number_start: int = 1,
    row_number_step: int = 1,
    overwrite: bool = False,
) -> TransformRecipe:
    """Translate existing transform options into their fixed-order recipe form."""

    steps: list[TransformStep] = []
    if select_columns:
        steps.append(
            TransformStep(
                TransformStepType.SELECT,
                {
                    "columns": list(select_columns),
                    "ignore_missing": ignore_missing_columns,
                },
            )
        )
    if drop_columns:
        steps.append(
            TransformStep(
                TransformStepType.DROP,
                {
                    "columns": list(drop_columns),
                    "ignore_missing": ignore_missing_columns,
                },
            )
        )
    if rename_items:
        steps.append(
            TransformStep(
                TransformStepType.RENAME,
                {
                    "map": parse_key_value_items(rename_items, "--rename"),
                    "ignore_missing": ignore_missing_columns,
                },
            )
        )
    if type_items:
        for column, data_type in parse_key_value_items(
            type_items,
            "--type",
        ).items():
            parameters: dict[str, Any] = {
                "column": column,
                "data_type": data_type,
                "errors": type_errors,
            }
            if datetime_format is not None:
                parameters["datetime_format"] = datetime_format
            steps.append(
                TransformStep(
                    TransformStepType.CONVERT_TYPE,
                    parameters,
                )
            )
    if derive_items:
        for column, expression in parse_key_value_items(
            derive_items,
            "--derive",
        ).items():
            steps.append(
                TransformStep(
                    TransformStepType.DERIVE,
                    {
                        "column": column,
                        "expression": expression,
                    },
                )
            )
    if filter_items:
        conditions = [
            {
                "column": condition.column,
                "operator": condition.operator,
                "value": condition.value,
            }
            for condition in parse_filter_items(filter_items)
        ]
        steps.append(
            TransformStep(
                TransformStepType.FILTER,
                {
                    "conditions": conditions,
                    "mode": filter_mode,
                    "reset_index": reset_index,
                },
            )
        )
    if filter_expression_items:
        for expression in filter_expression_items:
            steps.append(
                TransformStep(
                    TransformStepType.FILTER,
                    {
                        "expression": expression,
                        "reset_index": reset_index,
                    },
                )
            )
    if recode_items:
        for column, mapping in parse_recode_items(recode_items).items():
            parameters = {
                "column": column,
                "map": mapping,
                "update_value_labels": update_value_labels,
            }
            if recode_default is not None:
                parameters["default"] = recode_default
            steps.append(
                TransformStep(
                    TransformStepType.RECODE,
                    parameters,
                )
            )

    if sort_items:
        steps.append(
            TransformStep(
                TransformStepType.SORT,
                {
                    "keys": [
                        {
                            "column": key.column,
                            "order": key.order,
                            "nulls": key.nulls,
                        }
                        for key in parse_sort_items(sort_items, sort_nulls)
                    ]
                },
            )
        )
    if distinct_columns:
        steps.append(
            TransformStep(
                TransformStepType.DISTINCT,
                {
                    "columns": list(distinct_columns),
                    "keep": distinct_keep,
                },
            )
        )
    if row_number_column is not None:
        steps.append(
            TransformStep(
                TransformStepType.ROW_NUMBER,
                {
                    "column": row_number_column,
                    "start": row_number_start,
                    "step": row_number_step,
                },
            )
        )

    return TransformRecipe(
        input_file=input_file,
        output_file=output_file,
        steps=tuple(steps),
        overwrite=overwrite,
    )

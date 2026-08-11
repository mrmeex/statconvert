from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from statconvert.transformations.columns import (
    DropColumnsTransformation,
    RenameColumnsTransformation,
    SelectColumnsTransformation,
)
from statconvert.transformations.exceptions import TransformationError
from statconvert.transformations.expression_steps import (
    DeriveColumnTransformation,
    ExpressionFilterTransformation,
)
from statconvert.transformations.filtering import (
    FilterCondition,
    FilterRowsTransformation,
)
from statconvert.transformations.pipeline import TransformationPipeline
from statconvert.transformations.planning import plan_transform_recipe
from statconvert.transformations.recode import RecodeValuesTransformation
from statconvert.transformations.row_operations import (
    DistinctRowsTransformation,
    RowNumberTransformation,
    SortKey,
    SortRowsTransformation,
)
from statconvert.transformations.recipes import (
    TransformRecipe,
    TransformStep,
    TransformStepType,
)
from statconvert.transformations.types import ConvertTypesTransformation


def recipe_from_ordered_steps(
    *,
    input_file: str,
    output_file: str,
    steps: Sequence[Mapping[str, Any]],
    overwrite: bool = False,
) -> TransformRecipe:
    """Build a validated ordered recipe from canonical config step tables."""

    parsed_steps: list[TransformStep] = []
    for index, raw_step in enumerate(steps):
        if not isinstance(raw_step, Mapping):
            raise TransformationError(
                f"Ordered transform step {index} must be a table."
            )
        step_data = dict(raw_step)
        step_type = step_data.pop("type", None)
        step_id = step_data.pop("id", None)
        if not isinstance(step_type, str):
            raise TransformationError(
                f"Ordered transform step {index} is missing string field 'type'."
            )
        try:
            normalized_type = TransformStepType(step_type)
        except ValueError as exc:
            raise TransformationError(
                f"Ordered transform step {index} has unsupported type "
                f"'{step_type}'."
            ) from exc
        try:
            parsed_steps.append(
                TransformStep(
                    step_type=normalized_type,
                    parameters=step_data,
                    step_id=step_id,
                )
            )
        except (TypeError, ValueError) as exc:
            raise TransformationError(
                f"Ordered transform step {index} ({step_type}) is invalid: {exc}"
            ) from exc

    return TransformRecipe(
        input_file=input_file,
        output_file=output_file,
        steps=tuple(parsed_steps),
        overwrite=overwrite,
    )


def compile_transform_recipe(
    recipe: TransformRecipe,
    available_columns: Sequence[str],
) -> TransformationPipeline:
    """Compile one validated recipe to the existing transformation classes."""

    plan = plan_transform_recipe(recipe, available_columns)
    if not plan.valid:
        issue = plan.errors[0]
        detail = (
            f"Ordered transform step {issue.step_index} "
            f"({issue.step_type.value}) field '{issue.field}' "
            f"[{issue.code}]: {issue.message}"
        )
        if issue.source_span is not None:
            detail += (
                " (expression span "
                f"{issue.source_span.start}:{issue.source_span.end})"
            )
        raise TransformationError(detail, suggestion=issue.suggestion)

    pipeline = TransformationPipeline()
    for step in recipe.steps:
        pipeline.add(_compile_step(step))
    return pipeline


def _compile_step(step: TransformStep):
    parameters = step.parameters
    if step.step_type == TransformStepType.SELECT:
        return SelectColumnsTransformation(
            columns=list(parameters["columns"]),
            ignore_missing=bool(parameters.get("ignore_missing", False)),
        )
    if step.step_type == TransformStepType.DROP:
        return DropColumnsTransformation(
            columns=list(parameters["columns"]),
            ignore_missing=bool(parameters.get("ignore_missing", False)),
        )
    if step.step_type == TransformStepType.RENAME:
        raw_mapping = parameters.get("map")
        mapping = (
            dict(raw_mapping)
            if isinstance(raw_mapping, Mapping)
            else {str(parameters["from"]): str(parameters["to"])}
        )
        return RenameColumnsTransformation(
            rename_map=mapping,
            ignore_missing=bool(parameters.get("ignore_missing", False)),
        )
    if step.step_type == TransformStepType.CONVERT_TYPE:
        return ConvertTypesTransformation(
            type_map={str(parameters["column"]): str(parameters["data_type"])},
            errors=str(parameters.get("errors", "raise")),
            datetime_format=parameters.get("datetime_format"),
        )
    if step.step_type == TransformStepType.DERIVE:
        return DeriveColumnTransformation(
            column=str(parameters["column"]),
            expression=str(parameters["expression"]),
        )
    if step.step_type == TransformStepType.FILTER:
        if "expression" in parameters:
            return ExpressionFilterTransformation(
                expression=str(parameters["expression"]),
                reset_index=bool(parameters.get("reset_index", True)),
            )
        conditions = [
            FilterCondition(
                column=str(condition["column"]),
                operator=str(condition["operator"]),
                value=condition.get("value"),
            )
            for condition in parameters["conditions"]
        ]
        return FilterRowsTransformation(
            conditions=conditions,
            mode=str(parameters.get("mode", "and")),
            reset_index=bool(parameters.get("reset_index", True)),
        )
    if step.step_type == TransformStepType.RECODE:
        return RecodeValuesTransformation(
            recode_map={
                str(parameters["column"]): dict(parameters["map"]),
            },
            default=parameters.get("default"),
            use_default="default" in parameters,
            update_value_labels=bool(
                parameters.get("update_value_labels", True)
            ),
        )
    if step.step_type == TransformStepType.SORT:
        return SortRowsTransformation(
            [
                SortKey(
                    column=str(key["column"]),
                    order=str(key["order"]),
                    nulls=str(key["nulls"]),
                )
                for key in parameters["keys"]
            ]
        )
    if step.step_type == TransformStepType.DISTINCT:
        return DistinctRowsTransformation(
            columns=list(parameters["columns"]),
            keep=str(parameters["keep"]),
        )
    if step.step_type == TransformStepType.ROW_NUMBER:
        return RowNumberTransformation(
            column=str(parameters["column"]),
            start=int(parameters.get("start", 1)),
            step=int(parameters.get("step", 1)),
        )
    raise TransformationError(
        f"Unsupported ordered transform step '{step.step_type.value}'."
    )

from __future__ import annotations

from statconvert.dataset import ColumnMetadata, Dataset
from statconvert.metadata import VariableMetadata
from statconvert.transformations.base import Transformation
from statconvert.transformations.exceptions import TransformationError
from statconvert.transformations.expressions import (
    ParsedExpression,
    boolean_mask,
    evaluate_expression,
    parse_expression,
)
from statconvert.transformations.planning import (
    TransformPlanIssue,
    plan_transform_recipe,
)
from statconvert.transformations.recipes import (
    TransformRecipe,
    TransformStep,
    TransformStepType,
)


class DeriveColumnTransformation(Transformation):
    """Append one safely evaluated expression-derived column."""

    name = "derive-column"
    description = "Append one column derived from a closed transform expression."

    def __init__(self, column: str, expression: str) -> None:
        self.column = column
        self.expression = expression
        _validate_expression_syntax(expression)

    def apply(self, dataset: Dataset) -> Dataset:
        analysis = _validated_expression_step(
            dataset,
            TransformStep(
                TransformStepType.DERIVE,
                {
                    "column": self.column,
                    "expression": self.expression,
                },
            ),
        )
        result = dataset.copy()
        evaluated = evaluate_expression(analysis, result.dataframe)
        result.dataframe[self.column] = evaluated
        _add_derived_metadata(result, self.column)
        return result


class ExpressionFilterTransformation(Transformation):
    """Filter rows using one safely evaluated boolean expression."""

    name = "filter-expression"
    description = "Filter rows using a closed transform expression."

    def __init__(self, expression: str, reset_index: bool = True) -> None:
        self.expression = expression
        self.reset_index = reset_index
        _validate_expression_syntax(expression)

    def apply(self, dataset: Dataset) -> Dataset:
        analysis = _validated_expression_step(
            dataset,
            TransformStep(
                TransformStepType.FILTER,
                {"expression": self.expression, "reset_index": self.reset_index},
            ),
        )
        evaluated = evaluate_expression(analysis, dataset.dataframe)
        mask = boolean_mask(
            evaluated,
            dataset.dataframe,
            expression=self.expression,
            source_span=analysis.span,
        )
        result = dataset.copy()
        result.dataframe = result.dataframe.loc[mask].copy(deep=True)
        if self.reset_index:
            result.dataframe = result.dataframe.reset_index(drop=True)
        return result


def _validated_expression_step(
    dataset: Dataset,
    step: TransformStep,
) -> ParsedExpression:
    recipe = TransformRecipe(
        input_file="<dataset>",
        output_file="<dataset>",
        steps=(step,),
    )
    plan = plan_transform_recipe(recipe, [str(column) for column in dataset.columns])
    planned_step = plan.steps[0]
    if planned_step.errors:
        _raise_plan_issue(planned_step.errors[0])
    analysis = planned_step.expression_metadata
    if analysis is None:
        raise TransformationError(
            "Expression planning did not produce expression metadata."
        )
    return analysis


def _validate_expression_syntax(expression: str) -> None:
    analysis = parse_expression(expression)
    if analysis.valid:
        return
    error = analysis.errors[0]
    message = f"{error.message} (expression span {error.start}:{error.end})"
    raise TransformationError(message, suggestion=error.suggestion)


def _raise_plan_issue(issue: TransformPlanIssue) -> None:
    message = issue.message
    if issue.source_span is not None:
        message += (
            f" (expression span {issue.source_span.start}:{issue.source_span.end})"
        )
    raise TransformationError(message, suggestion=issue.suggestion)


def _add_derived_metadata(dataset: Dataset, column: str) -> None:
    series = dataset.dataframe[column]
    storage_type = str(series.dtype)
    logical_type = Dataset._infer_logical_type_from_dtype(series.dtype)
    dataset.get_normalized_metadata().add_variable(
        VariableMetadata(
            name=column,
            storage_type=storage_type,
        )
    )
    dataset.column_metadata[column] = ColumnMetadata(
        name=column,
        physical_type=storage_type,
        logical_type=logical_type,
        source_format=dataset.source_format,
    )
    columns_provenance = dataset.metadata_provenance.setdefault("columns", {})
    if isinstance(columns_provenance, dict):
        columns_provenance[column] = "derived"
    dataset.sync_metadata()

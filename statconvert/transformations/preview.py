from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from statconvert.dataset import Dataset
from statconvert.serialization import make_json_safe
from statconvert.transformations.planning import plan_transform_recipe
from statconvert.transformations.recipe_execution import compile_transform_recipe
from statconvert.transformations.recipes import TransformRecipe


@dataclass(frozen=True)
class TransformPreviewStep:
    """One UI-ready ordered preview step result."""

    step_index: int
    step_type: str
    status: str
    input_columns: tuple[str, ...]
    output_columns: tuple[str, ...]
    referenced_columns: tuple[str, ...]
    created_columns: tuple[str, ...]
    removed_columns: tuple[str, ...]
    renamed_columns: tuple[tuple[str, str], ...]
    rows_before: int | None
    rows_after: int | None
    expression_metadata: dict[str, Any] | None
    errors: tuple[dict[str, Any], ...] = ()
    warnings: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return make_json_safe(
            {
                "step_index": self.step_index,
                "step_type": self.step_type,
                "status": self.status,
                "input_columns": list(self.input_columns),
                "output_columns": list(self.output_columns),
                "referenced_columns": list(self.referenced_columns),
                "created_columns": list(self.created_columns),
                "removed_columns": list(self.removed_columns),
                "renamed_columns": dict(self.renamed_columns),
                "rows_before": self.rows_before,
                "rows_after": self.rows_after,
                "expression_metadata": self.expression_metadata,
                "errors": list(self.errors),
                "warnings": list(self.warnings),
            }
        )


@dataclass(frozen=True)
class TransformPreview:
    """Bounded, deterministic, JSON-safe ordered recipe preview."""

    valid: bool
    rows_before: int
    sampled_rows: int
    preview_rows: int
    limit: int
    columns_before: tuple[str, ...]
    columns_after: tuple[str, ...]
    steps: tuple[TransformPreviewStep, ...]
    sample_output_rows: tuple[dict[str, Any], ...]
    errors: tuple[dict[str, Any], ...] = ()
    warnings: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return make_json_safe(
            {
                "valid": self.valid,
                "rows_before": self.rows_before,
                "sampled_rows": self.sampled_rows,
                "preview_rows": self.preview_rows,
                "limit": self.limit,
                "columns_before": list(self.columns_before),
                "columns_after": list(self.columns_after),
                "steps": [step.to_dict() for step in self.steps],
                "sample_output_rows": list(self.sample_output_rows),
                "errors": list(self.errors),
                "warnings": list(self.warnings),
            }
        )


def preview_transform_recipe(
    dataset: Dataset,
    recipe: TransformRecipe,
    *,
    limit: int = 50,
) -> TransformPreview:
    """Apply one recipe to a bounded copy without reading or writing files."""

    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise ValueError("Transform preview limit must be a positive integer.")

    columns_before = tuple(str(column) for column in dataset.columns)
    plan = plan_transform_recipe(recipe, columns_before, mode="preview")
    sampled = dataset.copy()
    sampled.dataframe = sampled.dataframe.head(limit).copy(deep=True)
    sampled_rows = sampled.rows

    if not plan.valid:
        return TransformPreview(
            valid=False,
            rows_before=dataset.rows,
            sampled_rows=sampled_rows,
            preview_rows=sampled_rows,
            limit=limit,
            columns_before=columns_before,
            columns_after=columns_before,
            steps=tuple(
                _planned_preview_step(step)
                for step in plan.steps
            ),
            sample_output_rows=tuple(
                make_json_safe(sampled.dataframe.to_dict(orient="records"))
            ),
            errors=tuple(issue.to_dict() for issue in plan.errors),
            warnings=tuple(issue.to_dict() for issue in plan.warnings),
        )

    pipeline = compile_transform_recipe(recipe, columns_before)
    transformed = sampled
    results: list[TransformPreviewStep] = []
    for planned, transformation in zip(plan.steps, pipeline.transformations):
        rows_before = transformed.rows
        transformed = transformation.apply(transformed)
        output_columns = tuple(str(column) for column in transformed.columns)
        results.append(
            TransformPreviewStep(
                step_index=planned.step_index,
                step_type=planned.step_type.value,
                status="applied",
                input_columns=planned.input_columns,
                output_columns=output_columns,
                referenced_columns=planned.referenced_columns,
                created_columns=tuple(
                    column
                    for column in output_columns
                    if column not in planned.input_columns
                ),
                removed_columns=planned.removed_columns,
                renamed_columns=planned.renamed_columns,
                rows_before=rows_before,
                rows_after=transformed.rows,
                expression_metadata=(
                    planned.expression_metadata.to_dict()
                    if planned.expression_metadata is not None
                    else None
                ),
                warnings=tuple(
                    warning.to_dict() for warning in planned.warnings
                ),
            )
        )

    records = make_json_safe(transformed.dataframe.to_dict(orient="records"))
    return TransformPreview(
        valid=True,
        rows_before=dataset.rows,
        sampled_rows=sampled_rows,
        preview_rows=transformed.rows,
        limit=limit,
        columns_before=columns_before,
        columns_after=tuple(str(column) for column in transformed.columns),
        steps=tuple(results),
        sample_output_rows=tuple(records),
        warnings=tuple(issue.to_dict() for issue in plan.warnings),
    )


def _planned_preview_step(planned) -> TransformPreviewStep:
    return TransformPreviewStep(
        step_index=planned.step_index,
        step_type=planned.step_type.value,
        status=planned.status,
        input_columns=planned.input_columns,
        output_columns=planned.output_columns,
        referenced_columns=planned.referenced_columns,
        created_columns=tuple(
            column
            for column in planned.output_columns
            if column not in planned.input_columns
        ),
        removed_columns=planned.removed_columns,
        renamed_columns=planned.renamed_columns,
        rows_before=None,
        rows_after=None,
        expression_metadata=(
            planned.expression_metadata.to_dict()
            if planned.expression_metadata is not None
            else None
        ),
        errors=tuple(error.to_dict() for error in planned.errors),
        warnings=tuple(warning.to_dict() for warning in planned.warnings),
    )

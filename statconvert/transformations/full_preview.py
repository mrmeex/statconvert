from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from statconvert.dataset import Dataset
from statconvert.serialization import make_json_safe
from statconvert.transformations.planning import plan_transform_recipe
from statconvert.transformations.portable_recipes import PortableTransformRecipe
from statconvert.transformations.recode import (
    RecodeValuesTransformation,
    _is_missing_value,
    _values_match,
)
from statconvert.transformations.recipe_execution import compile_transform_recipe
from statconvert.transformations.recipes import TransformRecipe
from statconvert.transformations.row_operations import (
    DistinctRowsTransformation,
    RowNumberTransformation,
    SortRowsTransformation,
)
from statconvert.transformations.safety import TransformOutputPreflight
from statconvert.transformations.types import ConvertTypesTransformation


@dataclass(frozen=True)
class FullTransformPreview:
    """Exact, bounded-output preview produced by applying a full copied Dataset."""

    payload: dict[str, Any]

    @property
    def valid(self) -> bool:
        return bool(self.payload["valid"])

    def to_dict(self) -> dict[str, Any]:
        return make_json_safe(self.payload)


def preview_full_transform(
    dataset: Dataset,
    recipe: TransformRecipe,
    *,
    input_path: str | Path,
    output_preflight: TransformOutputPreflight,
    object_selector: str | None = None,
    portable_recipe: PortableTransformRecipe | None = None,
    sample_limit: int = 20,
) -> FullTransformPreview:
    """Apply every step once to a full copy while collecting exact impact counters."""

    if isinstance(sample_limit, bool) or not isinstance(sample_limit, int) or sample_limit <= 0:
        raise ValueError("Full transform preview sample limit must be positive.")

    source = dataset.copy()
    before_records = make_json_safe(
        source.dataframe.head(sample_limit).to_dict(orient="records")
    )
    columns_before = tuple(str(column) for column in source.columns)
    plan = plan_transform_recipe(recipe, columns_before, mode="full")
    recipe_payload = (
        portable_recipe.to_dict()
        if portable_recipe is not None
        else {
            "version": 1,
            "name": None,
            "description": None,
            "steps": [step.to_dict() for step in recipe.steps],
        }
    )
    base_payload: dict[str, Any] = {
        "valid": plan.valid,
        "mode": "full_preview",
        "input": {
            "path": str(Path(input_path).resolve(strict=False)),
            "format": Path(input_path).suffix.lower().lstrip("."),
            "object": object_selector,
            "rows": source.rows,
            "columns": list(columns_before),
        },
        "output": output_preflight.to_dict(),
        "recipe": {
            "name": recipe_payload.get("name"),
            "description": recipe_payload.get("description"),
            "schema_version": recipe_payload.get("version", 1),
            "normalized_steps": recipe_payload["steps"],
        },
        "issues": [issue.to_dict() for issue in (*plan.errors, *plan.warnings)],
        "caveats": [
            "Preview applies the complete recipe to a copied in-memory Dataset.",
            "No output data file or metadata sidecar is written.",
        ],
    }
    if not plan.valid:
        base_payload.update(
            {
                "summary": _empty_summary(source),
                "steps": [step.to_dict() for step in plan.steps],
                "sample": {"before": before_records, "after": []},
                "truncation": {
                    "sample_limit": sample_limit,
                    "before_truncated": source.rows > sample_limit,
                    "after_truncated": False,
                },
            }
        )
        return FullTransformPreview(make_json_safe(base_payload))

    pipeline = compile_transform_recipe(recipe, columns_before)
    transformed = source
    step_results: list[dict[str, Any]] = []
    for planned, transformation in zip(plan.steps, pipeline.transformations):
        step_input = transformed
        rows_before = step_input.rows
        step_columns_before = tuple(str(column) for column in step_input.columns)
        metadata_before = _metadata_variables(step_input)
        transformed = transformation.apply(step_input)
        rows_after = transformed.rows
        step_columns_after = tuple(str(column) for column in transformed.columns)
        metadata_after = _metadata_variables(transformed)
        conversion = _conversion_counts(transformation, step_input, transformed)
        recode = _recode_counts(transformation, step_input)
        renamed_columns = dict(planned.renamed_columns)
        operation_impact = _operation_impact(
            transformation,
            step_input,
            transformed,
        )
        step_results.append(
            {
                "step_index": planned.step_index,
                "type": planned.step_type.value,
                "valid": True,
                "rows_before": rows_before,
                "rows_after": rows_after,
                "rows_removed": max(0, rows_before - rows_after),
                "columns_before": list(step_columns_before),
                "columns_after": list(step_columns_after),
                "columns_added": [
                    column for column in step_columns_after
                    if column not in step_columns_before
                    and column not in renamed_columns.values()
                ],
                "columns_removed": [
                    column for column in step_columns_before
                    if column not in step_columns_after
                    and column not in renamed_columns
                ],
                "columns_renamed": renamed_columns,
                **conversion,
                **recode,
                **operation_impact,
                "metadata_impact": _metadata_impact(
                    metadata_before,
                    metadata_after,
                    renamed=renamed_columns,
                ),
                "issues": [
                    issue.to_dict() for issue in (*planned.errors, *planned.warnings)
                ],
            }
        )

    final_columns = tuple(str(column) for column in transformed.columns)
    final_metadata = _metadata_variables(transformed)
    initial_metadata = _metadata_variables(source)
    summary_renamed = {
        source_name: target_name
        for step in plan.steps
        for source_name, target_name in step.renamed_columns
    }
    after_records = make_json_safe(
        transformed.dataframe.head(sample_limit).to_dict(orient="records")
    )
    base_payload.update(
        {
            "summary": {
                "rows_before": source.rows,
                "rows_after": transformed.rows,
                "rows_removed": max(0, source.rows - transformed.rows),
                "columns_before": list(columns_before),
                "columns_after": list(final_columns),
                "columns_added": [
                    column for column in final_columns
                    if column not in columns_before
                    and column not in summary_renamed.values()
                ],
                "columns_removed": [
                    column for column in columns_before
                    if column not in final_columns
                    and column not in summary_renamed
                ],
                "columns_renamed": summary_renamed,
                "metadata_changes": _metadata_impact(
                    initial_metadata,
                    final_metadata,
                    renamed=summary_renamed,
                ),
            },
            "steps": step_results,
            "sample": {"before": before_records, "after": after_records},
            "truncation": {
                "sample_limit": sample_limit,
                "before_truncated": source.rows > sample_limit,
                "after_truncated": transformed.rows > sample_limit,
            },
        }
    )
    return FullTransformPreview(make_json_safe(base_payload))


def _empty_summary(dataset: Dataset) -> dict[str, Any]:
    columns = [str(column) for column in dataset.columns]
    return {
        "rows_before": dataset.rows,
        "rows_after": dataset.rows,
        "rows_removed": 0,
        "columns_before": columns,
        "columns_after": columns,
        "columns_added": [],
        "columns_removed": [],
        "columns_renamed": {},
        "metadata_changes": {
            "added": [], "removed": [], "renamed": {}, "changed": []
        },
    }


def _metadata_variables(dataset: Dataset) -> dict[str, dict[str, Any]]:
    return {
        name: make_json_safe(asdict(variable))
        for name, variable in dataset.get_normalized_metadata().variables.items()
    }


def _metadata_impact(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
    *,
    renamed: dict[str, str],
) -> dict[str, Any]:
    added = [name for name in after if name not in before and name not in renamed.values()]
    removed = [name for name in before if name not in after and name not in renamed]
    changed = [
        name for name in before.keys() & after.keys()
        if before[name] != after[name]
    ]
    return {
        "added": added,
        "removed": removed,
        "renamed": renamed,
        "changed": sorted(changed),
    }


def _conversion_counts(
    transformation: Any,
    before: Dataset,
    after: Dataset,
) -> dict[str, int]:
    result = {"coercion_count": 0, "skipped_conversion_count": 0}
    if not isinstance(transformation, ConvertTypesTransformation):
        return result
    for column in transformation.type_map:
        original = before.dataframe[column]
        converted = after.dataframe[column]
        result["coercion_count"] += int((original.notna() & converted.isna()).sum())
        if transformation.errors == "ignore" and original.equals(converted):
            result["skipped_conversion_count"] += int(original.notna().sum())
    return result


def _recode_counts(
    transformation: Any,
    before: Dataset,
) -> dict[str, int]:
    result = {
        "recode_mapped_count": 0,
        "recode_unmapped_count": 0,
        "recode_defaulted_count": 0,
    }
    if not isinstance(transformation, RecodeValuesTransformation):
        return result
    for column, mapping in transformation.recode_map.items():
        for value in before.dataframe[column]:
            if _is_missing_value(value):
                continue
            if any(_values_match(value, source) for source in mapping):
                result["recode_mapped_count"] += 1
            else:
                result["recode_unmapped_count"] += 1
                if transformation.use_default:
                    result["recode_defaulted_count"] += 1
    return result


def _operation_impact(
    transformation: Any,
    before: Dataset,
    after: Dataset,
) -> dict[str, Any]:
    result: dict[str, Any] = {"row_order_changed": False}
    if isinstance(transformation, SortRowsTransformation):
        result.update(
            {
                "row_order_changed": not before.dataframe.reset_index(
                    drop=True
                ).equals(after.dataframe.reset_index(drop=True)),
                "sort_keys": [
                    {
                        "column": key.column,
                        "order": key.order,
                        "nulls": key.nulls,
                    }
                    for key in transformation.keys
                ],
            }
        )
    elif isinstance(transformation, DistinctRowsTransformation):
        result.update(
            {
                "distinct_columns": list(transformation.columns),
                "distinct_keep": transformation.keep,
            }
        )
    elif isinstance(transformation, RowNumberTransformation):
        result.update(
            {
                "row_number_column": transformation.column,
                "row_number_start": transformation.start,
                "row_number_step": transformation.step,
            }
        )
    return result

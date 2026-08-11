from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Sequence

from statconvert.error_suggestions import did_you_mean
from statconvert.transformations.exceptions import TransformationError
from statconvert.transformations.expressions import (
    BinaryOpNode,
    ColumnReferenceNode,
    FunctionCallNode,
    GroupNode,
    ParsedExpression,
    SourceSpan,
    UnaryOpNode,
    parse_expression,
)
from statconvert.transformations.filtering import _normalize_operator
from statconvert.transformations.recipes import (
    TransformRecipe,
    TransformStep,
    TransformStepType,
)
from statconvert.transformations.types import _normalize_target_type


class TransformPlanMode(StrEnum):
    """Intended consumer of a non-executing transform recipe plan."""

    FULL = "full"
    PREVIEW = "preview"
    COMPATIBILITY = "compatibility"


@dataclass(frozen=True)
class TransformPlanIssue:
    """One structured recipe planning error or warning."""

    code: str
    message: str
    step_index: int
    step_type: TransformStepType
    field: str
    referenced_column: str | None = None
    source_span: SourceSpan | None = None
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "step_index": self.step_index,
            "step_type": self.step_type.value,
            "field": self.field,
        }
        if self.referenced_column is not None:
            result["referenced_column"] = self.referenced_column
        if self.source_span is not None:
            result["source_span"] = self.source_span.to_dict()
        if self.suggestion is not None:
            result["suggestion"] = self.suggestion
        return result


@dataclass(frozen=True)
class PlannedTransformStep:
    """Preview-ready metadata for one ordered recipe step."""

    step_index: int
    step_id: str | None
    step_type: TransformStepType
    status: str
    input_columns: tuple[str, ...]
    output_columns: tuple[str, ...]
    referenced_columns: tuple[str, ...] = ()
    removed_columns: tuple[str, ...] = ()
    renamed_columns: tuple[tuple[str, str], ...] = ()
    intended_types: tuple[tuple[str, str], ...] = ()
    expression: str | None = None
    expression_metadata: ParsedExpression | None = None
    recode_map_keys: tuple[str, ...] = ()
    recode_map_count: int | None = None
    recode_uses_default: bool | None = None
    recode_default: Any = None
    recode_updates_value_labels: bool | None = None
    recode_affects_missing_values: bool | None = None
    row_local: bool = True
    previewable: bool = True
    errors: tuple[TransformPlanIssue, ...] = ()
    warnings: tuple[TransformPlanIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result = {
            "step_index": self.step_index,
            "step_id": self.step_id,
            "step_type": self.step_type.value,
            "status": self.status,
            "input_columns": list(self.input_columns),
            "output_columns": list(self.output_columns),
            "referenced_columns": list(self.referenced_columns),
            "removed_columns": list(self.removed_columns),
            "renamed_columns": dict(self.renamed_columns),
            "intended_types": dict(self.intended_types),
            "expression": self.expression,
            "expression_metadata": (
                self.expression_metadata.to_dict()
                if self.expression_metadata is not None
                else None
            ),
            "row_local": self.row_local,
            "previewable": self.previewable,
            "errors": [error.to_dict() for error in self.errors],
            "warnings": [warning.to_dict() for warning in self.warnings],
        }
        if self.step_type == TransformStepType.RECODE:
            result.update(
                {
                    "recode_map_keys": list(self.recode_map_keys),
                    "recode_map_count": self.recode_map_count,
                    "recode_uses_default": self.recode_uses_default,
                    "recode_default": self.recode_default,
                    "recode_updates_value_labels": self.recode_updates_value_labels,
                    "recode_affects_missing_values": (
                        self.recode_affects_missing_values
                    ),
                }
            )
        return result


@dataclass(frozen=True)
class TransformRecipePlan:
    """Deterministic non-executing projection of an ordered transform recipe."""

    mode: TransformPlanMode
    valid: bool
    initial_columns: tuple[str, ...]
    final_columns: tuple[str, ...]
    steps: tuple[PlannedTransformStep, ...]
    errors: tuple[TransformPlanIssue, ...] = ()
    warnings: tuple[TransformPlanIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "valid": self.valid,
            "initial_columns": list(self.initial_columns),
            "final_columns": list(self.final_columns),
            "steps": [step.to_dict() for step in self.steps],
            "errors": [error.to_dict() for error in self.errors],
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


@dataclass
class _StepProjection:
    columns: list[str]
    referenced_columns: tuple[str, ...] = ()
    removed_columns: tuple[str, ...] = ()
    renamed_columns: tuple[tuple[str, str], ...] = ()
    intended_types: tuple[tuple[str, str], ...] = ()
    expression: str | None = None
    expression_metadata: ParsedExpression | None = None
    recode_map_keys: tuple[str, ...] = ()
    recode_map_count: int | None = None
    recode_uses_default: bool | None = None
    recode_default: Any = None
    recode_updates_value_labels: bool | None = None
    recode_affects_missing_values: bool | None = None
    row_local: bool = True
    previewable: bool = True
    errors: tuple[TransformPlanIssue, ...] = ()
    warnings: tuple[TransformPlanIssue, ...] = ()


def plan_transform_recipe(
    recipe: TransformRecipe,
    available_columns: Sequence[str],
    *,
    mode: TransformPlanMode | str = TransformPlanMode.FULL,
) -> TransformRecipePlan:
    """Validate ordered steps and project their column state without execution."""

    try:
        normalized_mode = TransformPlanMode(mode)
    except ValueError as exc:
        supported = ", ".join(item.value for item in TransformPlanMode)
        raise TransformationError(
            f"Unsupported transform planning mode '{mode}'. Use one of: {supported}."
        ) from exc
    initial_columns = tuple(str(column) for column in available_columns)
    current_columns = list(initial_columns)
    planned_steps: list[PlannedTransformStep] = []
    all_errors: list[TransformPlanIssue] = []
    all_warnings: list[TransformPlanIssue] = []

    for step_index, step in enumerate(recipe.steps):
        input_columns = tuple(current_columns)
        projection = _plan_step(step, step_index, current_columns)
        if not projection.errors:
            current_columns = list(projection.columns)
        output_columns = tuple(
            projection.columns if not projection.errors else current_columns
        )
        planned = PlannedTransformStep(
            step_index=step_index,
            step_id=step.step_id,
            step_type=step.step_type,
            status="invalid" if projection.errors else "planned",
            input_columns=input_columns,
            output_columns=output_columns,
            referenced_columns=projection.referenced_columns,
            removed_columns=(
                projection.removed_columns if not projection.errors else ()
            ),
            renamed_columns=(
                projection.renamed_columns if not projection.errors else ()
            ),
            intended_types=projection.intended_types,
            expression=projection.expression,
            expression_metadata=projection.expression_metadata,
            recode_map_keys=projection.recode_map_keys,
            recode_map_count=projection.recode_map_count,
            recode_uses_default=projection.recode_uses_default,
            recode_default=projection.recode_default,
            recode_updates_value_labels=projection.recode_updates_value_labels,
            recode_affects_missing_values=projection.recode_affects_missing_values,
            row_local=projection.row_local,
            previewable=projection.previewable,
            errors=projection.errors,
            warnings=projection.warnings,
        )
        planned_steps.append(planned)
        all_errors.extend(projection.errors)
        all_warnings.extend(projection.warnings)

    return TransformRecipePlan(
        mode=normalized_mode,
        valid=not all_errors,
        initial_columns=initial_columns,
        final_columns=tuple(current_columns),
        steps=tuple(planned_steps),
        errors=tuple(all_errors),
        warnings=tuple(all_warnings),
    )


def _plan_step(
    step: TransformStep,
    step_index: int,
    current_columns: list[str],
) -> _StepProjection:
    planners = {
        TransformStepType.SELECT: _plan_select,
        TransformStepType.DROP: _plan_drop,
        TransformStepType.RENAME: _plan_rename,
        TransformStepType.CONVERT_TYPE: _plan_convert_type,
        TransformStepType.DERIVE: _plan_derive,
        TransformStepType.FILTER: _plan_filter,
        TransformStepType.RECODE: _plan_recode,
        TransformStepType.SORT: _plan_sort,
        TransformStepType.DISTINCT: _plan_distinct,
        TransformStepType.ROW_NUMBER: _plan_row_number,
    }
    return planners[step.step_type](step, step_index, current_columns)


def _plan_select(
    step: TransformStep,
    step_index: int,
    current_columns: list[str],
) -> _StepProjection:
    requested = list(step.parameters["columns"])
    errors = _duplicate_column_issues(
        requested,
        step_index,
        step.step_type,
        "columns",
    )
    found, _, unknown_errors, warnings = _resolve_requested_columns(
        requested,
        current_columns,
        step,
        step_index,
        field="columns",
    )
    errors.extend(unknown_errors)
    if not found:
        errors.append(
            _issue(
                "transform_invalid_step",
                "Select step would leave no columns.",
                step_index,
                step.step_type,
                "columns",
                suggestion="Select at least one available column.",
            )
        )
    return _StepProjection(
        columns=found,
        referenced_columns=tuple(requested),
        removed_columns=tuple(
            column for column in current_columns if column not in found
        ),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def _plan_drop(
    step: TransformStep,
    step_index: int,
    current_columns: list[str],
) -> _StepProjection:
    requested = list(step.parameters["columns"])
    errors = _duplicate_column_issues(
        requested,
        step_index,
        step.step_type,
        "columns",
    )
    found, _, unknown_errors, warnings = _resolve_requested_columns(
        requested,
        current_columns,
        step,
        step_index,
        field="columns",
    )
    errors.extend(unknown_errors)
    remaining = [column for column in current_columns if column not in set(found)]
    if not remaining:
        errors.append(
            _issue(
                "transform_invalid_step",
                "Drop step would remove every column.",
                step_index,
                step.step_type,
                "columns",
                suggestion="Keep at least one column.",
            )
        )
    return _StepProjection(
        columns=remaining,
        referenced_columns=tuple(requested),
        removed_columns=tuple(found),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def _plan_rename(
    step: TransformStep,
    step_index: int,
    current_columns: list[str],
) -> _StepProjection:
    raw_mapping = step.parameters.get("map")
    if raw_mapping is None:
        raw_mapping = {step.parameters["from"]: step.parameters["to"]}
    mapping = list(raw_mapping.items())
    errors: list[TransformPlanIssue] = []
    warnings: list[TransformPlanIssue] = []
    if not mapping:
        errors.append(
            _issue(
                "transform_invalid_step",
                "Rename mapping must not be empty.",
                step_index,
                step.step_type,
                "map",
            )
        )

    sources = [source for source, _ in mapping]
    targets = [target for _, target in mapping]
    for source in sources:
        if not isinstance(source, str) or not source:
            errors.append(
                _issue(
                    "transform_invalid_step",
                    "Rename source must be a non-empty string.",
                    step_index,
                    step.step_type,
                    "map",
                )
            )
    for target in targets:
        if not isinstance(target, str) or not target.strip():
            errors.append(
                _issue(
                    "transform_invalid_step",
                    "Rename target must be a non-empty string.",
                    step_index,
                    step.step_type,
                    "to",
                )
            )

    errors.extend(
        _duplicate_column_issues(
            sources,
            step_index,
            step.step_type,
            "from",
        )
    )
    duplicate_targets = _duplicates(targets)
    for target in duplicate_targets:
        errors.append(
            _issue(
                "transform_duplicate_column",
                f"Rename target column '{target}' is duplicated.",
                step_index,
                step.step_type,
                "to",
                referenced_column=str(target),
            )
        )

    ignore_missing = bool(step.parameters.get("ignore_missing", False))
    missing_sources = [
        source
        for source in sources
        if isinstance(source, str) and source not in current_columns
    ]
    valid_mapping = [
        (source, target)
        for source, target in mapping
        if source in current_columns
        and isinstance(target, str)
        and bool(target.strip())
    ]
    for source in missing_sources:
        issue = _unknown_column_issue(
            source,
            step_index,
            step.step_type,
            "from",
            current_columns,
            warning=ignore_missing,
        )
        (warnings if ignore_missing else errors).append(issue)
    if ignore_missing and not valid_mapping:
        errors.append(
            _issue(
                "transform_invalid_step",
                "Rename step found no requested source columns.",
                step_index,
                step.step_type,
                "map",
            )
        )

    renamed_sources = {source for source, _ in valid_mapping}
    collisions = [
        target
        for _, target in valid_mapping
        if target in current_columns and target not in renamed_sources
    ]
    for target in _unique(collisions):
        errors.append(
            _issue(
                "transform_column_collision",
                f"Rename target column '{target}' already exists.",
                step_index,
                step.step_type,
                "to",
                referenced_column=target,
                suggestion="Choose a target that is not an existing unrenamed column.",
            )
        )

    validated_map = dict(valid_mapping)
    result = [validated_map.get(column, column) for column in current_columns]
    for duplicate in _duplicates(result):
        errors.append(
            _issue(
                "transform_duplicate_column",
                f"Rename would create duplicate column '{duplicate}'.",
                step_index,
                step.step_type,
                "to",
                referenced_column=duplicate,
            )
        )
    return _StepProjection(
        columns=result,
        referenced_columns=tuple(sources),
        renamed_columns=tuple(valid_mapping),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def _plan_convert_type(
    step: TransformStep,
    step_index: int,
    current_columns: list[str],
) -> _StepProjection:
    column = step.parameters["column"]
    target_type = step.parameters["data_type"]
    errors: list[TransformPlanIssue] = []
    if column not in current_columns:
        errors.append(
            _unknown_column_issue(
                column,
                step_index,
                step.step_type,
                "column",
                current_columns,
            )
        )
    normalized_type: str | None = None
    try:
        normalized_type = _normalize_target_type(target_type)
    except TransformationError:
        errors.append(
            _issue(
                "transform_unsupported_type",
                f"Unsupported transform target type '{target_type}'.",
                step_index,
                step.step_type,
                "data_type",
                suggestion=did_you_mean(
                    str(target_type),
                    (
                        "string",
                        "integer",
                        "float",
                        "boolean",
                        "datetime",
                        "date",
                        "category",
                    ),
                ),
            )
        )
    intended = (
        ((column, normalized_type),)
        if normalized_type is not None and isinstance(column, str)
        else ()
    )
    return _StepProjection(
        columns=list(current_columns),
        referenced_columns=(column,),
        intended_types=intended,
        errors=tuple(errors),
    )


def _plan_derive(
    step: TransformStep,
    step_index: int,
    current_columns: list[str],
) -> _StepProjection:
    column = step.parameters["column"]
    expression = step.parameters["expression"]
    analysis = parse_expression(expression)
    errors = _expression_issues(
        analysis,
        step_index,
        step.step_type,
        "expression",
    )
    errors.extend(
        _unknown_reference_issues(
            analysis,
            step_index,
            step.step_type,
            current_columns,
        )
    )
    if column in current_columns:
        errors.append(
            _issue(
                "transform_column_collision",
                f"Derived column '{column}' already exists.",
                step_index,
                step.step_type,
                "column",
                referenced_column=column,
                suggestion="Choose a new derived-column name.",
            )
        )
    result = list(current_columns)
    result.append(column)
    return _StepProjection(
        columns=result,
        referenced_columns=analysis.referenced_columns,
        expression=expression,
        expression_metadata=analysis,
        row_local=analysis.row_local,
        previewable=analysis.previewable,
        errors=tuple(errors),
    )


def _plan_filter(
    step: TransformStep,
    step_index: int,
    current_columns: list[str],
) -> _StepProjection:
    expression = step.parameters.get("expression")
    if expression is not None:
        analysis = parse_expression(expression)
        errors = _expression_issues(
            analysis,
            step_index,
            step.step_type,
            "expression",
        )
        errors.extend(
            _unknown_reference_issues(
                analysis,
                step_index,
                step.step_type,
                current_columns,
            )
        )
        if analysis.valid and analysis.result_kind not in {"boolean", "unknown"}:
            errors.append(
                _issue(
                    "transform_invalid_expression",
                    "Filter expression must produce a boolean result.",
                    step_index,
                    step.step_type,
                    "expression",
                    source_span=analysis.span,
                    suggestion="Use a comparison, boolean function, or boolean column.",
                )
            )
        return _StepProjection(
            columns=list(current_columns),
            referenced_columns=analysis.referenced_columns,
            expression=expression,
            expression_metadata=analysis,
            row_local=analysis.row_local,
            previewable=analysis.previewable,
            errors=tuple(errors),
        )
    return _plan_compatibility_filter(step, step_index, current_columns)


def _plan_compatibility_filter(
    step: TransformStep,
    step_index: int,
    current_columns: list[str],
) -> _StepProjection:
    conditions = step.parameters["conditions"]
    errors: list[TransformPlanIssue] = []
    referenced: list[str] = []
    mode = step.parameters.get("mode", "and")
    if mode not in {"and", "or"}:
        errors.append(
            _issue(
                "transform_invalid_step",
                f"Unsupported compatibility filter mode '{mode}'.",
                step_index,
                step.step_type,
                "mode",
                suggestion="Use 'and' or 'or'.",
            )
        )
    if not isinstance(conditions, tuple) or not conditions:
        errors.append(
            _issue(
                "transform_invalid_step",
                "Compatibility filter requires at least one condition.",
                step_index,
                step.step_type,
                "conditions",
            )
        )
        conditions = ()
    for condition in conditions:
        if not isinstance(condition, Mapping):
            errors.append(
                _issue(
                    "transform_invalid_step",
                    "Compatibility filter condition must be a mapping.",
                    step_index,
                    step.step_type,
                    "conditions",
                )
            )
            continue
        column = condition.get("column")
        operator = condition.get("operator")
        if isinstance(column, str):
            referenced.append(column)
            if column not in current_columns:
                errors.append(
                    _unknown_column_issue(
                        column,
                        step_index,
                        step.step_type,
                        "conditions",
                        current_columns,
                    )
                )
        else:
            errors.append(
                _issue(
                    "transform_invalid_step",
                    "Compatibility filter column must be a string.",
                    step_index,
                    step.step_type,
                    "conditions",
                )
            )
        try:
            _normalize_operator(str(operator))
        except TransformationError:
            errors.append(
                _issue(
                    "transform_invalid_step",
                    f"Unsupported compatibility filter operator '{operator}'.",
                    step_index,
                    step.step_type,
                    "conditions",
                )
            )
    return _StepProjection(
        columns=list(current_columns),
        referenced_columns=tuple(_unique(referenced)),
        errors=tuple(errors),
    )


def _plan_recode(
    step: TransformStep,
    step_index: int,
    current_columns: list[str],
) -> _StepProjection:
    column = step.parameters["column"]
    mapping = step.parameters["map"]
    errors: list[TransformPlanIssue] = []
    if column not in current_columns:
        errors.append(
            _unknown_column_issue(
                column,
                step_index,
                step.step_type,
                "column",
                current_columns,
            )
        )
    if not isinstance(mapping, Mapping) or not mapping:
        errors.append(
            _issue(
                "transform_invalid_recode_map",
                f"Recode map for column '{column}' must not be empty.",
                step_index,
                step.step_type,
                "map",
                referenced_column=column,
            )
        )
    return _StepProjection(
        columns=list(current_columns),
        referenced_columns=(column,),
        recode_map_keys=(
            tuple(str(key) for key in mapping)
            if isinstance(mapping, Mapping)
            else ()
        ),
        recode_map_count=len(mapping) if isinstance(mapping, Mapping) else 0,
        recode_uses_default="default" in step.parameters,
        recode_default=step.parameters.get("default"),
        recode_updates_value_labels=bool(
            step.parameters.get("update_value_labels", True)
        ),
        recode_affects_missing_values=False,
        errors=tuple(errors),
    )


def _plan_sort(
    step: TransformStep,
    step_index: int,
    current_columns: list[str],
) -> _StepProjection:
    columns = [str(key["column"]) for key in step.parameters["keys"]]
    errors = _duplicate_column_issues(
        columns,
        step_index,
        step.step_type,
        "keys",
    )
    errors.extend(
        _unknown_column_issue(
            column,
            step_index,
            step.step_type,
            "keys",
            current_columns,
        )
        for column in columns
        if column not in current_columns
    )
    return _StepProjection(
        columns=list(current_columns),
        referenced_columns=tuple(columns),
        row_local=False,
        errors=tuple(errors),
    )


def _plan_distinct(
    step: TransformStep,
    step_index: int,
    current_columns: list[str],
) -> _StepProjection:
    columns = list(step.parameters["columns"])
    errors = _duplicate_column_issues(
        columns,
        step_index,
        step.step_type,
        "columns",
    )
    errors.extend(
        _unknown_column_issue(
            column,
            step_index,
            step.step_type,
            "columns",
            current_columns,
        )
        for column in columns
        if column not in current_columns
    )
    return _StepProjection(
        columns=list(current_columns),
        referenced_columns=tuple(columns),
        row_local=False,
        errors=tuple(errors),
    )


def _plan_row_number(
    step: TransformStep,
    step_index: int,
    current_columns: list[str],
) -> _StepProjection:
    column = step.parameters["column"]
    errors: list[TransformPlanIssue] = []
    if column in current_columns:
        errors.append(
            _issue(
                "transform_column_collision",
                f"Row-number column '{column}' already exists.",
                step_index,
                step.step_type,
                "column",
                referenced_column=column,
                suggestion="Choose a new row-number column name.",
            )
        )
    return _StepProjection(
        columns=[*current_columns, column],
        row_local=False,
        errors=tuple(errors),
    )


def _expression_issues(
    analysis: ParsedExpression,
    step_index: int,
    step_type: TransformStepType,
    field: str,
) -> list[TransformPlanIssue]:
    return [
        _issue(
            "transform_invalid_expression",
            error.message,
            step_index,
            step_type,
            field,
            source_span=SourceSpan(error.start, error.end),
            suggestion=error.suggestion,
        )
        for error in analysis.errors
    ]


def _unknown_reference_issues(
    analysis: ParsedExpression,
    step_index: int,
    step_type: TransformStepType,
    current_columns: list[str],
) -> list[TransformPlanIssue]:
    return [
        _unknown_column_issue(
            column,
            step_index,
            step_type,
            "expression",
            current_columns,
            code="transform_unknown_referenced_column",
            source_span=_column_source_span(analysis, column),
        )
        for column in analysis.referenced_columns
        if column not in current_columns
    ]


def _column_source_span(
    analysis: ParsedExpression,
    column: str,
) -> SourceSpan | None:
    if analysis.ast is None:
        return None
    return _find_column_span(analysis.ast.root, column)


def _find_column_span(node: Any, column: str) -> SourceSpan | None:
    if isinstance(node, ColumnReferenceNode):
        return node.span if node.name == column else None
    if isinstance(node, FunctionCallNode):
        for argument in node.arguments:
            if (span := _find_column_span(argument, column)) is not None:
                return span
    elif isinstance(node, BinaryOpNode):
        return _find_column_span(node.left, column) or _find_column_span(
            node.right,
            column,
        )
    elif isinstance(node, UnaryOpNode):
        return _find_column_span(node.operand, column)
    elif isinstance(node, GroupNode):
        return _find_column_span(node.expression, column)
    return None


def _resolve_requested_columns(
    requested: list[str],
    current_columns: list[str],
    step: TransformStep,
    step_index: int,
    *,
    field: str,
) -> tuple[
    list[str],
    list[str],
    list[TransformPlanIssue],
    list[TransformPlanIssue],
]:
    found = [column for column in requested if column in current_columns]
    unknown = [column for column in requested if column not in current_columns]
    errors: list[TransformPlanIssue] = []
    warnings: list[TransformPlanIssue] = []
    ignore_missing = bool(step.parameters.get("ignore_missing", False))
    for column in _unique(unknown):
        issue = _unknown_column_issue(
            column,
            step_index,
            step.step_type,
            field,
            current_columns,
            warning=ignore_missing,
        )
        (warnings if ignore_missing else errors).append(issue)
    return found, unknown, errors, warnings


def _duplicate_column_issues(
    columns: list[Any],
    step_index: int,
    step_type: TransformStepType,
    field: str,
) -> list[TransformPlanIssue]:
    return [
        _issue(
            "transform_duplicate_column",
            f"Column '{column}' is duplicated in this step.",
            step_index,
            step_type,
            field,
            referenced_column=str(column),
            suggestion="List each column only once.",
        )
        for column in _duplicates(columns)
    ]


def _unknown_column_issue(
    column: Any,
    step_index: int,
    step_type: TransformStepType,
    field: str,
    current_columns: list[str],
    *,
    warning: bool = False,
    code: str = "transform_unknown_column",
    source_span: SourceSpan | None = None,
) -> TransformPlanIssue:
    suggestion = did_you_mean(str(column), current_columns)
    if warning:
        message = f"Unknown column '{column}' will be ignored."
        code = "transform_ignored_unknown_column"
    else:
        message = f"Unknown column '{column}'."
    return _issue(
        code,
        message,
        step_index,
        step_type,
        field,
        referenced_column=str(column),
        source_span=source_span,
        suggestion=suggestion,
    )


def _issue(
    code: str,
    message: str,
    step_index: int,
    step_type: TransformStepType,
    field: str,
    *,
    referenced_column: str | None = None,
    source_span: SourceSpan | None = None,
    suggestion: str | None = None,
) -> TransformPlanIssue:
    return TransformPlanIssue(
        code=code,
        message=message,
        step_index=step_index,
        step_type=step_type,
        field=field,
        referenced_column=referenced_column,
        source_span=source_span,
        suggestion=suggestion,
    )


def _duplicates(values: Sequence[Any]) -> list[Any]:
    seen: list[Any] = []
    duplicates: list[Any] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.append(value)
    return duplicates


def _unique(values: Sequence[Any]) -> list[Any]:
    result: list[Any] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result

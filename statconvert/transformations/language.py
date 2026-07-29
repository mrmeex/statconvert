from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExpressionFunctionSpec:
    """Non-executing metadata for one safe expression function."""

    name: str
    category: str
    minimum_arguments: int
    maximum_arguments: int
    result_kind: str
    row_local: bool = True
    previewable: bool = True
    deferred: bool = False

    def to_dict(self) -> dict[str, object]:
        """Return deterministic JSON-safe function metadata."""

        arity: object
        if self.minimum_arguments == self.maximum_arguments:
            arity = self.minimum_arguments
        else:
            arity = {
                "minimum": self.minimum_arguments,
                "maximum": self.maximum_arguments,
            }
        return {
            "name": self.name,
            "category": self.category,
            "arity": arity,
            "minimum_arguments": self.minimum_arguments,
            "maximum_arguments": self.maximum_arguments,
            "row_local": self.row_local,
            "previewable": self.previewable,
            "result_kind": self.result_kind,
            "deferred": self.deferred,
        }


CORE_EXPRESSION_FUNCTIONS: tuple[ExpressionFunctionSpec, ...] = (
    ExpressionFunctionSpec("strip", "text", 1, 1, "string"),
    ExpressionFunctionSpec("lower", "text", 1, 1, "string"),
    ExpressionFunctionSpec("upper", "text", 1, 1, "string"),
    ExpressionFunctionSpec("contains", "text", 2, 2, "boolean"),
    ExpressionFunctionSpec("starts_with", "text", 2, 2, "boolean"),
    ExpressionFunctionSpec("ends_with", "text", 2, 2, "boolean"),
    ExpressionFunctionSpec("abs", "numeric", 1, 1, "number"),
    ExpressionFunctionSpec("round", "numeric", 2, 2, "number"),
    ExpressionFunctionSpec("is_null", "missing", 1, 1, "boolean"),
    ExpressionFunctionSpec("not_null", "missing", 1, 1, "boolean"),
    ExpressionFunctionSpec("coalesce", "missing", 2, 2, "dynamic"),
    ExpressionFunctionSpec("normalize_whitespace", "text", 1, 1, "string"),
    ExpressionFunctionSpec("null_if", "missing", 2, 2, "dynamic"),
    ExpressionFunctionSpec("null_if_empty", "missing", 1, 1, "string"),
    ExpressionFunctionSpec("default_if_missing", "missing", 2, 2, "dynamic"),
    ExpressionFunctionSpec("normalize_code", "normalization", 1, 1, "string"),
    ExpressionFunctionSpec("if_else", "conditional", 3, 3, "dynamic"),
)

DEFERRED_EXPRESSION_FUNCTIONS: tuple[ExpressionFunctionSpec, ...] = tuple(
    ExpressionFunctionSpec(
        name,
        category,
        minimum_arguments,
        maximum_arguments,
        result_kind,
        deferred=True,
    )
    for name, category, minimum_arguments, maximum_arguments, result_kind in (
        ("replace", "text", 3, 3, "string"),
        ("regex_match", "text", 2, 2, "boolean"),
        ("regex_replace", "text", 3, 3, "string"),
        ("length", "text", 1, 1, "integer"),
        ("substring", "text", 2, 3, "string"),
        ("concat", "text", 2, 2, "string"),
        ("remove_accents", "text", 1, 1, "string"),
        ("parse_date", "date", 1, 2, "date"),
        ("format_date", "date", 2, 2, "string"),
        ("year", "date", 1, 1, "integer"),
        ("month", "date", 1, 1, "integer"),
        ("day", "date", 1, 1, "integer"),
        ("weekday", "date", 1, 1, "integer"),
        ("date_diff", "date", 2, 3, "number"),
        ("add_days", "date", 2, 2, "date"),
        ("to_string", "conversion", 1, 1, "string"),
        ("to_number", "conversion", 1, 1, "number"),
        ("to_integer", "conversion", 1, 1, "integer"),
        ("to_float", "conversion", 1, 1, "number"),
        ("to_boolean", "conversion", 1, 1, "boolean"),
        ("to_date", "conversion", 1, 2, "date"),
        ("between", "comparison", 3, 3, "boolean"),
        ("is_in", "comparison", 2, 2, "boolean"),
        ("not_in", "comparison", 2, 2, "boolean"),
        ("is_number", "validation", 1, 1, "boolean"),
        ("is_date", "validation", 1, 1, "boolean"),
        ("is_email", "validation", 1, 1, "boolean"),
    )
)

EXCLUDED_NON_ROW_LOCAL_FUNCTIONS: frozenset[str] = frozenset(
    {
        "sum",
        "mean",
        "median",
        "count",
        "rank",
        "lag",
        "lead",
        "group_by",
        "join",
        "window",
    }
)


def expression_function_specs(
    *,
    include_deferred: bool = False,
) -> tuple[ExpressionFunctionSpec, ...]:
    """Return function metadata without providing parser or execution behavior."""

    if include_deferred:
        return CORE_EXPRESSION_FUNCTIONS + DEFERRED_EXPRESSION_FUNCTIONS
    return CORE_EXPRESSION_FUNCTIONS

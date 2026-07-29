from __future__ import annotations

from dataclasses import dataclass
from numbers import Number
import re
from typing import Any

import pandas as pd

from statconvert.transformations.exceptions import TransformationError

from .ast import (
    BinaryOpNode,
    ColumnReferenceNode,
    Expression,
    ExpressionNode,
    FunctionCallNode,
    GroupNode,
    LiteralNode,
    SourceSpan,
    UnaryOpNode,
)
from .metadata import ParsedExpression, parse_expression


@dataclass(frozen=True)
class ExpressionEvaluationIssue:
    """One deterministic expression evaluation failure."""

    code: str
    message: str
    expression: str
    source_span: SourceSpan
    referenced_column: str | None = None
    function: str | None = None
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "expression": self.expression,
            "source_span": self.source_span.to_dict(),
        }
        if self.referenced_column is not None:
            result["referenced_column"] = self.referenced_column
        if self.function is not None:
            result["function"] = self.function
        if self.suggestion is not None:
            result["suggestion"] = self.suggestion
        return result


class ExpressionEvaluationError(TransformationError):
    """Safe evaluator error containing structured machine-readable context."""

    def __init__(self, issue: ExpressionEvaluationIssue) -> None:
        super().__init__(issue.message, suggestion=issue.suggestion)
        self.issue = issue


def evaluate_expression(
    expression: str | ParsedExpression | Expression,
    dataframe: pd.DataFrame,
) -> Any:
    """Evaluate only the closed StatConvert AST against one DataFrame."""

    source, parsed_ast = _normalize_expression(expression)
    try:
        return _evaluate_node(parsed_ast.root, dataframe, source)
    except ExpressionEvaluationError:
        raise
    except Exception as exc:
        raise ExpressionEvaluationError(
            ExpressionEvaluationIssue(
                code="expression_evaluation_failed",
                message="Expression evaluation failed safely.",
                expression=source,
                source_span=parsed_ast.span,
                suggestion="Check expression values and operand types.",
            )
        ) from exc


def boolean_mask(
    value: Any,
    dataframe: pd.DataFrame,
    *,
    expression: str,
    source_span: SourceSpan,
) -> pd.Series:
    """Return an index-aligned boolean mask, treating missing values as false."""

    if isinstance(value, pd.Series):
        if not _is_boolean_series(value):
            _raise(
                "expression_non_boolean_filter",
                "Filter expression did not produce boolean values.",
                expression,
                source_span,
                suggestion="Use a comparison, boolean function, or boolean column.",
            )
        return value.astype("boolean").fillna(False).astype(bool)
    if isinstance(value, bool):
        return pd.Series(value, index=dataframe.index, dtype=bool)
    if value is pd.NA or value is None or _is_scalar_missing(value):
        return pd.Series(False, index=dataframe.index, dtype=bool)
    _raise(
        "expression_non_boolean_filter",
        "Filter expression did not produce a boolean result.",
        expression,
        source_span,
        suggestion="Use a comparison, boolean function, or boolean column.",
    )


def _normalize_expression(
    expression: str | ParsedExpression | Expression,
) -> tuple[str, Expression]:
    if isinstance(expression, str):
        analysis = parse_expression(expression)
        if not analysis.valid or analysis.ast is None:
            error = analysis.errors[0]
            raise ExpressionEvaluationError(
                ExpressionEvaluationIssue(
                    code="expression_invalid",
                    message=error.message,
                    expression=expression,
                    source_span=SourceSpan(error.start, error.end),
                    suggestion=error.suggestion,
                )
            )
        return expression, analysis.ast
    if isinstance(expression, ParsedExpression):
        if not expression.valid or expression.ast is None:
            error = expression.errors[0]
            raise ExpressionEvaluationError(
                ExpressionEvaluationIssue(
                    code="expression_invalid",
                    message=error.message,
                    expression=expression.expression,
                    source_span=SourceSpan(error.start, error.end),
                    suggestion=error.suggestion,
                )
            )
        return expression.expression, expression.ast
    if isinstance(expression, Expression):
        return "", expression
    raise TypeError("Expression must be text, ParsedExpression, or Expression.")


def _evaluate_node(
    node: ExpressionNode,
    dataframe: pd.DataFrame,
    expression: str,
) -> Any:
    if isinstance(node, LiteralNode):
        return pd.NA if node.literal_kind == "null" else node.value
    if isinstance(node, ColumnReferenceNode):
        if node.name not in dataframe.columns:
            _raise(
                "expression_unknown_column",
                f"Unknown expression column '{node.name}'.",
                expression,
                node.span,
                referenced_column=node.name,
            )
        return dataframe[node.name]
    if isinstance(node, GroupNode):
        return _evaluate_node(node.expression, dataframe, expression)
    if isinstance(node, UnaryOpNode):
        value = _evaluate_node(node.operand, dataframe, expression)
        if node.operator == "not":
            mask = _boolean_operand(value, dataframe, expression, node.span)
            return ~mask if isinstance(mask, pd.Series) else not mask
        numeric = _numeric_operand(value, expression, node.span)
        return _apply_operator(
            lambda: -numeric,
            expression,
            node.span,
            "unary '-'",
        )
    if isinstance(node, BinaryOpNode):
        return _evaluate_binary(node, dataframe, expression)
    if isinstance(node, FunctionCallNode):
        arguments = [
            _evaluate_node(argument, dataframe, expression)
            for argument in node.arguments
        ]
        return _evaluate_function(node, arguments, dataframe, expression)
    _raise(
        "expression_evaluation_failed",
        "Unsupported internal expression node.",
        expression,
        node.span,
    )


def _evaluate_binary(
    node: BinaryOpNode,
    dataframe: pd.DataFrame,
    expression: str,
) -> Any:
    left = _evaluate_node(node.left, dataframe, expression)
    right = _evaluate_node(node.right, dataframe, expression)
    if node.operator in {"and", "or"}:
        left_mask = _boolean_operand(left, dataframe, expression, node.left.span)
        right_mask = _boolean_operand(right, dataframe, expression, node.right.span)
        operation = (
            (lambda: left_mask & right_mask)
            if node.operator == "and"
            else (lambda: left_mask | right_mask)
        )
        return _apply_operator(operation, expression, node.span, node.operator)

    if node.operator in {"+", "-", "*", "/"}:
        left_number = _numeric_operand(left, expression, node.left.span)
        right_number = _numeric_operand(right, expression, node.right.span)
        if node.operator == "/" and _contains_zero(right_number):
            _raise(
                "expression_division_by_zero",
                "Division by zero is not allowed in transform expressions.",
                expression,
                node.right.span,
                suggestion="Filter or replace zero divisors before division.",
            )
        operations = {
            "+": lambda: left_number + right_number,
            "-": lambda: left_number - right_number,
            "*": lambda: left_number * right_number,
            "/": lambda: left_number / right_number,
        }
        return _apply_operator(
            operations[node.operator],
            expression,
            node.span,
            node.operator,
        )

    operations = {
        "==": lambda: left == right,
        "!=": lambda: left != right,
        "<": lambda: left < right,
        "<=": lambda: left <= right,
        ">": lambda: left > right,
        ">=": lambda: left >= right,
    }
    return _apply_operator(
        operations[node.operator],
        expression,
        node.span,
        node.operator,
    )


def _evaluate_function(
    node: FunctionCallNode,
    arguments: list[Any],
    dataframe: pd.DataFrame,
    expression: str,
) -> Any:
    name = node.name
    if name in {"strip", "lower", "upper"}:
        value = _string_operand(arguments[0], expression, node.arguments[0].span, name)
        if isinstance(value, pd.Series):
            strings = value.astype("string")
            return getattr(strings.str, name)()
        if _is_scalar_missing(value):
            return pd.NA
        return getattr(value, name)()

    if name in {"contains", "starts_with", "ends_with"}:
        value = _string_operand(arguments[0], expression, node.arguments[0].span, name)
        text = arguments[1]
        if not isinstance(text, str):
            _raise(
                "expression_incompatible_type",
                f"Function '{name}' requires a string search value.",
                expression,
                node.arguments[1].span,
                function=name,
            )
        if isinstance(value, pd.Series):
            strings = value.astype("string")
            if name == "contains":
                return strings.str.contains(text, regex=False, na=False)
            method = "startswith" if name == "starts_with" else "endswith"
            return getattr(strings.str, method)(text, na=False)
        if _is_scalar_missing(value):
            return False
        if name == "contains":
            return text in value
        if name == "starts_with":
            return value.startswith(text)
        return value.endswith(text)

    if name in {"normalize_whitespace", "normalize_code"}:
        value = _string_operand(arguments[0], expression, node.arguments[0].span, name)
        normalized = _normalize_whitespace(value)
        if name == "normalize_code":
            if isinstance(normalized, pd.Series):
                return normalized.str.upper()
            if _is_scalar_missing(normalized):
                return pd.NA
            return normalized.upper()
        return normalized

    if name == "abs":
        value = _numeric_operand(arguments[0], expression, node.arguments[0].span)
        return _apply_operator(abs, expression, node.span, name, value)

    if name == "round":
        value = _numeric_operand(arguments[0], expression, node.arguments[0].span)
        digits = arguments[1]
        if not isinstance(digits, int) or isinstance(digits, bool):
            _raise(
                "expression_incompatible_type",
                "Function 'round' requires an integer digits argument.",
                expression,
                node.arguments[1].span,
                function=name,
            )
        return _apply_operator(round, expression, node.span, name, value, digits)

    if name == "is_null":
        value = arguments[0]
        return value.isna() if isinstance(value, pd.Series) else _is_scalar_missing(value)

    if name == "not_null":
        value = arguments[0]
        return value.notna() if isinstance(value, pd.Series) else not _is_scalar_missing(
            value
        )

    if name == "coalesce":
        value, fallback = arguments
        return _coalesce(value, fallback, dataframe.index)

    if name == "null_if":
        return _null_if(arguments[0], arguments[1], dataframe.index, expression, node)

    if name == "null_if_empty":
        value = _string_operand(
            arguments[0],
            expression,
            node.arguments[0].span,
            name,
        )
        if isinstance(value, pd.Series):
            empty = value.astype("string").str.strip().eq("").fillna(False)
            return value.mask(empty, pd.NA)
        if _is_scalar_missing(value):
            return pd.NA
        return pd.NA if value.strip() == "" else value

    if name == "default_if_missing":
        return _coalesce(arguments[0], arguments[1], dataframe.index)

    if name == "if_else":
        condition = boolean_mask(
            arguments[0],
            dataframe,
            expression=expression,
            source_span=node.arguments[0].span,
        )
        true_values = _as_series(arguments[1], dataframe.index)
        false_values = _as_series(arguments[2], dataframe.index)
        return true_values.where(condition, false_values)

    _raise(
        "expression_unsupported_function",
        f"Unsupported expression function '{name}'.",
        expression,
        node.name_span,
        function=name,
    )


def _string_operand(
    value: Any,
    expression: str,
    span: SourceSpan,
    function: str,
) -> Any:
    if isinstance(value, pd.Series):
        non_missing = value.dropna()
        if not non_missing.map(lambda item: isinstance(item, str)).all():
            _raise(
                "expression_incompatible_type",
                f"Function '{function}' requires string-like values.",
                expression,
                span,
                function=function,
            )
        return value
    if isinstance(value, str) or _is_scalar_missing(value):
        return value
    _raise(
        "expression_incompatible_type",
        f"Function '{function}' requires a string-like value.",
        expression,
        span,
        function=function,
    )


def _normalize_whitespace(value: Any) -> Any:
    if isinstance(value, pd.Series):
        return value.astype("string").str.replace(r"\s+", " ", regex=True).str.strip()
    if _is_scalar_missing(value):
        return pd.NA
    return re.sub(r"\s+", " ", value).strip()


def _coalesce(value: Any, fallback: Any, index: pd.Index) -> Any:
    if isinstance(value, pd.Series):
        if isinstance(fallback, pd.Series):
            fallback = fallback.reindex(index)
        return value.where(value.notna(), fallback)
    if _is_scalar_missing(value):
        return fallback.reindex(index) if isinstance(fallback, pd.Series) else fallback
    return value


def _null_if(
    value: Any,
    match: Any,
    index: pd.Index,
    expression: str,
    node: FunctionCallNode,
) -> Any:
    if isinstance(value, pd.Series) or isinstance(match, pd.Series):
        values = _as_series(value, index)
        matches = _as_series(match, index)
        equal = _apply_operator(
            lambda: values == matches,
            expression,
            node.span,
            "null_if",
        )
        if not isinstance(equal, pd.Series):
            equal = pd.Series(bool(equal), index=index)
        equal = equal.astype("boolean").fillna(False)
        return values.mask(equal, pd.NA)
    if _is_scalar_missing(value):
        return pd.NA
    if _is_scalar_missing(match):
        return value
    equal = _apply_operator(
        lambda: value == match,
        expression,
        node.span,
        "null_if",
    )
    try:
        return pd.NA if bool(equal) else value
    except (TypeError, ValueError) as exc:
        raise ExpressionEvaluationError(
            ExpressionEvaluationIssue(
                code="expression_incompatible_type",
                message="Function 'null_if' requires equality-compatible values.",
                expression=expression,
                source_span=node.span,
                function="null_if",
            )
        ) from exc


def _numeric_operand(
    value: Any,
    expression: str,
    span: SourceSpan,
) -> Any:
    if isinstance(value, pd.Series):
        non_missing = value.dropna()
        if not non_missing.map(_is_number).all():
            _raise(
                "expression_incompatible_type",
                "Numeric expression requires numeric-compatible values.",
                expression,
                span,
            )
        return value
    if _is_number(value) or _is_scalar_missing(value):
        return value
    _raise(
        "expression_incompatible_type",
        "Numeric expression requires numeric-compatible values.",
        expression,
        span,
    )


def _boolean_operand(
    value: Any,
    dataframe: pd.DataFrame,
    expression: str,
    span: SourceSpan,
) -> bool | pd.Series:
    if isinstance(value, pd.Series):
        if not _is_boolean_series(value):
            _raise(
                "expression_incompatible_type",
                "Boolean expression requires boolean-compatible values.",
                expression,
                span,
            )
        return value.astype("boolean").fillna(False)
    if isinstance(value, bool):
        return value
    if _is_scalar_missing(value):
        return False
    _raise(
        "expression_incompatible_type",
        "Boolean expression requires boolean-compatible values.",
        expression,
        span,
    )


def _is_boolean_series(value: pd.Series) -> bool:
    non_missing = value.dropna()
    return non_missing.map(lambda item: isinstance(item, bool)).all()


def _as_series(value: Any, index: pd.Index) -> pd.Series:
    if isinstance(value, pd.Series):
        return value.reindex(index)
    return pd.Series(value, index=index)


def _contains_zero(value: Any) -> bool:
    if isinstance(value, pd.Series):
        return bool((value == 0).fillna(False).any())
    return bool(value == 0) if not _is_scalar_missing(value) else False


def _is_number(value: Any) -> bool:
    return isinstance(value, Number) and not isinstance(value, bool)


def _is_scalar_missing(value: Any) -> bool:
    if value is pd.NA or value is None:
        return True
    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return bool(result) if not hasattr(result, "__len__") else False


def _apply_operator(
    operation: Any,
    expression: str,
    span: SourceSpan,
    label: str,
    *arguments: Any,
) -> Any:
    try:
        return operation(*arguments)
    except ExpressionEvaluationError:
        raise
    except Exception as exc:
        raise ExpressionEvaluationError(
            ExpressionEvaluationIssue(
                code="expression_incompatible_type",
                message=f"Expression operation '{label}' has incompatible values.",
                expression=expression,
                source_span=span,
                suggestion="Use operands with compatible types.",
            )
        ) from exc


def _raise(
    code: str,
    message: str,
    expression: str,
    source_span: SourceSpan,
    *,
    referenced_column: str | None = None,
    function: str | None = None,
    suggestion: str | None = None,
) -> None:
    raise ExpressionEvaluationError(
        ExpressionEvaluationIssue(
            code=code,
            message=message,
            expression=expression,
            source_span=source_span,
            referenced_column=referenced_column,
            function=function,
            suggestion=suggestion,
        )
    )

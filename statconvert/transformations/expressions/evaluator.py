from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import math
from numbers import Integral, Number
import re
from typing import Any
import unicodedata

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


MAX_REGEX_PATTERN_LENGTH = 256
MAX_REGEX_INPUT_LENGTH = 10_000
_NUMERIC_TEXT_PATTERN = re.compile(
    r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$"
)
_INTEGER_TEXT_PATTERN = re.compile(r"^[+-]?[0-9]+$")
_BOOLEAN_TRUE_TOKENS = frozenset({"true", "yes", "y", "t", "1"})
_BOOLEAN_FALSE_TOKENS = frozenset({"false", "no", "n", "f", "0"})
_MIN_INT64 = -(2**63)
_MAX_INT64 = 2**63 - 1
_DATE_FORMAT_DIRECTIVES = frozenset({"Y", "m", "d"})
_DATE_PARSE_PATTERNS = {
    "Y": r"[0-9]{4}",
    "m": r"[0-9]{2}",
    "d": r"[0-9]{2}",
}


@dataclass(frozen=True)
class _DateFormatSpec:
    value: str
    input_pattern: re.Pattern[str]


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
    if name == "replace":
        return _evaluate_replace(arguments, dataframe.index)

    if name == "regex_match":
        pattern = _compile_regex(
            arguments[1],
            expression,
            node.arguments[1].span,
            name,
        )
        return _evaluate_regex_match(
            arguments[0],
            pattern,
            dataframe.index,
            expression,
            node.arguments[0].span,
            name,
        )

    if name == "regex_replace":
        pattern = _compile_regex(
            arguments[1],
            expression,
            node.arguments[1].span,
            name,
        )
        replacement = _regex_replacement(
            arguments[2],
            pattern,
            expression,
            node.arguments[2].span,
            name,
        )
        if replacement is None:
            return _missing_result(arguments, dataframe.index, "string")
        return _evaluate_regex_replace(
            arguments[0],
            pattern,
            replacement,
            dataframe.index,
            expression,
            node.arguments[0].span,
            name,
        )

    if name == "length":
        return _evaluate_length(arguments[0], dataframe.index)

    if name == "substring":
        return _evaluate_substring(
            arguments,
            dataframe.index,
            expression,
            node,
        )

    if name == "concat":
        return _evaluate_concat(arguments, dataframe.index)

    if name == "remove_accents":
        return _evaluate_remove_accents(arguments[0], dataframe.index)

    if name == "to_string":
        return _evaluate_to_string(arguments[0], dataframe.index)

    if name == "to_number":
        return _evaluate_to_number(arguments[0], dataframe.index)

    if name == "to_integer":
        return _evaluate_to_integer(arguments[0], dataframe.index)

    if name == "to_float":
        return _evaluate_to_float(arguments[0], dataframe.index)

    if name == "to_boolean":
        return _evaluate_to_boolean(arguments[0], dataframe.index)

    if name == "parse_date":
        format_spec = _date_format(
            arguments[1],
            expression,
            node.arguments[1].span,
            name,
            require_complete_date=True,
        )
        return _evaluate_parse_date(arguments[0], format_spec, dataframe.index)

    if name == "format_date":
        format_spec = _date_format(
            arguments[1],
            expression,
            node.arguments[1].span,
            name,
        )
        return _evaluate_format_date(arguments[0], format_spec, dataframe.index)

    if name in {"year", "month", "day", "weekday"}:
        return _evaluate_date_part(name, arguments[0], dataframe.index)

    if name == "date_diff":
        return _evaluate_date_diff(arguments, dataframe.index)

    if name == "add_days":
        return _evaluate_add_days(arguments, dataframe.index)

    if name == "between":
        return _evaluate_between(arguments, dataframe.index, expression, node)

    if name in {"is_in", "not_in"}:
        return _evaluate_membership(
            arguments,
            dataframe.index,
            expression,
            node,
            negate=name == "not_in",
        )

    if name == "is_number":
        return _evaluate_is_number(arguments[0], dataframe.index)

    if name == "is_date":
        format_spec = _date_format(
            arguments[1],
            expression,
            node.arguments[1].span,
            name,
            require_complete_date=True,
        )
        return _evaluate_is_date(arguments[0], format_spec, dataframe.index)

    if name == "is_email":
        return _evaluate_is_email(arguments[0], dataframe.index)

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


_INVALID_TEXT = object()


def _evaluate_replace(arguments: list[Any], index: pd.Index) -> Any:
    def replace_one(value: Any, old: Any, new: Any) -> Any:
        converted = tuple(_deterministic_text(item) for item in (value, old, new))
        if any(item is None or item is _INVALID_TEXT for item in converted):
            return pd.NA
        text, old_text, new_text = converted
        return text.replace(old_text, new_text)

    return _apply_row_local(arguments, index, replace_one, dtype="string")


def _compile_regex(
    value: Any,
    expression: str,
    span: SourceSpan,
    function: str,
) -> re.Pattern[str]:
    if isinstance(value, pd.Series):
        _raise(
            "expression_non_scalar_control",
            f"Function '{function}' requires a scalar regular expression pattern.",
            expression,
            span,
            function=function,
        )
    if _is_scalar_missing(value):
        _raise(
            "expression_null_control",
            f"Function '{function}' requires a non-null regular expression pattern.",
            expression,
            span,
            function=function,
        )
    if not isinstance(value, str):
        _raise(
            "expression_incompatible_type",
            f"Function '{function}' requires a string regular expression pattern.",
            expression,
            span,
            function=function,
        )
    if len(value) > MAX_REGEX_PATTERN_LENGTH:
        _raise(
            "expression_regex_pattern_too_long",
            (
                f"Function '{function}' regular expression pattern exceeds "
                f"{MAX_REGEX_PATTERN_LENGTH} characters."
            ),
            expression,
            span,
            function=function,
            suggestion="Use a shorter bounded pattern.",
        )
    try:
        return re.compile(value)
    except re.error as exc:
        _raise(
            "expression_invalid_regex",
            f"Function '{function}' has an invalid regular expression pattern: {exc}.",
            expression,
            span,
            function=function,
            suggestion="Correct the regular expression pattern.",
        )


def _evaluate_regex_match(
    value: Any,
    pattern: re.Pattern[str],
    index: pd.Index,
    expression: str,
    span: SourceSpan,
    function: str,
) -> Any:
    def match_one(item: Any) -> bool:
        text = _bounded_regex_text(item, expression, span, function)
        if text is None or text is _INVALID_TEXT:
            return False
        return pattern.search(text) is not None

    return _apply_row_local([value], index, match_one, dtype="bool")


def _regex_replacement(
    value: Any,
    pattern: re.Pattern[str],
    expression: str,
    span: SourceSpan,
    function: str,
) -> str | None:
    if isinstance(value, pd.Series):
        _raise(
            "expression_non_scalar_control",
            f"Function '{function}' requires a scalar replacement value.",
            expression,
            span,
            function=function,
        )
    replacement = _deterministic_text(value)
    if replacement is None:
        return None
    if replacement is _INVALID_TEXT:
        _raise(
            "expression_incompatible_type",
            f"Function '{function}' requires a text-convertible replacement value.",
            expression,
            span,
            function=function,
        )
    try:
        pattern.sub(replacement, "")
    except re.error as exc:
        _raise(
            "expression_invalid_regex_replacement",
            f"Function '{function}' has an invalid replacement value: {exc}.",
            expression,
            span,
            function=function,
            suggestion="Correct the regular expression replacement.",
        )
    return replacement


def _evaluate_regex_replace(
    value: Any,
    pattern: re.Pattern[str],
    replacement: str,
    index: pd.Index,
    expression: str,
    span: SourceSpan,
    function: str,
) -> Any:
    def replace_one(item: Any) -> Any:
        text = _bounded_regex_text(item, expression, span, function)
        if text is None or text is _INVALID_TEXT:
            return pd.NA
        return pattern.sub(replacement, text)

    return _apply_row_local([value], index, replace_one, dtype="string")


def _bounded_regex_text(
    value: Any,
    expression: str,
    span: SourceSpan,
    function: str,
) -> str | None | object:
    text = _deterministic_text(value)
    if isinstance(text, str) and len(text) > MAX_REGEX_INPUT_LENGTH:
        _raise(
            "expression_regex_input_too_long",
            (
                f"Function '{function}' input exceeds "
                f"{MAX_REGEX_INPUT_LENGTH} characters."
            ),
            expression,
            span,
            function=function,
            suggestion="Shorten the input before applying a regular expression.",
        )
    return text


def _evaluate_length(value: Any, index: pd.Index) -> Any:
    def length_one(item: Any) -> Any:
        text = _deterministic_text(item)
        if text is None or text is _INVALID_TEXT:
            return pd.NA
        return len(text)

    return _apply_row_local([value], index, length_one, dtype="Int64")


def _evaluate_substring(
    arguments: list[Any],
    index: pd.Index,
    expression: str,
    node: FunctionCallNode,
) -> Any:
    start, end = arguments[1], arguments[2]
    if isinstance(start, pd.Series) or isinstance(end, pd.Series):
        span = (
            node.arguments[1].span
            if isinstance(start, pd.Series)
            else node.arguments[2].span
        )
        _raise(
            "expression_non_scalar_control",
            "Function 'substring' requires scalar start and end indexes.",
            expression,
            span,
            function="substring",
        )
    start_index = _exact_non_negative_integer(start)
    end_index = _exact_non_negative_integer(end)
    if start_index is None or end_index is None:
        return _missing_result(arguments, index, "string")

    def substring_one(value: Any) -> Any:
        text = _deterministic_text(value)
        if text is None or text is _INVALID_TEXT:
            return pd.NA
        return text[start_index:end_index]

    return _apply_row_local([arguments[0]], index, substring_one, dtype="string")


def _evaluate_concat(arguments: list[Any], index: pd.Index) -> Any:
    def concat_one(*values: Any) -> Any:
        parts: list[str] = []
        for value in values:
            text = _deterministic_text(value)
            if text is _INVALID_TEXT:
                return pd.NA
            parts.append("" if text is None else text)
        return "".join(parts)

    return _apply_row_local(arguments, index, concat_one, dtype="string")


def _evaluate_remove_accents(value: Any, index: pd.Index) -> Any:
    def remove_one(item: Any) -> Any:
        text = _deterministic_text(item)
        if text is None or text is _INVALID_TEXT:
            return pd.NA
        decomposed = unicodedata.normalize("NFKD", text)
        unaccented = "".join(
            character
            for character in decomposed
            if unicodedata.category(character) != "Mn"
        )
        return unicodedata.normalize("NFC", unaccented)

    return _apply_row_local([value], index, remove_one, dtype="string")


def _evaluate_to_string(value: Any, index: pd.Index) -> Any:
    def convert_one(item: Any) -> Any:
        converted = _deterministic_text(item)
        return pd.NA if converted is None or converted is _INVALID_TEXT else converted

    return _apply_row_local([value], index, convert_one, dtype="string")


def _evaluate_to_number(value: Any, index: pd.Index) -> Any:
    def convert_one(item: Any) -> Any:
        converted = _convert_number(item)
        return pd.NA if converted is None else converted

    return _apply_row_local([value], index, convert_one, dtype="object")


def _evaluate_to_integer(value: Any, index: pd.Index) -> Any:
    def convert_one(item: Any) -> Any:
        converted = _convert_number(item)
        if converted is None:
            return pd.NA
        try:
            integer = int(converted)
        except (TypeError, ValueError, OverflowError):
            return pd.NA
        if converted != integer or not _MIN_INT64 <= integer <= _MAX_INT64:
            return pd.NA
        return integer

    return _apply_row_local([value], index, convert_one, dtype="Int64")


def _evaluate_to_float(value: Any, index: pd.Index) -> Any:
    def convert_one(item: Any) -> Any:
        converted = _convert_number(item)
        if converted is None:
            return pd.NA
        try:
            result = float(converted)
        except (TypeError, ValueError, OverflowError):
            return pd.NA
        return result if math.isfinite(result) else pd.NA

    return _apply_row_local([value], index, convert_one, dtype="Float64")


def _evaluate_to_boolean(value: Any, index: pd.Index) -> Any:
    def convert_one(item: Any) -> Any:
        if _is_scalar_missing(item):
            return pd.NA
        if isinstance(item, bool):
            return item
        if _is_finite_number(item):
            if item == 1:
                return True
            if item == 0:
                return False
            return pd.NA
        if isinstance(item, str):
            token = item.strip().lower()
            if token in _BOOLEAN_TRUE_TOKENS:
                return True
            if token in _BOOLEAN_FALSE_TOKENS:
                return False
        return pd.NA

    return _apply_row_local([value], index, convert_one, dtype="boolean")


def _date_format(
    value: Any,
    expression: str,
    span: SourceSpan,
    function: str,
    *,
    require_complete_date: bool = False,
) -> _DateFormatSpec:
    if isinstance(value, pd.Series):
        _raise(
            "expression_non_scalar_control",
            f"Function '{function}' requires a scalar date format.",
            expression,
            span,
            function=function,
        )
    if _is_scalar_missing(value):
        _raise(
            "expression_null_control",
            f"Function '{function}' requires a non-null date format.",
            expression,
            span,
            function=function,
        )
    if not isinstance(value, str):
        _raise(
            "expression_incompatible_type",
            f"Function '{function}' requires a string date format.",
            expression,
            span,
            function=function,
        )

    pattern_parts: list[str] = []
    directives: set[str] = set()
    position = 0
    while position < len(value):
        character = value[position]
        if character != "%":
            pattern_parts.append(re.escape(character))
            position += 1
            continue
        if position + 1 >= len(value):
            _raise_invalid_date_format(value, expression, span, function)
        directive = value[position + 1]
        if directive == "%":
            pattern_parts.append("%")
        elif directive in _DATE_FORMAT_DIRECTIVES:
            if require_complete_date and directive in directives:
                _raise_invalid_date_format(value, expression, span, function)
            directives.add(directive)
            pattern_parts.append(_DATE_PARSE_PATTERNS[directive])
        else:
            _raise_invalid_date_format(value, expression, span, function)
        position += 2

    if not directives:
        _raise_invalid_date_format(value, expression, span, function)
    if require_complete_date and directives != _DATE_FORMAT_DIRECTIVES:
        _raise(
            "expression_invalid_date_format",
            (
                f"Function '{function}' date format must include exactly the portable "
                "date fields %Y, %m, and %d."
            ),
            expression,
            span,
            function=function,
            suggestion="Use a format such as '%Y-%m-%d'.",
        )
    try:
        input_pattern = re.compile("".join(pattern_parts))
    except re.error:
        _raise_invalid_date_format(value, expression, span, function)
    return _DateFormatSpec(value=value, input_pattern=input_pattern)


def _raise_invalid_date_format(
    value: str,
    expression: str,
    span: SourceSpan,
    function: str,
) -> None:
    _raise(
        "expression_invalid_date_format",
        (
            f"Function '{function}' has unsupported or malformed date format "
            f"{value!r}."
        ),
        expression,
        span,
        function=function,
        suggestion="Use only %Y, %m, %d, literal separators, and %% for percent.",
    )


def _evaluate_parse_date(
    value: Any,
    format_spec: _DateFormatSpec,
    index: pd.Index,
) -> Any:
    def parse_one(item: Any) -> Any:
        parsed = _parse_date_value(item, format_spec)
        return pd.NA if parsed is None else parsed

    return _apply_row_local([value], index, parse_one, dtype="object")


def _parse_date_value(value: Any, format_spec: _DateFormatSpec) -> date | None:
    existing = _calendar_date(value)
    if existing is not None:
        return existing
    if not isinstance(value, str) or format_spec.input_pattern.fullmatch(value) is None:
        return None
    try:
        return datetime.strptime(value, format_spec.value).date()
    except (TypeError, ValueError, OverflowError):
        return None


def _evaluate_format_date(
    value: Any,
    format_spec: _DateFormatSpec,
    index: pd.Index,
) -> Any:
    def format_one(item: Any) -> Any:
        calendar_date = _calendar_date(item)
        if calendar_date is None:
            return pd.NA
        result: list[str] = []
        position = 0
        while position < len(format_spec.value):
            character = format_spec.value[position]
            if character != "%":
                result.append(character)
                position += 1
                continue
            directive = format_spec.value[position + 1]
            replacements = {
                "%": "%",
                "Y": f"{calendar_date.year:04d}",
                "m": f"{calendar_date.month:02d}",
                "d": f"{calendar_date.day:02d}",
            }
            result.append(replacements[directive])
            position += 2
        return "".join(result)

    return _apply_row_local([value], index, format_one, dtype="string")


def _evaluate_date_part(name: str, value: Any, index: pd.Index) -> Any:
    def extract_one(item: Any) -> Any:
        calendar_date = _calendar_date(item)
        if calendar_date is None:
            return pd.NA
        if name == "weekday":
            return calendar_date.isoweekday()
        return getattr(calendar_date, name)

    return _apply_row_local([value], index, extract_one, dtype="Int64")


def _evaluate_date_diff(arguments: list[Any], index: pd.Index) -> Any:
    def difference_one(start: Any, end: Any) -> Any:
        start_date = _calendar_date(start)
        end_date = _calendar_date(end)
        if start_date is None or end_date is None:
            return pd.NA
        return (end_date - start_date).days

    return _apply_row_local(arguments, index, difference_one, dtype="Int64")


def _evaluate_add_days(arguments: list[Any], index: pd.Index) -> Any:
    def add_one(value: Any, days: Any) -> Any:
        calendar_date = _calendar_date(value)
        day_count = _exact_integer(days)
        if calendar_date is None or day_count is None:
            return pd.NA
        try:
            return calendar_date + timedelta(days=day_count)
        except (OverflowError, ValueError):
            return pd.NA

    return _apply_row_local(arguments, index, add_one, dtype="object")


def _calendar_date(value: Any) -> date | None:
    if _is_scalar_missing(value):
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None and value.utcoffset() is not None:
            return None
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _evaluate_between(
    arguments: list[Any],
    index: pd.Index,
    expression: str,
    node: FunctionCallNode,
) -> Any:
    def between_one(value: Any, minimum: Any, maximum: Any) -> bool:
        if any(_is_scalar_missing(item) for item in (value, minimum, maximum)):
            return False
        converted = tuple(
            _comparison_family_value(item) for item in (value, minimum, maximum)
        )
        families = {item[0] for item in converted if item is not None}
        if None in converted or len(families) != 1:
            _raise(
                "expression_incompatible_type",
                (
                    "Function 'between' requires value, minimum, and maximum to use "
                    "one finite numeric, date-like, or string family."
                ),
                expression,
                node.span,
                function="between",
            )
        comparable = tuple(item[1] for item in converted if item is not None)
        try:
            return bool(comparable[1] <= comparable[0] <= comparable[2])
        except (TypeError, ValueError, OverflowError) as exc:
            raise ExpressionEvaluationError(
                ExpressionEvaluationIssue(
                    code="expression_incompatible_type",
                    message="Function 'between' received incompatible range values.",
                    expression=expression,
                    source_span=node.span,
                    function="between",
                )
            ) from exc

    return _apply_row_local(arguments, index, between_one, dtype="bool")


def _comparison_family_value(value: Any) -> tuple[str, Any] | None:
    if isinstance(value, str):
        return ("string", value)
    if _is_finite_number(value):
        return ("number", value)
    calendar_date = _calendar_date(value)
    if calendar_date is not None:
        return ("date", calendar_date)
    return None


def _evaluate_membership(
    arguments: list[Any],
    index: pd.Index,
    expression: str,
    node: FunctionCallNode,
    *,
    negate: bool,
) -> Any:
    function = "not_in" if negate else "is_in"

    def membership_one(value: Any, *options: Any) -> bool:
        if _is_scalar_missing(value):
            matched = False
        else:
            matched = any(
                _membership_equal(value, option, expression, node, function)
                for option in options
                if not _is_scalar_missing(option)
            )
        return not matched if negate else matched

    return _apply_row_local(arguments, index, membership_one, dtype="bool")


def _membership_equal(
    value: Any,
    option: Any,
    expression: str,
    node: FunctionCallNode,
    function: str,
) -> bool:
    try:
        result = value == option
        if _is_scalar_missing(result):
            return False
        if hasattr(result, "__len__") and not isinstance(result, (str, bytes)):
            raise ValueError("non-scalar equality result")
        return bool(result)
    except (TypeError, ValueError) as exc:
        raise ExpressionEvaluationError(
            ExpressionEvaluationIssue(
                code="expression_incompatible_type",
                message=f"Function '{function}' received equality-incompatible values.",
                expression=expression,
                source_span=node.span,
                function=function,
            )
        ) from exc


def _evaluate_is_number(value: Any, index: pd.Index) -> Any:
    return _apply_row_local(
        [value],
        index,
        lambda item: _convert_number(item) is not None,
        dtype="bool",
    )


def _evaluate_is_date(
    value: Any,
    format_spec: _DateFormatSpec,
    index: pd.Index,
) -> Any:
    return _apply_row_local(
        [value],
        index,
        lambda item: _parse_date_value(item, format_spec) is not None,
        dtype="bool",
    )


def _evaluate_is_email(value: Any, index: pd.Index) -> Any:
    def validate_one(item: Any) -> bool:
        text = _deterministic_text(item)
        if text is None or text is _INVALID_TEXT or len(text) > 254:
            return False
        if text.count("@") != 1 or any(character.isspace() for character in text):
            return False
        local, domain = text.split("@")
        if not local or not domain or "." not in domain:
            return False
        if (
            local.startswith(".")
            or local.endswith(".")
            or domain.startswith(".")
            or domain.endswith(".")
            or ".." in domain
        ):
            return False
        return True

    return _apply_row_local([value], index, validate_one, dtype="bool")


def _convert_number(value: Any) -> Number | None:
    if _is_scalar_missing(value) or isinstance(value, bool):
        return None
    if _is_finite_number(value):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or _NUMERIC_TEXT_PATTERN.fullmatch(text) is None:
        return None
    try:
        converted: Number
        if _INTEGER_TEXT_PATTERN.fullmatch(text) is not None:
            converted = int(text)
        else:
            converted = float(text)
    except (TypeError, ValueError, OverflowError):
        return None
    return converted if _is_finite_number(converted) else None


def _is_finite_number(value: Any) -> bool:
    if not isinstance(value, Number) or isinstance(value, (bool, complex)):
        return False
    if isinstance(value, Integral):
        return True
    try:
        return bool(math.isfinite(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _deterministic_text(value: Any) -> str | None | object:
    if _is_scalar_missing(value):
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Number) and not isinstance(value, complex):
        try:
            if not math.isfinite(value):
                return _INVALID_TEXT
        except TypeError:
            return _INVALID_TEXT
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return _INVALID_TEXT


def _exact_non_negative_integer(value: Any) -> int | None:
    integer = _exact_integer(value)
    return integer if integer is not None and integer >= 0 else None


def _exact_integer(value: Any) -> int | None:
    number = _convert_number(value)
    if number is None:
        return None
    try:
        integer = int(number)
    except (TypeError, ValueError, OverflowError):
        return None
    return integer if number == integer else None


def _apply_row_local(
    arguments: list[Any],
    index: pd.Index,
    operation: Any,
    *,
    dtype: str,
) -> Any:
    if not any(isinstance(argument, pd.Series) for argument in arguments):
        return operation(*arguments)
    aligned = [_as_series(argument, index) for argument in arguments]
    values = [
        operation(*row)
        for row in zip(*(series.tolist() for series in aligned), strict=True)
    ]
    return pd.Series(values, index=index, dtype=dtype)


def _missing_result(
    arguments: list[Any],
    index: pd.Index,
    dtype: str,
) -> Any:
    if any(isinstance(argument, pd.Series) for argument in arguments):
        return pd.Series(pd.NA, index=index, dtype=dtype)
    return pd.NA


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

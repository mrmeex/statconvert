from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from statconvert.transformations.language import CORE_EXPRESSION_FUNCTIONS

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
from .errors import ExpressionIssue, ExpressionParseError
from .parser import parse_expression_ast


_FUNCTION_SPECS = {spec.name: spec for spec in CORE_EXPRESSION_FUNCTIONS}


@dataclass(frozen=True)
class ParsedExpression:
    """Parsed AST plus deterministic metadata for recipe validation and future UI use."""

    expression: str
    valid: bool
    ast: Expression | None
    referenced_columns: tuple[str, ...]
    functions: tuple[str, ...]
    row_local: bool
    previewable: bool
    result_kind: str
    span: SourceSpan
    errors: tuple[ExpressionIssue, ...] = ()
    warnings: tuple[ExpressionIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a fully JSON-safe analysis result."""

        return {
            "expression": self.expression,
            "valid": self.valid,
            "ast": self.ast.to_dict() if self.ast is not None else None,
            "referenced_columns": list(self.referenced_columns),
            "functions": list(self.functions),
            "row_local": self.row_local,
            "previewable": self.previewable,
            "result_kind": self.result_kind,
            "span": self.span.to_dict(),
            "errors": [error.to_dict() for error in self.errors],
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


def parse_expression(expression: str) -> ParsedExpression:
    """Parse and analyze an expression without exposing internal exceptions."""

    if not isinstance(expression, str):
        issue = ExpressionIssue(
            code="invalid_expression_type",
            message="Expression must be a string.",
            start=0,
            end=0,
        )
        return ParsedExpression(
            expression="",
            valid=False,
            ast=None,
            referenced_columns=(),
            functions=(),
            row_local=False,
            previewable=False,
            result_kind="unknown",
            span=SourceSpan(0, 0),
            errors=(issue,),
        )

    span = SourceSpan(0, len(expression))
    try:
        parsed_ast = parse_expression_ast(expression)
    except ExpressionParseError as exc:
        return ParsedExpression(
            expression=expression,
            valid=False,
            ast=None,
            referenced_columns=(),
            functions=(),
            row_local=False,
            previewable=False,
            result_kind="unknown",
            span=span,
            errors=(exc.issue,),
        )

    columns: list[str] = []
    functions: list[str] = []
    _collect_metadata(parsed_ast.root, columns, functions)
    specs = [_FUNCTION_SPECS[name] for name in functions]
    return ParsedExpression(
        expression=expression,
        valid=True,
        ast=parsed_ast,
        referenced_columns=tuple(columns),
        functions=tuple(functions),
        row_local=all(spec.row_local for spec in specs),
        previewable=all(spec.previewable for spec in specs),
        result_kind=_infer_result_kind(parsed_ast.root),
        span=span,
    )


def _collect_metadata(
    node: ExpressionNode,
    columns: list[str],
    functions: list[str],
) -> None:
    if isinstance(node, ColumnReferenceNode):
        _append_once(columns, node.name)
        return
    if isinstance(node, FunctionCallNode):
        _append_once(functions, node.name)
        for argument in node.arguments:
            _collect_metadata(argument, columns, functions)
        return
    if isinstance(node, UnaryOpNode):
        _collect_metadata(node.operand, columns, functions)
        return
    if isinstance(node, BinaryOpNode):
        _collect_metadata(node.left, columns, functions)
        _collect_metadata(node.right, columns, functions)
        return
    if isinstance(node, GroupNode):
        _collect_metadata(node.expression, columns, functions)


def _infer_result_kind(node: ExpressionNode) -> str:
    if isinstance(node, LiteralNode):
        return node.literal_kind
    if isinstance(node, ColumnReferenceNode):
        return "unknown"
    if isinstance(node, GroupNode):
        return _infer_result_kind(node.expression)
    if isinstance(node, UnaryOpNode):
        if node.operator == "not":
            return "boolean"
        operand_kind = _infer_result_kind(node.operand)
        return "number" if operand_kind == "number" else "unknown"
    if isinstance(node, BinaryOpNode):
        if node.operator in {"==", "!=", "<", "<=", ">", ">=", "and", "or"}:
            return "boolean"
        left_kind = _infer_result_kind(node.left)
        right_kind = _infer_result_kind(node.right)
        if left_kind == right_kind == "number":
            return "number"
        return "unknown"
    if isinstance(node, FunctionCallNode):
        if node.name in {"coalesce", "default_if_missing"}:
            return _infer_coalesce_kind(node.arguments)
        if node.name == "null_if":
            return _infer_result_kind(node.arguments[0])
        if node.name == "if_else":
            true_kind = _infer_result_kind(node.arguments[1])
            false_kind = _infer_result_kind(node.arguments[2])
            return true_kind if true_kind == false_kind else "unknown"
        result_kind = _FUNCTION_SPECS[node.name].result_kind
        if result_kind in {"integer", "float"}:
            return "number"
        if result_kind == "dynamic":
            return "unknown"
        return result_kind
    return "unknown"


def _infer_coalesce_kind(arguments: tuple[ExpressionNode, ...]) -> str:
    kinds = [_infer_result_kind(argument) for argument in arguments]
    known = [kind for kind in kinds if kind != "null"]
    if not known:
        return "null"
    if "unknown" in known:
        return "unknown"
    return known[0] if all(kind == known[0] for kind in known) else "unknown"


def _append_once(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)

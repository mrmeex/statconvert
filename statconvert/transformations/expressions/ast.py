from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeAlias


@dataclass(frozen=True)
class SourceSpan:
    """Half-open character offsets into the original expression."""

    start: int
    end: int

    def to_dict(self) -> dict[str, int]:
        return {"start": self.start, "end": self.end}


@dataclass(frozen=True)
class LiteralNode:
    value: Any
    literal_kind: str
    span: SourceSpan

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "literal",
            "value": self.value,
            "literal_kind": self.literal_kind,
            "span": self.span.to_dict(),
        }


@dataclass(frozen=True)
class ColumnReferenceNode:
    name: str
    bracketed: bool
    span: SourceSpan

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "column_reference",
            "name": self.name,
            "bracketed": self.bracketed,
            "span": self.span.to_dict(),
        }


@dataclass(frozen=True)
class FunctionCallNode:
    name: str
    arguments: tuple[ExpressionNode, ...]
    name_span: SourceSpan
    span: SourceSpan

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "function_call",
            "name": self.name,
            "arguments": [argument.to_dict() for argument in self.arguments],
            "name_span": self.name_span.to_dict(),
            "span": self.span.to_dict(),
        }


@dataclass(frozen=True)
class UnaryOpNode:
    operator: str
    operand: ExpressionNode
    operator_span: SourceSpan
    span: SourceSpan

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "unary_operation",
            "operator": self.operator,
            "operand": self.operand.to_dict(),
            "operator_span": self.operator_span.to_dict(),
            "span": self.span.to_dict(),
        }


@dataclass(frozen=True)
class BinaryOpNode:
    left: ExpressionNode
    operator: str
    right: ExpressionNode
    operator_span: SourceSpan
    span: SourceSpan

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "binary_operation",
            "left": self.left.to_dict(),
            "operator": self.operator,
            "right": self.right.to_dict(),
            "operator_span": self.operator_span.to_dict(),
            "span": self.span.to_dict(),
        }


@dataclass(frozen=True)
class GroupNode:
    expression: ExpressionNode
    span: SourceSpan

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "group",
            "expression": self.expression.to_dict(),
            "span": self.span.to_dict(),
        }


ExpressionNode: TypeAlias = (
    LiteralNode
    | ColumnReferenceNode
    | FunctionCallNode
    | UnaryOpNode
    | BinaryOpNode
    | GroupNode
)


@dataclass(frozen=True)
class Expression:
    """Immutable parsed expression root."""

    root: ExpressionNode
    span: SourceSpan

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "expression",
            "root": self.root.to_dict(),
            "span": self.span.to_dict(),
        }
